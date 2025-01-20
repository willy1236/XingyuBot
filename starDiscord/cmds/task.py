import asyncio
import random
from datetime import date, datetime, timedelta, timezone

import discord
from discord.ext import commands, tasks
from requests.exceptions import ConnectTimeout, RequestException
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from starlib import BotEmbed, Jsondb, log, sclient, tz, utils
from starlib.dataExtractor import *
from starlib.types import NotifyChannelType, NotifyCommunityType, JsonCacheType

from ..extension import Cog_Extension

rss = YoutubeRSS()
ytapi = YoutubeAPI()
twapi = TwitchAPI()
cwa_api = CWA_API()
apexapi = ApexAPI()

class task(Cog_Extension):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        #await self.bot.wait_until_ready()
    
    @commands.Cog.listener()
    async def on_ready(self):
        scheduler = AsyncIOScheduler()
        if not Jsondb.config.get("debug_mode",True):
            scheduler.add_job(self.forecast_update,'cron',hour='0/3',minute=0,second=1,jitter=30,misfire_grace_time=60)
            scheduler.add_job(self.weather_check,'cron',minute='20,35',second=30,jitter=30,misfire_grace_time=60)
            scheduler.add_job(self.apex_map_rotation,'cron',minute='0/15',second=10,jitter=30,misfire_grace_time=60)
            scheduler.add_job(self.refresh_yt_push,'cron',hour="2/6",jitter=30,misfire_grace_time=40)

            scheduler.add_job(self.earthquake_check,'interval',minutes=2,jitter=30,misfire_grace_time=40)
            scheduler.add_job(self.weather_warning_check,'interval',minutes=15,jitter=30,misfire_grace_time=40)
            scheduler.add_job(self.youtube_video,'interval',minutes=15,jitter=30,misfire_grace_time=40)
            scheduler.add_job(self.twitch_live,'interval',minutes=4,jitter=15,misfire_grace_time=20)
            scheduler.add_job(self.twitch_video,'interval',minutes=15,jitter=30,misfire_grace_time=40)
            scheduler.add_job(self.twitch_clip,'interval',minutes=10,jitter=30,misfire_grace_time=40)
            #scheduler.add_job(self.get_mongodb_data,'interval',minutes=3,jitter=30,misfire_grace_time=40)

            if self.bot.user.id == 589744540240314368:
                scheduler.add_job(self.birtday_task,'cron',month=10,day=16,hour=8,minute=0,second=0,jitter=30,misfire_grace_time=60)
                scheduler.add_job(self.new_years_eve_task, CronTrigger(month=1, day=1, hour=0, minute=0, second=0), misfire_grace_time=60)
        else:
            pass
        
        if not scheduler.running:
            scheduler.start()

    async def earthquake_check(self):
        timefrom = Jsondb.get_cache(JsonCacheType.EarthquakeTimeFrom)
        try:
            earthquake_records = cwa_api.get_earthquake_report_auto(timefrom, True)
        except ConnectTimeout:
            log.warning("earthquake_check timeout.")
            return
        except Exception as e:
            log.error(f"earthquake_check error: {e}")
            return
        
        if not earthquake_records:
            return

        for data in earthquake_records:
            if data.is_significant:
                await self.bot.send_notify_channel(data.embed(), NotifyChannelType.MajorQuakeNotifications, "顯著有感地震報告")
            else:
                await self.bot.send_notify_channel(data.embed(), NotifyChannelType.SlightQuakeNotifications, "小區域地震報告")
        
        timefrom = earthquake_records[-1].originTime + timedelta(seconds=1)
        Jsondb.write_cache(JsonCacheType.EarthquakeTimeFrom, timefrom.strftime("%Y-%m-%dT%H:%M:%S"))

    async def weather_check(self):
        weather = cwa_api.get_weather_data()[0]
        text = f"現在天氣： {weather.WeatherElement.Weather if weather.WeatherElement.Weather != '-99' else '--'}/{weather.WeatherElement.AirTemperature}°C"
        if weather.WeatherElement.AirTemperature == weather.WeatherElement.DailyExtreme.DailyHigh.AirTemperature:
            text += f" （最高溫）"
        elif weather.WeatherElement.AirTemperature == weather.WeatherElement.DailyExtreme.DailyLow.AirTemperature:
            text += f" （最低溫）"
        await self.bot.change_presence(activity=discord.CustomActivity(name=text))

    async def weather_warning_check(self):
        apidatas = cwa_api.get_weather_warning()
        if not apidatas:
            return
        
        timefrom = Jsondb.get_cache(JsonCacheType.WeatherWarning)
        report_time = datetime.fromisoformat(timefrom) if timefrom else datetime.now(tz) - timedelta(days=1)
        datas = [i for i in apidatas if i.datasetInfo.issueTime > report_time]
        for data in datas:
            report_time = data.datasetInfo.issueTime
            await self.bot.send_notify_channel(data.embed(), NotifyChannelType.WeatherWarning)
        Jsondb.write_cache(JsonCacheType.WeatherWarning, report_time.isoformat())

    async def forecast_update(self):
        forecast = cwa_api.get_forecast()
        if forecast:
            await self.bot.edit_notify_channel(forecast.embed(), NotifyChannelType.WeatherForecast, "6小時天氣預報")

    async def apex_map_rotation(self):
        try:
            data = apexapi.get_map_rotation()
            if data:
                await self.bot.edit_notify_channel(data.embeds(), NotifyChannelType.ApexRotation)
        except RequestException:
            log.warning("連線失敗", exc_info=True)

    #@tasks.loop(minutes=3)
    async def twitch_live(self):
        log.debug("twitch_live start")
        users = sclient.dbcache[NotifyCommunityType.TwitchLive]
        if not users:
            return
        twitch_cache = Jsondb.get_cache(JsonCacheType.TwitchLive) or {}
        data = twapi.get_lives(users)
        log.debug(f"twitch_live data: {data}")
        for user in users:
            user_cache = twitch_cache.get(user)
            
            if data[user] and not user_cache:
                twitch_cache[user] = True
                embed = data[user].embed()
                await self.bot.send_notify_communities(embed, NotifyCommunityType.TwitchLive, user)

            elif not data[user] and user_cache:
                del twitch_cache[user]

        Jsondb.write_cache(JsonCacheType.TwitchLive, twitch_cache)

    async def twitch_video(self):
        users = sclient.dbcache[NotifyCommunityType.TwitchVideo]
        if not users:
            return
        twitch_cache = Jsondb.get_cache(JsonCacheType.TwitchVideo) or {}
        for user in users:
            videos = twapi.get_videos(user)
            cache_last_update_time = datetime.fromisoformat(twitch_cache.get(user)).replace(tzinfo=tz) if twitch_cache.get(user) else None
            if not cache_last_update_time or videos[0].created_at > cache_last_update_time:
                videos.reverse()
                video_list = [d for d in videos if d.created_at > cache_last_update_time]
                twitch_cache[user] = video_list[-1].created_at.isoformat()

                for data in video_list:
                    embed = data.embed()
                    await self.bot.send_notify_communities(embed, NotifyCommunityType.TwitchVideo, data.user_id)

        Jsondb.write_cache(JsonCacheType.TwitchVideo,twitch_cache)

    async def twitch_clip(self):
        users = sclient.dbcache[NotifyCommunityType.TwitchClip]
        if not users:
            return
        twitch_cache = Jsondb.get_cache(JsonCacheType.TwitchClip) or {}
        for user in users:
            cache_last_update_time = datetime.fromisoformat(twitch_cache.get(user)).replace(tzinfo=tz) if twitch_cache.get(user) else None
            clips = twapi.get_clips(user, started_at=cache_last_update_time)
            if clips:
                newest = clips[0].created_at
                broadcaster_id = clips[0].broadcaster_id
                
                videos_dict = {clip.video_id: None for clip in clips}
                api_video = twapi.get_videos(ids=list(videos_dict.keys()))
                videos_dict = {video.id: video for video in api_video}

                for clip in clips:
                    video = videos_dict[video.id]
                    newest = clip.created_at if clip.created_at > newest else newest
                    if clip.title != video.title:
                        embed = clip.embed(video)
                        await self.bot.send_notify_communities(embed, NotifyCommunityType.TwitchClip, broadcaster_id)

                twitch_cache[broadcaster_id] = (newest + timedelta(seconds=1)).isoformat()

        Jsondb.write_cache(JsonCacheType.TwitchClip,twitch_cache)

    async def youtube_video(self):
        ytchannels = sclient.dbcache[NotifyCommunityType.Youtube]
        if not ytchannels:
            return
        cache_youtube = Jsondb.get_cache(JsonCacheType.YoutubeVideo) or {}
        for ytchannel_id in ytchannels:
            #抓取資料
            rss_data = rss.get_videos(ytchannel_id)
            if not rss_data:
                continue
            cache_last_update_time_str = cache_youtube.get(ytchannel_id)
            cache_last_update_time = datetime.fromisoformat(cache_last_update_time_str) if cache_last_update_time_str else None
            #判斷是否有更新
            if not cache_last_update_time or rss_data[0].uplood_at > cache_last_update_time:
                #整理影片列表&儲存最後更新時間
                rss_data.reverse()
                video_id_list = [d.yt_videoid for d in rss_data if d.uplood_at > cache_last_update_time]
                cache_youtube[ytchannel_id] = rss_data[-1].uplood_at.isoformat()

                api_videos = ytapi.get_video(video_id_list)
                #發布通知
                for video in api_videos:
                    embed = video.embed()
                    await self.bot.send_notify_communities(embed, NotifyCommunityType.Youtube, ytchannel_id)

        Jsondb.write_cache(JsonCacheType.YoutubeVideo,cache_youtube)

    # async def get_mongodb_data(self):
    #     dbdata = mongedb.get_apidata()

    async def update_pubsubhubbub_data(self):
        pass

    async def city_battle(self):
        log.info("city_battle start")
        city_battle_list = sclient.sqldb.get_all_city_battle()
        if not city_battle_list:
            return
        
        for city_battle in city_battle_list:    
            if city_battle.defencer:
                if not city_battle.attacker:
                    return
                
                for defencer in city_battle.defencer:
                    player_def = sclient.sqldb.get_rpguser(defencer.discord_id,user_dc=self.bot.get_user(defencer.discord_id))
                    if city_battle.attacker:
                        attacker = random.choice(city_battle.attacker)
                        player_atk = sclient.sqldb.get_rpguser(attacker.discord_id,user_dc=self.bot.get_user(attacker.discord_id))
                        
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

    async def start_eletion(self):
        log.info("start_eletion start")
        session = utils.calculate_eletion_session(datetime.now())
        channel = self.bot.get_channel(1163127708839071827)

        embed = sclient.election_format(session,self.bot)
        await channel.send(embed=embed)

        dbdata = sclient.sqldb.get_election_full_by_session(session)
        results = {}
        for position in Jsondb.options["position_option"].keys():
            results[position] = []
        
        for data in dbdata:
            user_id = data['discord_id']
            #party_name = i['party_name'] or "無黨籍"
            position = data['position']
            
            user = channel.guild.get_member(user_id)
            username = user_id if not user else (user.display_name if user.display_name else (user.global_name if user.global_name else user.name))
            if username not in results[position]:
                results[position].append(username)

        # count_data = sclient.get_election_count(session)
        # count_dict = {}
        # for data in count_data:
        #     pos = data['position']
        #     count = data['count']
        #     count_dict[pos] = count

        for position in Jsondb.options["position_option"].keys():
            #count = count_dict[position]
            if len(results[position]) <= 0:
                continue

            position_name = Jsondb.get_tw(position, "position_option")
            title = f"第{session}屆中央選舉：{position_name}"
            #options = [f"{i}號" for i in range(1,count + 1)]
            i = 1
            options = []
            for username in results[position]:
                options.append(f"{i}號 {username}" )
                i += 1

            view = sclient.create_election_poll(title, options, self.bot.user.id, channel.guild.id, self.bot)

            message = await channel.send(embed=view.embed(channel.guild),view=view)
            await asyncio.sleep(1)
    
        await channel.send(f"第{session}屆中央選舉投票已開始，請大家把握時間踴躍投票!")

        tz = timezone(timedelta(hours=8))
        start_time = datetime.now(tz)
        if start_time.hour < 20:
            end_time = datetime(start_time.year,start_time.month,start_time.day,20,0,0,tzinfo=tz)
        else:
            end_time = start_time + timedelta(days=1)
        
        start_time += timedelta(seconds=10)
        event = await channel.guild.create_scheduled_event(name="【快樂營中央選舉】投票階段",start_time=start_time,end_time=end_time,location="<#1163127708839071827>")
        
    async def birtday_task(self):
        channel = self.bot.get_channel(566533708371329026)
        await channel.send("今天是個特別的日子，別忘記了喔⭐")

    async def new_years_eve_task(self):
        channel = self.bot.get_channel(643764975663448064)
        msg = await channel.send("新的一年 祝大家新年快樂~🎉\n來自快樂營的2025新年轟炸 @everyone ", allowed_mentions=discord.AllowedMentions(everyone=True))
        await msg.add_reaction("🎉")

    async def refresh_yt_push(self):
        push = YoutubePush()
        records = sclient.sqldb.get_expired_push_records()
        callback_url = Jsondb.get_token("youtube_push")
        for record in records:
            push.add_push(record.channel_id, callback_url)
            await asyncio.sleep(3)
            data = push.get_push(record.channel_id, callback_url)

            record.push_at = data.last_successful_verification
            record.expire_at = data.expiration_time
            sclient.sqldb.merge(record)
            await asyncio.sleep(1)


def setup(bot):
    bot.add_cog(task(bot))