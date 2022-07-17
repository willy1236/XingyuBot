import asyncio, datetime,discord,requests
from datetime import datetime, timezone, timedelta,time
from discord.ext import commands,tasks

from cmds.weather import EarthquakeReport,Covid19Report,Forecast
from core.classes import Cog_Extension
from BotLib.database import Database
from BotLib.gamelib import ApexData

class task(Cog_Extension):
    def __init__(self,*args,**kwargs):
        self.jdata = Database().jdata
        super().__init__(*args,**kwargs)
        #await self.bot.wait_until_ready()
    tz = timezone(timedelta(hours=+8))
    
    @commands.Cog.listener()
    async def on_ready(self):
        if self.bot.user.id == 589744540240314368:
            self.sign_reset.start()
            self.earthquake_check.start()
            self.apex_crafting_update.start()
            self.apex_map_update.start()
            self.covid_update.start()
            self.forecast_update.start()
            self.twitch.start()


    def __gettime_15min():
        tz = timezone(timedelta(hours=+8))
        now = datetime.now(tz=tz)
        if now.minute >= 0 and now.minute<15:
            return time(hour=now.hour,minute=15,second=0,tzinfo=tz)
        elif now.minute >= 15 and now.minute <30:
            return time(hour=now.hour,minute=30,second=0,tzinfo=tz)
        elif now.minute >= 30 and now.minute <45:
            return time(hour=now.hour,minute=45,second=0,tzinfo=tz)
        elif now.minute >= 45 and now.minute <60:
            next = now + timedelta(hours=1)
            return time(hour=next.hour,minute=0,second=0,tzinfo=tz)

    def __gettime_3hr():
        tz = timezone(timedelta(hours=+8))
        now = datetime.now(tz=tz)
        next = now + timedelta(hours=3)
        return time(hour=next.hour,minute=0,second=0,tzinfo=tz)
        

    def __gettime_0400():
        tz = timezone(timedelta(hours=+8))
        return time(hour=4,minute=0,second=0,tzinfo=tz)

    def __gettime_0105():
        tz = timezone(timedelta(hours=+8))
        return time(hour=1,minute=5,second=0,tzinfo=tz)

    def __gettime_1430():
        tz = timezone(timedelta(hours=+8))
        now = datetime.now(tz=tz)
        if now.hour == 14 and now.minute >= 30 and now.second < 45:
            return time(hour=14,minute=30,second=0,tzinfo=tz)
        else:
            return time(hour=14,minute=45,second=0,tzinfo=tz)


    
    @commands.command()
    async def task(self,ctx,task_name):
        if task_name == 'apex_map_update' or task_name == 'all':
            await self.apex_map_update.__call__()
            await ctx.message.add_reaction('✅')
        if task_name == 'apex_crafting_update' or task_name == 'all':
            await self.apex_crafting_update.__call__()
            await ctx.message.add_reaction('✅')
        if task_name == 'earthquake_check' or task_name == 'all':
            await self.earthquake_check.__call__()
            await ctx.message.add_reaction('✅')
        if task_name == 'covid_update' or task_name == 'all':
            await self.covid_update.__call__()
            await ctx.message.add_reaction('✅')
        if task_name == 'forecast_update' or task_name == 'all':
            await self.forecast_update.__call__()
            await ctx.message.add_reaction('✅')

    @tasks.loop(time=__gettime_0400())
    async def sign_reset(self):
        task_report_channel = self.bot.get_channel(self.jdata['task_report'])
        reset = []
        Database().write('jdsign',reset)
        await task_report_channel.send('簽到已重置')
        self.sign_reset.stop()

    @sign_reset.after_loop
    async def sign_reset_after(self):
        await asyncio.sleep(10)
        self.sign_reset.start()

    @tasks.loop(minutes=1)
    async def earthquake_check(self):
        db = Database()
        bdata = db.bdata
        timefrom = bdata['timefrom']
        data = EarthquakeReport.get_report_auto(timefrom)
        if data:
            embed = data.desplay
            time = datetime.strptime(data.originTime, "%Y-%m-%d %H:%M:%S")+timedelta(seconds=1)
            bdata['timefrom'] = time.strftime("%Y-%m-%dT%H:%M:%S")
            db.write('bdata',bdata)
            
            ch_list = db.cdata['earthquake']
            for i in ch_list:
                channel = self.bot.get_channel(ch_list[i])
                if channel:
                    await channel.send('地震報告',embed=embed)
                    await asyncio.sleep(0.5)
        
    @tasks.loop(time=__gettime_1430())
    async def covid_update(self):
        cdata = Database().cdata
        embed = Covid19Report.get_covid19().desplay
        for i in cdata["covid_update"]:
            channel = self.bot.get_channel(cdata["covid_update"][i])
            try:
                id = channel.last_message_id
                msg = await channel.fetch_message(id)
            except:
                msg = None

            if msg and msg.author == self.bot.user:
                await msg.edit('Covid 疫情資訊',embed=embed)
            else:
                await channel.send('Covid 疫情資訊',embed=embed)
            await asyncio.sleep(0.5)


    @tasks.loop(time=__gettime_0105())
    async def apex_crafting_update(self):
        cdata = Database().cdata
        crafting = ApexData.get_crafting()
        if crafting:
            for i in cdata["apex_crafting"]:
                channel = self.bot.get_channel(cdata["apex_crafting"][i])
                try:
                    id = channel.last_message_id
                    msg = await channel.fetch_message(id)
                except:
                    msg = None

                if msg and msg.author == self.bot.user:
                    await msg.edit('Apex合成台內容自動更新資料',embed=crafting.desplay)
                else:
                    await channel.send('Apex合成台內容自動更新資料',embed=crafting.desplay)
                await asyncio.sleep(0.5)
        self.apex_crafting_update.stop()

    @apex_crafting_update.after_loop
    async def apex_map_update_after(self):
        await asyncio.sleep(10)
        self.apex_crafting_update.start()

    
    @tasks.loop(time=__gettime_15min())
    async def apex_map_update(self):
        cdata = Database().cdata
        map = ApexData.get_map_rotation()
        if map:
            for i in cdata["apex_map"]:
                channel = self.bot.get_channel(cdata["apex_map"][i])
                try:
                    id = channel.last_message_id
                    msg = await channel.fetch_message(id)
                except:
                    msg = None

                if msg and msg.author == self.bot.user:
                    await msg.edit('Apex地圖輪替自動更新資料',embed=map.desplay)
                else:
                    await channel.send('Apex地圖輪替自動更新資料',embed=map.desplay)
                await asyncio.sleep(0.5)
        self.apex_map_update.change_interval(time=task.__gettime_15min())
        await asyncio.sleep(1)
        #self.apex_map_update.stop()

    @apex_map_update.after_loop
    async def apex_map_update_after(self):
        await asyncio.sleep(10)
        self.apex_map_update.start()
    
    @tasks.loop(time=__gettime_3hr())
    async def forecast_update(self):
        cdata = Database().cdata
        forecast = Forecast.get_report()
        if forecast:
            for i in cdata["forecast"]:
                channel = self.bot.get_channel(cdata["forecast"][i])
                try:
                    id = channel.last_message_id
                    msg = await channel.fetch_message(id)
                except:
                    msg = None

                if msg and msg.author == self.bot.user:
                    await msg.edit('台灣各縣市天氣預報',embed=forecast.desplay)
                else:
                    await channel.send('台灣各縣市天氣預報',embed=forecast.desplay)
                await asyncio.sleep(0.5)
        self.apex_map_update.change_interval(time=task.__gettime_3hr())
        await asyncio.sleep(1)
    
    @tasks.loop(seconds=1)
    async def time_task(self):
        now_time_hour = datetime.now().strftime('%H%M%S')
        #now_time_day = datetime.datetime.now().strftime('%Y%m%d')
    
    @tasks.loop(minutes=1)
    async def twitch(self):
        db = Database()
        id,secret = db.get_token('twitch')
        def get_token():
            APIURL = "https://id.twitch.tv/oauth2/token"
            headers = {"Content-Type": "application/x-www-form-urlencoded"}
            params = {
                'client_id':id,
                'client_secret':secret,
                'grant_type':'client_credentials'
                }
            tokens= requests.post(APIURL, params=params).json()
            return tokens['access_token']

        URL ='https://api.twitch.tv/helix/streams'
        headers = {
            'Authorization': f"Bearer {get_token()}",
            'Client-Id':id
        }
        params = {
            "user_login" : "rainteaorwhatever",
            "first":1
        }
        r= requests.get(URL, params=params,headers=headers).json()
        if r['data']:
            data = r['data'][0]

            time = datetime.strptime(data['started_at'],'%Y-%m-%dT%H:%M:%SZ')
            time = time.strftime('%Y/%m/%d %H:%M:%S')
            embed = discord.Embed(
                title=data['title'],
                url=f"https://www.twitch.tv/{data['user_login']}",
                description=f"{data['game_name']}",
                color=0x6441a5,
                timestamp = datetime.now()
                )
            embed.set_author(name=f"{data['user_name']} 開台啦！")
            thumbnail = data['thumbnail_url']
            thumbnail = thumbnail.replace('{width}','1280')
            thumbnail = thumbnail.replace('{height}','1024')
            embed.set_image(url=thumbnail)
            embed.set_footer(text=f"開始於{time}")
            
            channel = self.bot.get_channel(986230549192519720)
            await channel.send(embed=embed)

def setup(bot):
    bot.add_cog(task(bot))