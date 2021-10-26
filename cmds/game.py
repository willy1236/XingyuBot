import discord
from discord.ext import commands
import json
from core.classes import Cog_Extension

with open('setting.json',mode='r',encoding='utf8') as jfile:
    jdata = json.load(jfile)

with open('gamer_data.json',mode='r',encoding='utf8') as jfile:
    gdata = json.load(jfile)


class game(Cog_Extension):
    
    @commands.command()
    async def game(self,ctx,*arg):
        if not str(ctx.author.id) in gdata:
            with open('gamer_data.json',mode='w',encoding='utf8') as jfile:
                gdata[f'{ctx.author.id}'] = {}
                json.dump(gdata,jfile,indent=4)
            await ctx.send('偵測到資料庫內無使用者資料，已自動註冊')
            
        if arg[0] == 'steam':
            if not 'steam' in gdata[f'{ctx.author.id}']:
                with open('gamer_data.json',mode='w',encoding='utf8') as jfile:
                    gdata[f'{ctx.author.id}']['steam'] = 'None'
                    json.dump(gdata,jfile,indent=4)
                await ctx.send('偵測到資料庫內無使用者資料，已自動補齊')
            
            with open('gamer_data.json',mode='w',encoding='utf8') as jfile:
                print(len(arg))
                if len(arg) == 1 :
                    gdata[f'{ctx.author.id}']['steam'] = 'None'
                    await ctx.send('已重設steam資料')
                else:
                    gdata[f'{ctx.author.id}']['steam'] = arg[1]
                    await ctx.send(f'已將steam資料設定為 {arg[1]}')
                json.dump(gdata,jfile,indent=4)
            
                



def setup(bot):
    bot.add_cog(game(bot))