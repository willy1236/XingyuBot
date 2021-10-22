import discord
from discord.ext import commands
import json
from core.classes import Cog_Extension
import asyncio
from pyosu import OsuApi

with open('setting.json',mode='r',encoding='utf8') as jfile:
    jdata = json.load(jfile)

with open('command.json',mode='r',encoding='utf8') as jfile:
    comdata = json.load(jfile)

api = OsuApi('1e99d316fc8fb8e630fe92b4d7cb32701713d2d2')
#async def main():
#    bests = await api.get_user_bests('Renondedju')
#    for best in bests:
#        print(best.__dict__)


class lol(Cog_Extension):
    @commands.command()
    async def osu(self,ctx,*arg):

        if arg[0] == 'player':
            player = await api.get_user(arg[1])
            url = 'https://osu.ppy.sh/users/'+str(player.user_id)
            bot_name = self.bot.user.name

            embed = discord.Embed(title=player.username, url=url, color=0xeee657)
            embed.add_field(name="等級", value=str(player.level), inline=True)
            embed.add_field(name="總遊玩次數", value=str(player.playcount), inline=True)
            embed.add_field(name="總pp數", value=str(player.pp_raw), inline=True)
            embed.add_field(name="準確率", value=str(player.accuracy), inline=True)
            embed.add_field(name="全球排名", value=str(player.pp_rank), inline=True)
            embed.add_field(name="國內排名", value=str(player.pp_country_rank), inline=True) 
            embed.add_field(name="國家", value=str(player.country), inline=True)
            
            #embed.set_thumbnail(url=url)
        
            await ctx.send(embed=embed)
        #elif arg[0] == 'match':
        #    player = await api.get_user(arg[1])
        #    id = 88393653
        #    match = await api.get_match(id)
        #    print(match)
        else:
            await ctx.send('目前沒有這種用法喔')



def setup(bot):
    bot.add_cog(lol(bot))