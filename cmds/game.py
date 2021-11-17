import discord
from discord.ext import commands
import json

from library import user_who
from core.classes import Cog_Extension

jdata = json.load(open('setting.json',mode='r',encoding='utf8'))

with open('gamer_data.json',mode='r',encoding='utf8') as jfile:
    gdata = json.load(jfile)

games = ['steam','osu','apex','lol']
class game(Cog_Extension):
    
    @commands.group(invoke_without_command=True)
    async def game(self,ctx):
        pass
        
    @game.command()
    async def set(self,ctx,game,data=None):
        if not str(ctx.author.id) in gdata:
            with open('gamer_data.json',mode='w',encoding='utf8') as jfile:
                gdata[f'{ctx.author.id}'] = {}
                json.dump(gdata,jfile,indent=4)
            await ctx.send('偵測到資料庫內無使用者資料，已自動註冊',delete_after=5)

        if game in games:
            user = str(ctx.author.id)

            if not game in gdata[user]:
                with open('gamer_data.json',mode='w',encoding='utf8') as jfile:
                    gdata[user][game] = 'None'
                    json.dump(gdata,jfile,indent=4)
                #await ctx.send('偵測到資料庫內無使用者資料，已自動補齊')

            with open('gamer_data.json',mode='w',encoding='utf8') as jfile:
                if data == None:
                    gdata[user][game] = 'None'
                    await ctx.send(f'已重設{game}資料')
                else:
                    gdata[user][game] = data
                    await ctx.send(f'已將{game}資料設定為 {data}')
                json.dump(gdata,jfile,indent=4)
        
        else:
            await ctx.send(f'遊戲錯誤:此遊戲目前未開放設定\n目前支援:{games}',delete_after=10)

    @game.command()
    @commands.is_owner()
    async def find(self,ctx,user):
        user = await user_who(ctx,user)
        if user != None:
            data = {}
            for game in games:
                if game in gdata[f'{user.id}']:
                    data[game] = gdata[f'{user.id}'][game]
                else:
                    data[game] = 'None'

            embed = discord.Embed(title=user, color=0xc4e9ff)
            for game in games:
                embed.add_field(name=game, value=data[game], inline=False)
            embed.set_thumbnail(url=user.avatar_url)
            await ctx.send(embed=embed)



def setup(bot):
    bot.add_cog(game(bot))