import discord
from discord.ext import commands
import json, requests
from core.classes import Cog_Extension
from bs4 import BeautifulSoup

with open('setting.json',mode='r',encoding='utf8') as jfile:
    jdata = json.load(jfile)

def player_search(player,url):
    response = requests.get(url)
    soup = BeautifulSoup(response.text, "html.parser")
    results = soup.find_all("h1",class_="row")

    for result in results:
        if result.div.string == None:
            result2 = str(result.div)[166:]
            lvl = ''.join([x for x in result2 if x.isdigit()])
            return lvl

class lol(Cog_Extension):

    @commands.command()
    async def lol(self,ctx,*arg):

        if arg[0] == 'player':
            player = arg[1]
            url = 'https://lol.moa.tw/summoner/show/'+player
            lvl = player_search(player,url)

            embed = discord.Embed(title="LOL玩家查詢", url=url, color=0xeee657)
            embed.add_field(name="玩家名稱", value=player, inline=False)
            embed.add_field(name="等級", value=lvl, inline=False)
            embed.add_field(name="查詢戰績", value="LOL戰績網(lol.moa.tw)", inline=False)
            embed.set_thumbnail(url='https://i.imgur.com/B0TMreW.png')
        
            await ctx.send(embed=embed)
        else:
            await ctx.send('目前沒有這種用法喔')


def setup(bot):
    bot.add_cog(lol(bot))