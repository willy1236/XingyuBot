import asyncio,discord,genshin,logging,random,time
#from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timezone, timedelta,date
from discord.ext import commands,tasks
from requests.exceptions import ConnectTimeout

from starcord import Cog_Extension,Jsondb,sclient,log,BotEmbed
from starcord.DataExtractor import *
from starcord.DataExtractor.community import YoutubeRSS
from starcord.models.community import TwitchVideo, YoutubeVideo

#apsc_log = logging.getLogger('apscheduler')
formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
consoleHandler = logging.StreamHandler()
consoleHandler.setLevel(logging.WARNING)
consoleHandler.setFormatter(formatter)
log.addHandler(consoleHandler)

def slice_list(lst:list[YoutubeVideo], target_id):
    """以target_id為基準取出更新的影片資訊"""
    index = next((i for i, d in enumerate(lst) if d.updated_at > target_id), None)
    return lst[index:] if index else lst

def slice_list_twitch(lst:list[TwitchVideo], target_id:datetime):
    """以target_id為基準取出更新的影片資訊"""
    index = next((i for i, d in enumerate(lst) if d.created_at > target_id), None)
    return lst[index:] if index else lst

class task(Cog_Extension):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        #await self.bot.wait_until_ready()
    tz = timezone(timedelta(hours=8))
    
    @commands.Cog.listener()
    async def on_ready(self):
        if not Jsondb.jdata.get("debug_mode",True):
            global scheduler
            scheduler = AsyncIOScheduler()
            scheduler.add_job(self.apex_info_update,'cron',minute='00,15,30,45',second=1,jitter=30,misfire_grace_time=60)
            scheduler.add_job(self.apex_crafting_update,'cron',hour=1,minute=5,second=0,jitter=30,misfire_grace_time=60)
            scheduler.add_job(self.forecast_update,'cron',hour='00,03,06,09,12,15,18,21',minute=0,second=1,jitter=30,misfire_grace_time=60)
            #scheduler.add_job(self.auto_hoyo_reward,'cron',hour=19,minute=0,second=0,jitter=30,misfire_grace_time=60)
            #scheduler.add_job(self.update_rpgshop_data,'cron',hour=0,minute=0,second=1,jitter=30,misfire_grace_time=60)
            
            #scheduler.add_job(self.update_channel_dict,'cron',hour='*',minute="0,30",second=0,jitter=30,misfire_grace_time=60)

            scheduler.add_job(self.earthquake_check,'interval',minutes=2,jitter=30,misfire_grace_time=40)
            scheduler.add_job(self.youtube_video,'interval',minutes=15,jitter=30,misfire_grace_time=40)
            scheduler.add_job(self.twitch_video,'interval',minutes=15,jitter=30,misfire_grace_time=40)
            #scheduler.add_job(self.city_battle,'interval',minutes=1,jitter=30,misfire_grace_time=60)
            #scheduler.add_job(self.get_mongodb_data,'interval',minutes=3,jitter=30,misfire_grace_time=40)

            scheduler.add_job(sclient.init_NoticeClient,"date")

            scheduler.start()
            self.twitch.start()
        else:
            pass

    async def earthquake_check(self):
        timefrom = Jsondb.read_cache('earthquake_timefrom')
        try:
            data = CWA_API().get_earthquake_report_auto(timefrom)
        except ConnectTimeout:
            log.warning("earthquake_check timeout.")
            return
        except:
            return
        
        if data:
            embed = data.desplay()
            time = datetime.strptime(data.originTime, "%Y-%m-%d %H:%M:%S")+timedelta(seconds=1)
            Jsondb.write_cache('earthquake_timefrom',time.strftime("%Y-%m-%dT%H:%M:%S"))

            if data.auto_type == 'E-A0015-001':
                text = '顯著有感地震報告'
            elif data.auto_type == 'E-A0016-001':
                text = '小區域地震報告'
            else:
                text = '地震報告'
            
            records = sclient.get_notify_channel_by_type('earthquake')
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
                    log.warning(f"earthquake_check: {i['guild_id']}/{i['channel_id']}")

    async def weather_warning_check(self):
        timefrom = Jsondb.read_cache('earthquake_timefrom')
        try:
            data = CWA_API().get_earthquake_report_auto(timefrom)
        except:
            pass

    async def apex_info_update(self):
        aclient = ApexInterface()
        map = aclient.get_map_rotation()
        crafting = aclient.get_crafting_from_chche()
        if map:
            embed_list = []
            if crafting:
                embed_list.append(crafting.desplay())
            embed_list.append(map.desplay())
            
            records = sclient.get_notify_channel_by_type('apex_info')
            for i in records:
                channel = self.bot.get_channel(i['channel_id'])
                if channel:
                    try:
                        id = channel.last_message_id
                        msg = await channel.fetch_message(id)
                    except:
                        msg = None

                    if msg and msg.author == self.bot.user:
                        await msg.edit('Apex資訊自動更新資料',embeds=embed_list)
                    else:
                        await channel.send('Apex資訊內容自動更新資料',embeds=embed_list)
                    await asyncio.sleep(0.5)
                
                else:
                    log.warning(f"apex_info_update: {i['guild_id']}/{i['channel_id']}")

    async def apex_crafting_update(self):
        today = date.today()
        apex_crafting = Jsondb.read_cache("apex_crafting")
        if not apex_crafting or apex_crafting.get("date") != today.isoformat():
            apex_crafting = ApexInterface().get_raw_crafting()
            apex_crafting_dict = {
                "date": today.isoformat(),
                "data": apex_crafting[0:2]
            }
            Jsondb.write_cache("apex_crafting",apex_crafting_dict)


    async def forecast_update(self):
        forecast = CWA_API().get_forecast()
        if forecast:
            records = sclient.get_notify_channel_by_type('forecast')
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
                    log.warning(f"forecast_update: {i['guild_id']}/{i['channel_id']}")

    @tasks.loop(minutes=3)
    async def twitch(self):
        users = sclient.get_notice_dict("twitch")
        if not users:
            return
        twitch_cache = Jsondb.read_cache('twitch') or {}
        data = TwitchAPI().get_lives(users)
        for user in users:
            user_cache = twitch_cache.get(user)
            
            if data[user] and not user_cache:
                twitch_cache[user] = True
                embed = data[user].embed()
                guilds = sclient.get_notify_community_guild('twitch',user)
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

    async def twitch_video(self):
        users = sclient.get_notice_dict("twitch_v")
        if not users:
            return
        twitch_cache = Jsondb.read_cache('twitch_v') or {}
        for user in users:
            videos = TwitchAPI().get_videos(user)
            cache_last_update_time = datetime.fromisoformat(twitch_cache.get(user)) if twitch_cache.get(user) else None
            if not cache_last_update_time or videos[0].created_at > cache_last_update_time:
                videos.reverse()
                video_list = slice_list_twitch(videos, cache_last_update_time)
                twitch_cache[user] = video_list[-1].created_at.isoformat()

                for data in video_list:
                    embed = data.embed()
                    guilds = sclient.get_notify_community_guild('twitch_v',data.user_id)
                    for guildid in guilds:
                        guild = self.bot.get_guild(guildid)
                        channel = self.bot.get_channel(guilds[guildid][0])
                        role = guild.get_role(guilds[guildid][1])
                        if channel:
                            if role:
                                await channel.send(f'{role.mention} 新影片上傳啦~',embed=embed)
                            else:
                                await channel.send(f'新影片上傳啦~',embed=embed)
                            await asyncio.sleep(0.5)
                        else:
                            log.warning(f"twitch_v: {guild.id}/{channel.id}")

        Jsondb.write_cache('twitch_v',twitch_cache)

    async def youtube_video(self):
        ytchannels = sclient.get_notice_dict("youtube")
        if not ytchannels:
            return
        cache_youtube = Jsondb.read_cache('youtube') or {}
        rss = YoutubeRSS()
        for ytchannel_id in ytchannels:
            #抓取資料
            rss_data = rss.get_videos(ytchannel_id)
            if not rss_data:
                continue
            cache_last_update_time = datetime.fromisoformat(cache_youtube.get(ytchannel_id)) if cache_youtube.get(ytchannel_id) else None
            
            #判斷是否有更新
            if not cache_last_update_time or cache_last_update_time > rss_data[0].updated_at:
                #整理影片列表&儲存最後更新時間
                rss_data.reverse()
                video_list = slice_list(rss_data, cache_last_update_time)
                cache_youtube[ytchannel_id] = rss_data[-1].updated_at.isoformat()

                #發布通知
                for video in video_list:
                    embed = video.embed()
                    guilds = sclient.get_notify_community_guild('youtube',ytchannel_id)
                    for guildid in guilds:
                        guild = self.bot.get_guild(guildid)
                        channel = self.bot.get_channel(guilds[guildid][0])
                        role = guild.get_role(guilds[guildid][1])
                        text = "新影片上傳啦~" if video.uplood_at == video.updated_at else "影片更新啦~"
                        if channel:
                            if role:
                                await channel.send(f'{role.mention} {text}',embed=embed)
                            else:
                                await channel.send(f'{text}',embed=embed)
                            await asyncio.sleep(0.5)
                        else:
                            log.warning(f"youtube: {guild.id}/{channel.id}")

        Jsondb.write_cache('youtube',cache_youtube)

    async def auto_hoyo_reward(self):
        list = sclient.get_hoyo_reward()
        for user in list:
            user_id = user['user_id']
            user_dc = self.bot.get_user(int(user_id))
            channel_id = user['channel_id']
            channel = self.bot.get_channel(int(channel_id))
            cookies = sclient.get_userdata(user_id,'game_hoyo_cookies')
            if not channel:
                log.warning(f"auto_hoyo_reward: {user_id}/{channel_id}")
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

    # async def get_mongodb_data(self):
    #     dbdata = mongedb.get_apidata()

    async def update_pubsubhubbub_data(self):
        pass

    async def update_rpgshop_data(self):
        log.info("update_rpgshop_data start")
        sclient.rpg_shop_daily()

    async def city_battle(self):
        log.info("city_battle start")
        city_battle_list = sclient.get_all_city_battle()
        if not city_battle_list:
            return
        
        for city_battle in city_battle_list:    
            if city_battle.defencer:
                if not city_battle.attacker:
                    return
                
                for defencer in city_battle.defencer:
                    player_def = sclient.get_rpguser(defencer.discord_id,user_dc=self.bot.get_user(defencer.discord_id))
                    if city_battle.attacker:
                        attacker = random.choice(city_battle.attacker)
                        player_atk = sclient.get_rpguser(attacker.discord_id,user_dc=self.bot.get_user(attacker.discord_id))
                        
                        embed = BotEmbed.rpg(f"在 {city_battle.city.city_name} 的占領戰\n",f"攻擊者 {player_atk.name} 對 防守者{player_def.name}\n")
                        text, participants = player_def.battle_with(player_atk)
                        embed.description += text

                        if participants[0] == player_def:
                            city_battle.attacker.remove(attacker)
                        embed.description += f"\n剩餘 {len(city_battle.attacker)} 位攻擊者"
                        await self.bot.get_channel(1181201785055096842).send(embed=embed)

            else:
                embed = BotEmbed.rpg(f"在 {city_battle.city.city_name} 的占領戰\n",f"佔領值 +{len(city_battle.attacker)}")
                await self.bot.get_channel(1181201785055096842).send(embed=embed)
        
        log.info("city_battle end")


def setup(bot):
    bot.add_cog(task(bot))