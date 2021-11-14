import discord
from discord.ext import commands
import json
from core.classes import Cog_Extension

with open('setting.json',mode='r',encoding='utf8') as jfile:
    jdata = json.load(jfile)

with open('gamer_data.json',mode='r',encoding='utf8') as jfile:
    gdata = json.load(jfile)

games = ['steam','osu','apex','lol']
class game(Cog_Extension):
    
    @commands.group(invoke_without_command=True)
    async def game(self):
        pass
        
    @game.command()
    async def set(self,ctx,*arg):
        if not str(ctx.author.id) in gdata:
            with open('gamer_data.json',mode='w',encoding='utf8') as jfile:
                gdata[f'{ctx.author.id}'] = {}
                json.dump(gdata,jfile,indent=4)
            await ctx.send('偵測到資料庫內無使用者資料，已自動註冊')

        if len(arg) >= 1 and arg[0] in games:
            game = arg[0]
            user = str(ctx.author.id)
            if len(arg) >= 2:
                data = arg[1]
            else:
                data = None

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
        
        elif not len(arg) >=1:
            await ctx.send('缺少參數:請輸入要設定的內容')
        elif not arg[0] in games:
            await ctx.send(f'遊戲錯誤:此遊戲目前未開放設定\n目前支援:{games}')

    @game.command()
    async def find(self,ctx,*arg):
        user:commands.MemberConverter = arg 
        if user != None:
            data = {}
            for game in games:
                print(data)
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