import discord
from discord.ext import commands
from core.classes import Cog_Extension
from discord.commands import SlashCommandGroup
from starcord import BotEmbed,ChoiceList,sclient
from starcord.ui_element.button import Delete_Pet_button

pet_option = ChoiceList.set('pet_option')

class system_user(Cog_Extension):
    pet = SlashCommandGroup("pet", "寵物相關指令")

    @pet.command(description='查看寵物資訊')
    async def check(self,ctx,user_dc:discord.Option(discord.Member,name='用戶',description='可不輸入以查詢自己',default=None)):
        user_dc = user_dc or ctx.author
        pet = sclient.get_pet(user_dc.id)
        embed = pet.desplay(user_dc) if pet else BotEmbed.simple(f'{user_dc.name} 的寵物','用戶沒有認養寵物')
        await ctx.respond(embed=embed)
    
    @pet.command(description='認養寵物')
    async def add(self,ctx,
                  species:discord.Option(str,name='物種',description='想認養的寵物物種',choices=pet_option),
                  name:discord.Option(str,name='寵物名',description='想幫寵物取的名子')):
        r = sclient.create_user_pet(ctx.author.id,species,name)
        if r:
            await ctx.respond(r)
        else:
            await ctx.respond(f"你收養了一隻名叫 {name} 的{ChoiceList.get_tw(species,'pet_option')}!")
    
    @pet.command(description='放生寵物')
    async def remove(self,ctx):
        pet = sclient.get_pet(ctx.author.id)
        if not pet:
            await ctx.respond('你沒有寵物')
            return
        await ctx.respond('你真的確定要放生寵物嗎?',view=Delete_Pet_button())

def setup(bot):
    bot.add_cog(system_user(bot))