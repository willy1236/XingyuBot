import discord
from discord.ext import commands
from discord.commands import SlashCommandGroup
from starlib import BotEmbed,ChoiceList,sclient
from starlib.uiElement.button import Delete_Pet_button
from ..extension import Cog_Extension

pet_option = ChoiceList.set('pet_option')

class system_user(Cog_Extension):
    pet = SlashCommandGroup("pet", "寵物相關指令")

    @commands.slash_command(description='查看用戶資訊')
    async def ui(self,ctx:discord.ApplicationContext,
                 user_dc:discord.Option(discord.Member,name='用戶',description='留空以查詢自己',default=None),
                 show_alt_account:discord.Option(bool,name='顯示小帳',description='顯示小帳，僅在查詢自己時可使用',default=False)):
        if user_dc and not await self.bot.is_owner(ctx.author):
            show_alt_account = False
        user_dc = user_dc or ctx.author
        user = sclient.sqldb.get_dcuser(user_dc.id,True,user_dc)
        if not user:
            sclient.sqldb.create_discord_user(user_dc.id)
            user = sclient.sqldb.get_dcuser(user_dc.id,True,user_dc)

        pet = user.get_pet()
        #game = user.get_game()
        user_embed = user.embed(self.bot)
        if show_alt_account:
            dbdata = user.get_alternate_account()
            if dbdata:
                alt_accounts = ", ".join([f'<@{i}>' for i in dbdata])
                user_embed.add_field(name='小帳',value=f"{alt_accounts}",inline=False)
        pet_embed = pet.desplay(user_dc) if pet else BotEmbed.simple(f'{user_dc.name} 的寵物','用戶沒有認養寵物')
        #game_embed = game.desplay(user_dc) if game else GameInfoPage().desplay(user_dc)
        await ctx.respond(embeds=[user_embed, pet_embed])

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