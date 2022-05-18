import discord, asyncio, datetime
from datetime import datetime, timezone, timedelta,time
from discord.ext import commands,tasks
from cmds.weather import EarthquakeReport
from core.classes import Cog_Extension
from BotLib.database import Database

class task(Cog_Extension):
    def __init__(self,*args,**kwargs):
        #jevent = Database().jevent
        super().__init__(*args,**kwargs)
        #await self.bot.wait_until_ready()
    tz = timezone(timedelta(hours=+8))
    
    @commands.Cog.listener()
    async def on_ready(self):
        self.sign_reset.start()
        self.earthquake_check.start()
    
    
    @tasks.loop(time=time(hour=00,minute=0,second=0,tzinfo=tz))
    async def sign_reset(self):
        task_report_channel = self.bot.get_channel(self.jdata['task_report'])
        reset = []
        Database().write('jdsign',reset)
        await task_report_channel.send('簽到已重置')

    @tasks.loop(minutes=5)
    async def earthquake_check(self):
        jdata = Database().jdata
        timefrom = jdata['timefrom']
        data = EarthquakeReport.get_report_auto(timefrom)
        if data:
            embed = data.desplay
            time = datetime.strptime(data.originTime, "%Y-%m-%d %H:%M:%S")+timedelta(seconds=1)
            jdata['timefrom'] = time.strftime("%Y-%m-%dT%H:%M:%S")
            Database().write('jdata',jdata)
            
            ch_list = Database().cdata['earthquake']
            for i in ch_list:
                channel = self.bot.get_channel(ch_list[i])
                if channel:
                    await channel.send('地震報告',embed=embed)


    def get_time(tz):
        zt = datetime.now().astimezone(tz)
        zt = zt+timedelta(seconds=20)
        now_time = time(hour=zt.hour, minute=zt.minute, second=zt.second,tzinfo=tz)
        return now_time
    now_time = get_time(tz)

    @tasks.loop(time=now_time)
    async def test_task(self):
        print('task_worked')

    @tasks.loop(seconds=1)
    async def time_task(self):
        now_time_hour = datetime.now().strftime('%H%M%S')
        #now_time_day = datetime.datetime.now().strftime('%Y%m%d')

def setup(bot):
    bot.add_cog(task(bot))