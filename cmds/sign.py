import discord
from discord.ext import commands
import json
from library import Counter
from core.classes import Cog_Extension

with open('setting.json',mode='r',encoding='utf8') as jfile:
    jdata = json.load(jfile)

with open('sign_week.json',mode='r',encoding='utf8') as jfile:
    jwsign2 = json.load(jfile)
    jwsign = Counter(jwsign2)

with open('point.json',mode='r',encoding='utf8') as jfile:
    jpt2 = json.load(jfile)
    jpt = Counter(jpt2)

class sign(Cog_Extension):
    @commands.command()
    async def sign(self,ctx):
        await ctx.message.delete()
        with open('sign_day.json',mode='r',encoding='utf8') as jfile:
            jdsign = json.load(jfile)

        list = set(jdsign['sign'])
        if not int(ctx.author.id) in list:
            signer = str(ctx.author.id)
            #日常
            jdsign['sign'].append(ctx.author.id)
            with open('sign_day.json',mode='w',encoding='utf8') as jfile:
                json.dump(jdsign,jfile,indent=4)
            #週常
            with open('sign_week.json','w',encoding='utf8') as jfile:
                jwsign[signer] = jwsign[signer]+1
                json.dump(jwsign,jfile,indent=4)
            
            if ctx.guild.id == jdata['001_guild']:
                with open('point.json',mode='w',encoding='utf8') as jfile:
                    jpt[signer] = jpt[signer]+1
                    json.dump(jpt,jfile,indent=4)
                await ctx.send(f'{ctx.author.mention} 簽到完成:pt點數+1',delete_after=5)
            else:
                await ctx.send(f'{ctx.author.mention} 簽到完成!',delete_after=5)

        else:
            await ctx.send(f'{ctx.author.mention} 已經簽到過了喔',delete_after=5)
    
    #@commands.Cog.listener()
    #async def on_voice_state_update(self,user, before, after):
        #guild = after.channel.guild
        #print(user.voice.deaf)

        #jdsign['sign'].append(f'{user.id}')
        #with open('sign_day.json',mode='w',encoding='utf8') as jfile:
        #    json.dump(jdsign,jfile,indent=4)

            #jfile.write(deta)
        #print('4')

def setup(bot):
    bot.add_cog(sign(bot))