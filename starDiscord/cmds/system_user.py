import discord
from discord.commands import SlashCommandGroup
from discord.ext import commands

from starlib import BotEmbed, ChoiceList, Jsondb, sclient
from starlib.database.postgresql.enums import PlatformType
from starlib.database.postgresql.models import DiscordUser
from starlib.identity import IdentityUnavailable, fetch_twitch_passports, resolve_identity
from starlib.instance import happycamp_guild

from ..checks import with_identity
from ..extension import Cog_Extension
from ..uiElement.view import DeletePetView

pet_option = ChoiceList.set("pet_option")

PLATFORM_DISPLAY_NAME = {
    PlatformType.Discord: "Discord",
    PlatformType.Twitch: "Twitch",
    PlatformType.Minecraft: "Minecraft",
}

class system_user(Cog_Extension):
    pet = SlashCommandGroup("pet", "寵物相關指令")

    @commands.slash_command(description="查看使用者的基本資訊")
    @with_identity()
    async def user_info(self, ctx: discord.ApplicationContext, member: discord.Option(discord.Member, name="用戶", description="留空以查詢自己", default=None)):
        # 身分查詢加上即時查 Twitch 可能超過 Discord 的 3 秒回應期限
        await ctx.defer()
        user_dc: discord.Member = member or ctx.author

        # 析域帳號：查自己用 with_identity 取得的結果；查別人不替沒用過 bot 的人發臨時 ID，查不到視為未註冊
        identity = ctx.identity
        unavailable = False
        if user_dc.id != ctx.author.id:
            try:
                identity = await resolve_identity(user_dc.id, create=False)
            except IdentityUnavailable:
                identity = None
                unavailable = True

        account_embed = BotEmbed.general("使用者資料", icon_url=user_dc.avatar.url if user_dc.avatar else None)
        if unavailable:
            account_embed.add_field(name="析域帳號", value="身分服務暫時無法連線")
        elif identity is None or not identity.is_formal:
            account_embed.add_field(name="析域帳號", value="未註冊")
        else:
            account_embed.add_field(name="析域帳號", value=identity.username or "已註冊")

        if identity is not None:
            account_embed.add_field(name="雲端共用資料夾", value="已共用" if sclient.sqldb.get_drive_share(identity.user_id) else "未共用")
            account_lines = []
            for discord_id in sclient.sqldb.get_discord_ids_by_user(identity.user_id):
                if discord_id != user_dc.id:
                    account_lines.append(f"Discord：<@{discord_id}>")
            # Twitch 以 auth server 為準，每次即時查；連不上就不顯示。臨時使用者不是域民，不必查；
            # 這次解析剛向 auth server 查過就直接用，不再查第二次
            if identity.is_formal:
                passports = identity.twitch_passports
                if passports is None:
                    passports = await fetch_twitch_passports(user_dc.id)
                for passport in passports:
                    account_lines.append(f"{PLATFORM_DISPLAY_NAME[PlatformType.Twitch]}：{passport.username or passport.subject}")
            for account in sclient.sqldb.get_linked_accounts(identity.user_id):
                platform = PlatformType(account.platform)
                if platform in (PlatformType.Twitch, PlatformType.Google):
                    continue  # linked_account 殘留的 Twitch、Google 列不顯示
                platform_name = PLATFORM_DISPLAY_NAME.get(platform, platform.name)
                account_lines.append(f"{platform_name}：{account.display_name or account.external_id}")
            if account_lines:
                account_embed.add_field(name="綁定的帳號", value="\n".join(account_lines), inline=False)

        # discord
        user = sclient.sqldb.get_dcuser(user_dc.id) or DiscordUser(discord_id=user_dc.id)
        discord_user_embed = BotEmbed.general(name="Discord資料", icon_url=user_dc.avatar.url if user_dc.avatar else None)
        coins = sclient.sqldb.get_coin(user_dc.id)
        discord_user_embed.add_field(name="⭐星塵", value=coins.stardust)
        discord_user_embed.add_field(name="PT點數", value=coins.point)
        discord_user_embed.add_field(name="Rcoin", value=coins.rcoin)

        if user.max_sign_consecutive_days:
            discord_user_embed.add_field(name="連續簽到最高天數", value=user.max_sign_consecutive_days)
        if user.meatball_times:
            discord_user_embed.add_field(name="貢丸次數", value=user.meatball_times)
        if user.registration:
            guild = self.bot.get_guild(user.registration.guild_id)
            discord_user_embed.add_field(name="戶籍", value=guild.name if guild else user.registration.guild_id)

        embeds = [account_embed, discord_user_embed]

        # HappyCamp
        if ctx.guild_id in happycamp_guild:
            happycamp_embed = BotEmbed.general("快樂營使用者資料", icon_url=user_dc.avatar.url if user_dc.avatar else None)
            happycamp_embed.add_field(name="累計語音時間", value=sclient.sqldb.get_voice_time(user_dc.id, ctx.guild_id).total_minute)
            embeds.append(happycamp_embed)

        await ctx.respond(embeds=embeds)

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
