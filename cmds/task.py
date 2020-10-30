import discord
from discord.ext import commands
import json
from core.classes import Cog_Extension
import json, asyncio, datetime

class task(Cog_Extension):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)

        self.counter = 0

    #    async def interval():
    #        await self.bot.wait_until_ready()
    #        self.channel = self.bot.get_channel(566533708371329026)
    #        while not self.bot.is_closed():
    #            await self.channel.send("Hi I'm running!")
    #            await asyncio.sleep(5) #單位:秒

        async def time_task():
            await self.bot.wait_until_ready()
            self.channel = self.bot.get_channel(566533708371329026)
            while not self.bot.is_closed():
                now_time = datetime.datetime.now().strftime('%H%M%S')
                with open('setting.json',mode='r',encoding='utf8') as jfile:
                    jdata = json.load(jfile)
                if now_time == jdata['time'] and self.counter == 0:
                    await self.channel.send('Task working')
                    self.counter = 1
                    await asyncio.sleep(1)
                else:
                    await asyncio.sleep(1)
                    pass
        
        #self.bg_task = self.bot.loop.create_task(interval())
        self.bg_task = self.bot.loop.create_task(time_task())

    @commands.command()
    async def set_channel(self,ctx,ch:int):
        self.channel = self.bot.get_channel(ch)
        await ctx.send(f'Set Channel:{self.channel.mention}')

    @commands.command()
    async def set_time(self,ctx,time):
        self.counter = 0
        with open('setting.json',mode='r',encoding='utf8') as jfile:
            jdata = json.load(jfile)
        jdata['time'] = time
        with open('setting.json',mode='w',encoding='utf8') as jfile:
            json.dump(jdata,jfile,indent=4)

def setup(bot):
    bot.add_cog(task(bot))