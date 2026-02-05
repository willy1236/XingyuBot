import discord
from discord.commands import SlashCommandGroup
from discord.ext import commands

from starlib import BotEmbed, ChoiceList, Jsondb, sclient
from starlib.instance import happycamp_guild
from starlib.models.postgresql import DiscordUser

from ..checks import RegisteredContext, ensure_registered
from ..extension import Cog_Extension
from ..uiElement.view import DeletePetView

pet_option = ChoiceList.set("pet_option")

class system_user(Cog_Extension):
    pet = SlashCommandGroup("pet", "寵物相關指令")

    @commands.slash_command(description="查看用戶資訊")
    @ensure_registered()
    async def ui(self, ctx: RegisteredContext, member: discord.Option(discord.Member, name="用戶", description="留空以查詢自己", default=None)):
        user_dc:discord.Member = member or ctx.author
        cuser = ctx.cuser

        user = sclient.sqldb.get_dcuser(user_dc.id) or DiscordUser(discord_id=user_dc.id)
        user_embed = BotEmbed.general(name="Discord資料", icon_url=user_dc.avatar.url if user_dc.avatar else None)
        coins = sclient.sqldb.get_coin(user_dc.id)
        user_embed.add_field(name="⭐星塵", value=coins.stardust)
        user_embed.add_field(name="PT點數", value=coins.point)
        user_embed.add_field(name="Rcoin", value=coins.rcoin)

        if user.max_sign_consecutive_days:
            user_embed.add_field(name="連續簽到最高天數", value=user.max_sign_consecutive_days)
        if user.meatball_times:
            user_embed.add_field(name="貢丸次數", value=user.meatball_times)
        if user.registration:
            guild = self.bot.get_guild(user.registration.guild_id)
            user_embed.add_field(name="戶籍", value=guild.name if guild else user.registration.guild_id)

        dbdata = sclient.sqldb.get_discord_accounts(cuser.id)
        if len(dbdata) > 1:
            alt_accounts = ", ".join([f"<@{i.external_id}>" for i in dbdata if int(i.external_id) != user_dc.id])
            user_embed.add_field(name="綁定的其他 Discord 帳號", value=f"{alt_accounts}", inline=False)

        cloud_user_embed = BotEmbed.general("使用者資料", icon_url=user_dc.avatar.url if user_dc.avatar else None)
        if cuser:
            cloud_user_embed.add_field(name="雲端共用資料夾", value="已共用" if cuser.drive_share_id else "未共用")
            if cuser.name:
                cloud_user_embed.add_field(name="註冊名稱", value=cuser.name)

        embeds = [user_embed, cloud_user_embed]

        if ctx.guild_id in happycamp_guild:
            happycamp_embed = BotEmbed.general("快樂營使用者資料", icon_url=user_dc.avatar.url if user_dc.avatar else None)
            happycamp_embed.add_field(name="累計語音時間", value=sclient.sqldb.get_voice_time(user_dc.id, ctx.guild_id).total_minute)
            embeds.append(happycamp_embed)

        await ctx.respond(embeds=embeds)

    @commands.slash_command(description="取得綁定碼")
    @ensure_registered()
    async def link_code(self, ctx: RegisteredContext):
        code = sclient.sqldb.get_or_create_link_code(ctx.cuser.id)
        embed = BotEmbed.simple("綁定碼", f"請在新綁定帳號欲註冊時輸入：\n{code.code}\n綁定碼10分鐘內有效，可使用當前指令重新獲取")
        embed.set_footer(text=f"擁有此綁定碼的人可以綁定你的帳號，請勿隨意提供給他人")
        await ctx.respond(embed=embed, ephemeral=True)

    @pet.command(description="查看寵物資訊")
    async def check(self, ctx, user_dc: discord.Option(discord.Member, name="用戶", description="可不輸入以查詢自己", default=None)):
        user_dc = user_dc or ctx.author
        pet = sclient.sqldb.get_pet(user_dc.id)
        embed = pet.desplay(user_dc) if pet else BotEmbed.simple(f"{user_dc.name} 的寵物", "用戶沒有認養寵物")
        await ctx.respond(embed=embed)

    @pet.command(description="認養寵物")
    async def add(
        self,
        ctx,
        species: discord.Option(str, name="物種", description="想認養的寵物物種", choices=pet_option),
        name: discord.Option(str, name="寵物名", description="想幫寵物取的名子"),
    ):
        r = sclient.sqldb.create_user_pet(ctx.author.id, species, name)
        if r:
            await ctx.respond(r)
        else:
            await ctx.respond(f"你收養了一隻名叫 {name} 的{Jsondb.get_tw(species, 'pet_option')}!")

    @pet.command(description="放生寵物")
    async def remove(self,ctx):
        pet = sclient.sqldb.get_pet(ctx.author.id)
        if not pet:
            await ctx.respond("你沒有寵物")
            return
        await ctx.respond("你真的確定要放生寵物嗎?", view=DeletePetView())

    @commands.slash_command(description="查看語音時間排行榜")
    async def voice_time_leaderboard(self, ctx: discord.ApplicationContext):
        # if ctx.guild_id not in happycamp_guild:
        #     await ctx.respond("此指令僅限快樂營伺服器使用")
        #     return

        leaderboard = sclient.sqldb.get_voice_time_leaderboard(ctx.guild_id, limit=10)
        if not leaderboard:
            await ctx.respond("目前沒有語音時間紀錄")
            return

        embed = BotEmbed.general("語音時間排行榜", icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
        description_lines = []
        for idx, record in enumerate(leaderboard, start=1):
            user = self.bot.get_user(record.discord_id)
            user_name = user.mention if user else f"未知用戶({record.discord_id})"
            description_lines.append(f"**{idx}. {user_name}** - {record.total_minute}")

        embed.description = "\n".join(description_lines)
        await ctx.respond(embed=embed)


def setup(bot):
    bot.add_cog(system_user(bot))
