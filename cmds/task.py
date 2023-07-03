import asyncio,discord,genshin,logging
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timezone, timedelta
from discord.ext import commands,tasks

from core.classes import Cog_Extension
from starcord import Jsondb,sqldb
from starcord.interface import *


apsc_log = logging.getLogger('apscheduler')
formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
consoleHandler = logging.StreamHandler()
consoleHandler.setLevel(logging.WARNING)
consoleHandler.setFormatter(formatter)
apsc_log.addHandler(consoleHandler)

class task(Cog_Extension):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        #await self.bot.wait_until_ready()
    tz = timezone(timedelta(hours=+8))
    
    @commands.Cog.listener()
    async def on_ready(self):
        if self.bot.user.id == 589744540240314368:
            scheduler = AsyncIOScheduler()
            scheduler.add_job(self.sign_reset,'cron',hour=4,minute=0,second=0,jitter=60)
            scheduler.add_job(self.apex_crafting_update,'cron',hour=1,minute=5,second=0,jitter=60)
            scheduler.add_job(self.apex_map_update,'cron',minute='00,15,30,45',second=1,jitter=60)
            scheduler.add_job(self.forecast_update,'cron',hour='00,03,06,09,12,15,18,21',minute=0,second=1,jitter=60)
            scheduler.add_job(self.auto_hoyo_reward,'cron',hour=19,minute=0,second=0,jitter=60)

            scheduler.add_job(self.earthquake_check,'interval',minute=1)

            scheduler.start()
            self.twitch.start()
        if self.bot.user.id == 870923985569861652:
            pass

    async def sign_reset(self):
        task_report_channel = self.bot.get_channel(Jsondb.jdata['task_report'])
        sqldb.truncate_table('user_sign')
        await task_report_channel.send('簽到已重置')

    async def earthquake_check(self):
        timefrom = Jsondb.read_cache('timefrom')
        data = CWBInterface().get_report_auto(timefrom)
        if data:
            embed = data.desplay()
            time = datetime.strptime(data.originTime, "%Y-%m-%d %H:%M:%S")+timedelta(seconds=1)
            Jsondb.write_cache('timefrom',time.strftime("%Y-%m-%dT%H:%M:%S"))

            if data.auto_type == 'E-A0015-001':
                text = '顯著有感地震報告'
            elif data.auto_type == 'E-A0016-001':
                text = '小區域地震報告'
            else:
                text = '地震報告'
            
            records = sqldb.get_notice_channel('earthquake')
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
                else:
                    print(f"earthquake_check: {i['guild_id']}/{i['channel_id']}")
    
    async def covid_update(self):
        CovidReport = Covid19Interface.get_covid19()
        if CovidReport:
            records = sqldb.get_notice_channel('covid_update')
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


    async def apex_crafting_update(self):
        crafting = ApexInterface().get_crafting()
        if crafting:
            records = sqldb.get_notice_channel('apex_crafting')
            for i in records:
                channel = self.bot.get_channel(i['channel_id'])
                if channel:
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
                
                else:
                    print(f"apex_crafting_update: {i['guild_id']}/{i['channel_id']}")

    async def apex_map_update(self):
        map = ApexInterface().get_map_rotation()
        if map:
            records = sqldb.get_notice_channel('apex_map')
            for i in records:
                channel = self.bot.get_channel(i['channel_id'])
                if channel:
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
                
                else:
                    print(f"apex_map_update: {i['guild_id']}/{i['channel_id']}")

    async def forecast_update(self):
        forecast = CWBInterface().get_forecast()
        if forecast:
            records = sqldb.get_notice_channel('forecast')
            for i in records:
                channel = self.bot.get_channel(i['channel_id'])
                if channel:
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
                
                else:
                    print(f"forecast_update: {i['guild_id']}/{i['channel_id']}")

    # @tasks.loop(seconds=1)
    # async def time_task(self):
    #     now_time_hour = datetime.now().strftime('%H%M%S')
    #     #now_time_day = datetime.datetime.now().strftime('%Y%m%d')

    @tasks.loop(minutes=2)
    async def twitch(self):
        users = sqldb.get_notice_community_userlist('twitch')
        if not users:
            return
        twitch_cache = Jsondb.read_cache('twitch')
        data = TwitchAPI().get_lives(users)
        for user in users:
            user_cache = twitch_cache.get(user)
            
            if data[user] and not user_cache:
                twitch_cache[user] = True
                embed = data[user].desplay()
                guilds = sqldb.get_notice_community_guild('twitch',user)
                for guildid in guilds:
                    guild = self.bot.get_guild(guildid)
                    channel = self.bot.get_channel(guilds[guildid][0])
                    role = guild.get_role(guilds[guildid][1])
                    if channel:
                        if role:
                            await channel.send(f'{role.mention} 開台啦~',embed=embed)
                        else:
                            await channel.send(f'開台啦~',embed=embed)
                        await asyncio.sleep(0.5)
                    else:
                        print(f"twitch: {guild.id}/{channel.id}")
            elif not data[user] and user_cache:
                #cache['twitch'][user] = False
                del twitch_cache[user]

        Jsondb.write_cache('twitch',twitch_cache)

    async def auto_hoyo_reward(self):
        list = sqldb.get_hoyo_reward()
        for user in list:
            user_id = user['user_id']
            user_dc = self.bot.get_user(int(user_id))
            channel_id = user['channel_id']
            channel = self.bot.get_channel(int(channel_id))
            cookies = self.sqldb.get_userdata(str(user_id),'game_hoyo_cookies')
            if not channel:
                print(f"auto_hoyo_reward: {user_id}/{channel_id}")
            if not cookies:
                await channel.send(f'{user_dc.mention} 沒有設定cookies或已過期')
            else:
                try:
                    client = genshin.Client(cookies,lang='zh-tw')
                    game = genshin.Game(user['game'])

                    reward = await client.claim_daily_reward(game=game,reward=True)
                    if channel and user['need_mention']:
                        await channel.send(f'{user_dc.mention} 簽到完成！獲得{reward.name}x{reward.amount}')
                    elif channel and not user['need_mention']:
                        await channel.send(f'{user_dc.name} 簽到完成！獲得{reward.name}x{reward.amount}')
                except Exception as e:
                    await channel.send(f'{user_dc.mention} 簽到時發生錯誤：{e}')
            
            await asyncio.sleep(30)

def setup(bot):
    bot.add_cog(task(bot))