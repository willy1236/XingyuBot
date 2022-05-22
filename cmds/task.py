import discord, asyncio, datetime
from datetime import datetime, timezone, timedelta,time
from discord.ext import commands,tasks
from cmds.weather import EarthquakeReport
from core.classes import Cog_Extension
from BotLib.database import Database
from BotLib.gamedata import ApexData

class task(Cog_Extension):
    def __init__(self,*args,**kwargs):
        #jevent = Database().jevent
        super().__init__(*args,**kwargs)
        #await self.bot.wait_until_ready()
    tz = timezone(timedelta(hours=+8))
    
    @commands.Cog.listener()
    async def on_ready(self):
        if self.bot.user.id == 419131103836635136:
            self.sign_reset.start()
            self.earthquake_check.start()
            self.apex_crafting_update.start()
            self.apex_map_update.start()
            self.restart_all.start()

    @commands.command()
    async def updete_task(self,ctx,task):
        if task == 'apex_map_update':
            await self.apex_map_update.__call__()
            await ctx.message.add_reaction('✅')
        if task == 'apex_crafting_update':
            await self.apex_crafting_update.__call__()
            await ctx.message.add_reaction('✅')
        if task == 'earthquake_check':
            await self.earthquake_check.__call__()
            await ctx.message.add_reaction('✅')

    @tasks.loop(time=time(hour=4, minute=0,second=0,tzinfo=tz))
    async def restart_all(self):
        print("restart")
        self.earthquake_check.restart()
        self.apex_map_update.restart()

    @tasks.loop(time=time(hour=4,minute=0,second=0,tzinfo=tz))
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

    @tasks.loop(time=time(hour=1,minute=5,second=0,tzinfo=tz))
    async def apex_crafting_update(self):
        cdata = Database().cdata
        embed = ApexData.get_crafting().desplay
        for i in cdata["apex_crafting"]:
            channel = self.bot.get_channel(cdata["apex_crafting"][i])
            try:
                id = channel.last_message_id
                msg = await channel.fetch_message(id)
            except:
                msg = None

            if msg and msg.author == self.bot.user:
                await msg.edit('Apex合成台內容自動更新資料',embed=embed)
            else:
                await channel.send('Apex合成台內容自動更新資料',embed=embed)
            await asyncio.sleep(1)
    
    @tasks.loop(minutes=15)
    async def apex_map_update(self):
        cdata = Database().cdata
        embed = ApexData.get_map_rotation().desplay
        for i in cdata["apex_map"]:
            channel = self.bot.get_channel(cdata["apex_map"][i])
            try:
                id = channel.last_message_id
                msg = await channel.fetch_message(id)
            except:
                msg = None

            if msg and msg.author == self.bot.user:
                await msg.edit('Apex地圖輪替自動更新資料',embed=embed)
            else:
                await channel.send('Apex地圖輪替自動更新資料',embed=embed)
            await asyncio.sleep(1)
        

    @tasks.loop(seconds=1)
    async def time_task(self):
        now_time_hour = datetime.now().strftime('%H%M%S')
        #now_time_day = datetime.datetime.now().strftime('%Y%m%d')

def setup(bot):
    bot.add_cog(task(bot))