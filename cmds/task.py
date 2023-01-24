import asyncio,discord,schedule
from datetime import datetime, timezone, timedelta,time
from discord.ext import commands,tasks
from threading import Thread

from core.classes import Cog_Extension
import bothelper
from bothelper.interface.weather import *
from bothelper.interface.game import ApexInterface
from bothelper.interface.community import Twitch

class task(Cog_Extension):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        #await self.bot.wait_until_ready()
    tz = timezone(timedelta(hours=+8))
    
    @commands.Cog.listener()
    async def on_ready(self):
        if self.bot.user.id == 589744540240314368:
            self.task_timer.start()
            self.earthquake_check.start()
            self.twitch.start()
        if self.bot.user.id == 870923985569861652:
            pass

    # @commands.command()
    # async def task(self,ctx,task_name):
    #     if task_name == 'apex_map_update' or task_name == 'all':
    #         await self.apex_map_update.__call__()
    #         await ctx.message.add_reaction('✅')
    #     if task_name == 'apex_crafting_update' or task_name == 'all':
    #         await self.apex_crafting_update.__call__()
    #         await ctx.message.add_reaction('✅')
    #     if task_name == 'earthquake_check' or task_name == 'all':
    #         await self.earthquake_check.__call__()
    #         await ctx.message.add_reaction('✅')
    #     if task_name == 'covid_update' or task_name == 'all':
    #         await self.covid_update.__call__()
    #         await ctx.message.add_reaction('✅')
    #     if task_name == 'forecast_update' or task_name == 'all':
    #         await self.forecast_update.__call__()
    #         await ctx.message.add_reaction('✅')
    
    @tasks.loop(seconds=1)
    async def task_timer(self):
        schedule.run_pending()
    
    @schedule.repeat(schedule.every().day.at("04:00"))
    async def sign_reset(self):
        db = bothelper.Jsondb
        task_report_channel = self.bot.get_channel(db.jdata['task_report'])
        self.sqldb.truncate_table('user_sign')
        await task_report_channel.send('簽到已重置')
        await asyncio.sleep(10)

    @tasks.loop(minutes=1)
    async def earthquake_check(self):
        db = bothelper.Jsondb
        cache = db.cache
        timefrom = cache['timefrom']
        data = CWBInterface().get_report_auto(timefrom)
        if data:
            embed = data.desplay()
            time = datetime.datetime.strptime(data.originTime, "%Y-%m-%d %H:%M:%S")+timedelta(seconds=1)
            cache['timefrom'] = time.strftime("%Y-%m-%dT%H:%M:%S")
            db.write('cache',cache)

            if data.auto_type == 'E-A0015-001':
                text = '顯著有感地震報告'
            elif data.auto_type == 'E-A0016-001':
                text = '小區域地震報告'
            else:
                text = '地震報告'
            
            records = self.sqldb.get_notice_channel('earthquake')
            for i in records:
                channel = self.bot.get_channel(i['channel_id'])
                if channel:
                    if i.get('role_id'):
                        try:
                            role = self.bot.get_guild(i['guild_id']).get_role(i['role_id'])
                            text += f' {role.mention}'
                        except:
                            pass
                    await channel.send(text,embed=embed)
                    await asyncio.sleep(0.5)

    @schedule.repeat(schedule.every().day.at("14:30"))
    async def covid_update(self):
        CovidReport = Covid19Interface.get_covid19()
        if CovidReport:
            records = self.sqldb.get_notice_channel('covid_update')
            for i in records:
                channel = self.bot.get_channel(i["channel_id"])
                try:
                    id = channel.last_message_id
                    msg = await channel.fetch_message(id)
                except:
                    msg = None

                if msg and msg.author == self.bot.user:
                    await msg.edit('Covid 疫情資訊',embed=CovidReport.desplay())
                else:
                    await channel.send('Covid 疫情資訊',embed=CovidReport.desplay())
                await asyncio.sleep(0.5)
        await asyncio.sleep(10)

    @schedule.repeat(schedule.every().day.at("01:05"))
    async def apex_crafting_update(self):
        crafting = ApexInterface().get_crafting()
        if crafting:
            records = self.sqldb.get_notice_channel('apex_crafting')
            for i in records:
                channel = self.bot.get_channel(i['channel_id'])
                try:
                    id = channel.last_message_id
                    msg = await channel.fetch_message(id)
                except:
                    msg = None

                if msg and msg.author == self.bot.user:
                    await msg.edit('Apex合成台內容自動更新資料',embed=crafting.desplay())
                else:
                    await channel.send('Apex合成台內容自動更新資料',embed=crafting.desplay())
                await asyncio.sleep(0.5)
        await asyncio.sleep(10)
        self.apex_crafting_update.stop()

    @schedule.repeat(schedule.every().hours.at("00:00"))
    @schedule.repeat(schedule.every().hours.at("15:00"))
    @schedule.repeat(schedule.every().hours.at("30:00"))
    @schedule.repeat(schedule.every().hours.at("45:00"))
    async def apex_map_update(self):
        print(1)
        map = ApexInterface().get_map_rotation()
        if map:
            records = self.sqldb.get_notice_channel('apex_map')
            for i in records:
                channel = self.bot.get_channel(i['channel_id'])
                try:
                    id = channel.last_message_id
                    msg = await channel.fetch_message(id)
                except:
                    msg = None

                if msg and msg.author == self.bot.user:
                    await msg.edit('Apex地圖輪替自動更新資料',embed=map.desplay())
                else:
                    await channel.send('Apex地圖輪替自動更新資料',embed=map.desplay())
                await asyncio.sleep(0.5)
        self.apex_map_update.change_interval(time=task.__gettime_15min())
        await asyncio.sleep(10)
    
    @schedule.repeat(schedule.every(3).hours.at("00:00"))
    async def forecast_update(self):
        forecast = CWBInterface().get_forecast()
        if forecast:
            records = self.sqldb.get_notice_channel('forecast')
            for i in records:
                channel = self.bot.get_channel(i['channel_id'])
                try:
                    id = channel.last_message_id
                    msg = await channel.fetch_message(id)
                except:
                    msg = None

                if msg and msg.author == self.bot.user:
                    await msg.edit('台灣各縣市天氣預報',embed=forecast.desplay())
                else:
                    await channel.send('台灣各縣市天氣預報',embed=forecast.desplay())
                await asyncio.sleep(0.5)
        self.forecast_update.change_interval(time=task.__gettime_3hr())
        await asyncio.sleep(10)
    
    # @tasks.loop(seconds=1)
    # async def time_task(self):
    #     now_time_hour = datetime.now().strftime('%H%M%S')
    #     #now_time_day = datetime.datetime.now().strftime('%Y%m%d')
    
    @tasks.loop(minutes=2)
    async def twitch(self):
        db = bothelper.Jsondb
        cache = db.cache
        users = self.sqldb.get_notice_community_userlist('twitch')
        if not users:
            return
        
        data = Twitch().get_lives(users)
        for username in data:
            if data[username] and not cache['twitch'].get(username,False):
                cache['twitch'][username] = True
                embed = data[username]
                guilds = self.sqldb.get_notice_community_guild('twitch',username)
                for guild in guilds:
                    guild = self.bot.get_guild(guild)
                    channel = self.bot.get_channel(guilds['guild'][0])
                    role = guild.get_role(guilds['guild'][1])
                    if channel:
                        await channel.send(f'{role.mention or None} 開台啦~',embed=embed)
                    await asyncio.sleep(1)
            elif not data[username] and cache['twitch'].get(username,False):
                cache['twitch'][username] = False
            
        db.write('cache',cache)

def setup(bot):
    bot.add_cog(task(bot))