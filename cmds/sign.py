import discord
from discord.ext import commands
import json
from library import Counter,Point
from core.classes import Cog_Extension


jdata = json.load(open('setting.json',mode='r',encoding='utf8'))

with open('database/sign_week.json',mode='r',encoding='utf8') as jfile:
    jwsign2 = json.load(jfile)
    jwsign = Counter(jwsign2)

class sign(Cog_Extension):
    @commands.command()
    async def sign(self,ctx):
        await ctx.message.delete()
        jdsign = json.load(open('database/sign_day.json',mode='r',encoding='utf8'))
        
        if ctx.author.id not in jdsign:
            signer = str(ctx.author.id)
            #日常
            jdsign.append(ctx.author.id)
            with open('database/sign_day.json',mode='w',encoding='utf8') as jfile:
                json.dump(jdsign,jfile,indent=4)
            #週常
            with open('database/sign_week.json','w',encoding='utf8') as jfile:
                jwsign[signer] = jwsign[signer]+1
                json.dump(jwsign,jfile,indent=4)
            
            if ctx.guild.id == jdata['guild']['001']:
                Point(signer).add(1)
                await ctx.send(f'{ctx.author.mention} 簽到完成:pt點數+1',delete_after=5)
            else:
                await ctx.send(f'{ctx.author.mention} 簽到完成!',delete_after=5)

        else:
            await ctx.send(f'{ctx.author.mention} 已經簽到過了喔',delete_after=5)
    
    # @commands.Cog.listener()
    # async def on_voice_state_update(self,user, before, after):
    #     if before.channel is None and after.channel is not None and after.channel.guild.id == jdata['guild']['001']:
    #         print(user.voice.deaf)

def setup(bot):
    bot.add_cog(sign(bot))