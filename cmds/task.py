import discord
from discord.ext import commands
from core.classes import Cog_Extension
import json, asyncio, datetime

jdata = json.load(open('setting.json',mode='r',encoding='utf8'))

with open('database/event.json',mode='r',encoding='utf8') as jfile:
    jevent = json.load(jfile)

class task(Cog_Extension):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        
        async def time_task():
            await self.bot.wait_until_ready()
            task_report_channel = self.bot.get_channel(jdata['task_report'])
            event_channel = self.bot.get_channel(643764975663448064)
            while not self.bot.is_closed():
                now_time_hour = datetime.datetime.now().strftime('%H%M%S')
                now_time_day = datetime.datetime.now().strftime('%Y%m%d')
                
                if now_time_hour == '040000':
                    with open('database/sign_day.json',mode='w',encoding='utf8') as jfile:
                        reset = []
                        json.dump(reset,jfile,indent=4)

                    await task_report_channel.send('簽到已重置')    
                    await asyncio.sleep(1)

                else:
                    await asyncio.sleep(1)
                    pass
        
        self.bg_task = self.bot.loop.create_task(time_task())

def setup(bot):
    bot.add_cog(task(bot))