import discord
from discord.ext import commands
import json
from core.classes import Cog_Extension

with open('setting.json',mode='r',encoding='utf8') as jfile:
    jdata = json.load(jfile)

with open('sign_day.json',mode='r',encoding='utf8') as jfile:
    jdsign = json.load(jfile)

with open('sign_week.json',mode='r',encoding='utf8') as jfile:
    jwsign2 = json.load(jfile)

with open('point.json',mode='r',encoding='utf8') as jfile:
    jpt2 = json.load(jfile)

#如果為第一次簽到 就先補0避免keyerror
class Counter(dict):
    def __missing__(self, key): 
        return 0
jwsign = Counter(jwsign2)
jpt = Counter(jpt2)

class sign(Cog_Extension):
    @commands.command()
    async def sign(self,ctx):
        has_signed = 0 
        for signed_id in jdsign['sign']:
            if int(ctx.author.id) == int(signed_id):
                has_signed = has_signed+1
           
        #list = set(jdsign['sign'])
        #if int(ctx.author.id) in list:

        if has_signed == 0:
            signer = str(ctx.author.id)
            #日常
            jdsign['sign'].append(ctx.author.id)
            with open('sign_day.json',mode='w',encoding='utf8') as jfile:
                json.dump(jdsign,jfile,indent=4)
            #週常
            with open('sign_week.json','w',encoding='utf8') as jfile:
                jwsign[signer] = jwsign[signer]+1
                json.dump(jwsign,jfile,indent=4)
            
            await ctx.send(f'{ctx.author.mention} 簽到完成!')
            if ctx.guild.id == jdata['001_guild']:
                with open('point.json',mode='w',encoding='utf8') as jfile:
                    jpt[signer] = jpt[signer]+1
                    json.dump(jpt,jfile,indent=4)
                await ctx.send(content=f'{ctx.author.mention} 簽到完成:pt點數+1',delete_after=5)

        else:
            await ctx.send(f'{ctx.author.mention} 已經簽到過了喔')
    
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