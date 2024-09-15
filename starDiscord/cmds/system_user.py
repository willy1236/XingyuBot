import discord
from discord.ext import commands
from discord.commands import SlashCommandGroup
from starlib import BotEmbed,ChoiceList,sclient
from starlib.uiElement.button import Delete_Pet_button
from starlib.models.mysql import DiscordUser
from ..extension import Cog_Extension

pet_option = ChoiceList.set('pet_option')

class system_user(Cog_Extension):
    pet = SlashCommandGroup("pet", "寵物相關指令")

    @commands.slash_command(description='查看用戶資訊')
    async def ui(self,ctx:discord.ApplicationContext,
                 user_dc:discord.Option(discord.Member,name='用戶',description='留空以查詢自己',default=None),
                 show_alt_account:discord.Option(bool,name='顯示小帳',description='顯示小帳，僅在查詢自己時可使用',default=False)):
        user_dc:discord.Member = user_dc or ctx.author
        if user_dc != ctx.author and not await self.bot.is_owner(ctx.author):
            show_alt_account = False
        
        user = sclient.sqldb.get_dcuser(user_dc.id) or DiscordUser(discord_id=user_dc.id)
        user_embed = BotEmbed.general(name="Discord資料", icon_url=user_dc.avatar.url if user_dc.avatar else None)
        main_account_id = sclient.sqldb.get_main_account(user.discord_id)
        if main_account_id:
            main_account = self.bot.get_user(main_account_id).mention or main_account_id
            user_embed.description = f"{main_account} 的小帳"
        
        # user_embed.add_field(name='⭐星塵',value=user_dc.scoin)
        # user_embed.add_field(name='PT點數',value=user_dc.point)
        # user_embed.add_field(name='Rcoin',value=user_dc.rcoin)
        user_embed.add_field(name='連續簽到最高天數',value=user.max_sign_consecutive_days)
        if user.meatball_times:
            user_embed.add_field(name='貢丸次數',value=user.meatball_times)
        if user.registration:
            guild = self.bot.get_guild(user.registration.guild_id)
            user_embed.add_field(name='戶籍',value=guild.name if guild else user.registration.guild_id)

        if show_alt_account:
            dbdata = sclient.sqldb.get_alternate_account(user.discord_id)
            if dbdata:
                alt_accounts = ", ".join([f'<@{i}>' for i in dbdata])
                user_embed.add_field(name='小帳',value=f"{alt_accounts}",inline=False)

        cuser = sclient.sqldb.get_cloud_user(user_dc.id)
        cloud_user_embed = BotEmbed.general("使用者資料", icon_url=user_dc.avatar.url if user_dc.avatar else None)
        if cuser:
            cloud_user_embed.add_field(name='雲端共用資料夾',value="已共用" if cuser.drive_share_id else "未共用")
            cloud_user_embed.add_field(name='Twitch ID',value=cuser.twitch_id or "未設定")
        await ctx.respond(embeds=[user_embed, cloud_user_embed])

    @pet.command(description='查看寵物資訊')
    async def check(self,ctx,user_dc:discord.Option(discord.Member,name='用戶',description='可不輸入以查詢自己',default=None)):
        user_dc = user_dc or ctx.author
        pet = sclient.sqldb.get_pet(user_dc.id)
        embed = pet.desplay(user_dc) if pet else BotEmbed.simple(f'{user_dc.name} 的寵物','用戶沒有認養寵物')
        await ctx.respond(embed=embed)
    
    @pet.command(description='認養寵物')
    async def add(self,ctx,
                  species:discord.Option(str,name='物種',description='想認養的寵物物種',choices=pet_option),
                  name:discord.Option(str,name='寵物名',description='想幫寵物取的名子')):
        r = sclient.sqldb.create_user_pet(ctx.author.id,species,name)
        if r:
            await ctx.respond(r)
        else:
            await ctx.respond(f"你收養了一隻名叫 {name} 的{ChoiceList.get_tw(species,'pet_option')}!")
    
    @pet.command(description='放生寵物')
    async def remove(self,ctx):
        pet = sclient.sqldb.get_pet(ctx.author.id)
        if not pet:
            await ctx.respond('你沒有寵物')
            return
        await ctx.respond('你真的確定要放生寵物嗎?',view=Delete_Pet_button())

def setup(bot):
    bot.add_cog(system_user(bot))