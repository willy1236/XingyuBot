import discord
from discord.ext import commands
from core.classes import Cog_Extension
import json, asyncio, datetime

with open('setting.json',mode='r',encoding='utf8') as jfile:
    jdata = json.load(jfile)
with open('event.json',mode='r',encoding='utf8') as jfile:
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
                
                if now_time_hour == jdata['time']:
                    with open('sign_day.json',mode='w',encoding='utf8') as jfile:
                        reset = {"sign":[]}
                        json.dump(reset,jfile,indent=4)

                    await task_report_channel.send('簽到已重置')    
                    await asyncio.sleep(1)
                
                elif now_time_day == '20210821' and now_time_hour == '000000' and jevent['guild_annual'] == 0:
                    with open('event.json','w+',encoding='utf8') as jfile:
                        jevent['guild_annual'] = 1
                        json.dump(jevent,jfile,indent=4)
                    await event_channel.send(jevent['guild_annual_message'])
                    await asyncio.sleep(1)
                
                elif now_time_day == '20210821' and now_time_hour == '070000' and jevent['guild_annual2'] == 0:
                    with open('event.json','w+',encoding='utf8') as jfile:
                        jevent['guild_annual2'] = 1
                        json.dump(jevent,jfile,indent=4)
                    await event_channel.send(jevent['guild_annual_message2'])
                    await asyncio.sleep(1)

                else:
                    await asyncio.sleep(1)
                    pass
        
        self.bg_task = self.bot.loop.create_task(time_task())

def setup(bot):
    bot.add_cog(task(bot))