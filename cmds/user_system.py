import asyncio
from discord import Embed
from discord.ext import commands
from core.classes import Cog_Extension

from BotLib.userlib import *
from BotLib.database import Database
from BotLib.funtions import find
from BotLib.basic import BotEmbed

class user_system(Cog_Extension):
    @commands.command()
    async def ui(self,ctx,user=None):
        user_dc = await find.user(ctx,user) or ctx.author
        user = User(user_dc.id,user_dc.name)
        await ctx.send(embed=user.desplay())

    @commands.command()
    async def bag(self,ctx,user=None):
        user_dc = await find.user(ctx,user) or ctx.author
        user = User(user_dc.id,user_dc.name)
        embed = BotEmbed.general('你的包包')
        if user.bag:
            text = ""
            for i in user.bag:
                text += f'{i} x{user.bag[i]}\n'
            embed.add_field(name='一般物品',value=text)
        else:
            embed.add_field(name='一般物品',value='背包空無一物')
        await ctx.send(embed=embed)

    @commands.group(invoke_without_command=True)
    async def pet(self,ctx,user=None):
        user_dc = await find.user(ctx,user) or ctx.author
        pet = Pet(user_dc.id)
        if pet.has_pet:
            embed = BotEmbed.general(f'{ctx.author.name} 的寵物')
            embed.add_field(name='寵物名',value=pet.name)
            embed.add_field(name='寵物物種',value=pet.species)
            await ctx.send(embed=embed)
        else:
            await ctx.send('用戶沒有認養寵物')
    
    @pet.command()
    async def add(self,ctx,species,name):
        user = User(ctx.author.id)
        if user.pet:
            await ctx.send('你已經有寵物了')
            return
        if species not in ['shark','dog','cat','fox']:
            await ctx.send('沒有該物種的寵物喔')    
            return
        
        db = Database()
        jpet = db.jpet
        pet = {
            'name' : name,
            'type' : type
        }
        jpet[str(user.id)] = pet
        db.write('jpet',jpet)
        await ctx.send(f'你收養了一隻名叫 {name} 的{type}!')

    @pet.command()
    async def remove(self,ctx):
        def check(m):
            try:
                return m.content == 'y' and m.author == ctx.author
            except:
                return False
        user = User(ctx.author.id)
        if user.pet:
            await ctx.send('你沒有寵物')
            return

        try:
            await ctx.send('你真的確定要放生寵物嗎?(輸入y確定)')
            msg = await self.bot.wait_for('message', check=check,timeout=60)
            if msg.content == 'y':
                db = Database()
                jpet = db.jpet
                del jpet[str(ctx.author.id)]
                db.write('jpet',jpet)
                await ctx.send('寵物已放生')
            else:
                await ctx.send(f'取消放生寵物')
        except asyncio.TimeoutError:
            await ctx.send(f'{ctx.author.name} 超時自動取消放生')

def setup(bot):
    bot.add_cog(user_system(bot))