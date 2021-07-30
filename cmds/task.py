import discord
from discord.ext import commands
from core.classes import Cog_Extension
import json, asyncio, datetime

class task(Cog_Extension):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)

        async def time_task():
            await self.bot.wait_until_ready()
            while not self.bot.is_closed():
                now_time = datetime.datetime.now().strftime('%H%M%S')
                with open('setting.json',mode='r',encoding='utf8') as jfile:
                    jdata = json.load(jfile)
                
                if now_time == jdata['time']:
                    with open('daysignin.json',mode='w',encoding='utf8') as jfile2:
                        jdsign = {"sign":[]}
                        json.dump(jdsign,jfile2,indent=4)
                    
                    await asyncio.sleep(1)
                else:
                    await asyncio.sleep(1)
                    pass
        
        self.bg_task = self.bot.loop.create_task(time_task())

def setup(bot):
    bot.add_cog(task(bot))