import discord
from discord.ext import commands
import json
from core.classes import Cog_Extension

with open('setting.json',mode='r',encoding='utf8') as jfile1:
    jdata = json.load(jfile1)

with open('daysignin.json',mode='r',encoding='utf8') as jfile2:
    jdsign = json.load(jfile2)

with open('weeksignin.json',mode='r',encoding='utf8') as jfile3:
    jwsign2 = json.load(jfile3)

with open('command.json',mode='r',encoding='utf8') as jfile4:
    comdata = json.load(jfile4)

#如果為第一次簽到 就先補0避免keyerror
class Counter(dict):
    def __missing__(self, key): 
        return 0
jwsign = Counter(jwsign2)


class sign(Cog_Extension):
    @commands.command()
    async def sign(self,ctx):
        if ctx.guild.id == int(jdata['main_guild']):
            has = 0 
            for a in jdsign['sign']:
                if int(ctx.author.id) == int(a):
                    has = has+1
           
            if has == 0:
                signer = str(f'{ctx.author.id}')
                #日常
                jdsign['sign'].append(f'{ctx.author.id}')
                with open('daysignin.json',mode='w',encoding='utf8') as jfile:
                    json.dump(jdsign,jfile,indent=4)
                #週常
                with open('weeksignin.json','w+',encoding='utf8') as jfile:
                    jwsign[signer] = jwsign[signer]+1
                    json.dump(jwsign,jfile)
                
                await ctx.send(f'{ctx.author.mention} 簽到完成!')
            
            else:
                await ctx.send(f'{ctx.author.mention} 已經簽到過了喔')             
    
    #@commands.Cog.listener()
    #async def on_voice_state_update(self,user, before, after):
        #guild = after.channel.guild
        #print(user.voice.deaf)

        #jdsign['sign'].append(f'{user.id}')
        #with open('daysignin.json',mode='w',encoding='utf8') as jfile:
        #    json.dump(jdsign,jfile,indent=4)

            #jfile.write(deta)
        #print('4')



def setup(bot):
    bot.add_cog(sign(bot))