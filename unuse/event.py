import discord
from discord.ext import commands
import json
from core.classes import Cog_Extension

with open('setting.json',mode='r',encoding='utf8') as jfile:
    jdata = json.load(jfile)

class event(Cog_Extension):
    @commands.command()
    async def a(self, ctx, msg):
        await ctx.send(jdata[f'{ctx.author.id}_test'])
        jdata[f'{ctx.author.id}_test'] = msg
        with open('setting.json',mode='w',encoding='utf8') as jfile:
            json.dump(jdata,jfile,indent=4)
        await ctx.send(jdata[f'{ctx.author.id}_test'])
        
        result = 0
        for a in jdata['test']:
            if a == f'{ctx.author.id}_test':
                result = result +1

        if result == 0:
            jdata['test'].append(f'{ctx.author.id}_test')
            with open('setting.json',mode='w',encoding='utf8') as jfile:
                json.dump(jdata,jfile,indent=4)
        
        else:
            await ctx.send('no')


def setup(bot):
    bot.add_cog(event(bot))