import asyncio
import subprocess
from datetime import datetime, timedelta, timezone

import discord
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from discord.ext import commands, tasks
from requests.exceptions import ConnectTimeout, RequestException

from starlib import BotEmbed, Jsondb, log, sclient, tz, utils, sqldb
from starlib.instance import *
from starlib.models.community import YoutubeVideo
from starlib.types import NotifyChannelType, NotifyCommunityType, APIType

from ..extension import Cog_Extension
from ..uiElement.view import GiveawayView

scheduler = AsyncIOScheduler()

class task(Cog_Extension):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        #await self.bot.wait_until_ready()
    
    @commands.Cog.listener()
    async def on_ready(self):
        if not Jsondb.config.get("debug_mode",True):
            scheduler.add_job(self.forecast_update,'cron',hour='0/3',minute=0,second=1,jitter=30,misfire_grace_time=60)
            scheduler.add_job(self.weather_check,'cron',minute='20,35',second=30,jitter=30,misfire_grace_time=60)
            scheduler.add_job(self.apex_map_rotation,'cron',minute='0/15',second=10,jitter=30,misfire_grace_time=60)
            scheduler.add_job(self.refresh_yt_push,'cron',hour="2/3",jitter=30,misfire_grace_time=40)

            scheduler.add_job(self.earthquake_check,'interval',minutes=3,jitter=30,misfire_grace_time=40)
            scheduler.add_job(self.weather_warning_check,'interval',minutes=15,jitter=30,misfire_grace_time=40)
            scheduler.add_job(self.youtube_video,'interval',minutes=15,jitter=30,misfire_grace_time=40)
            scheduler.add_job(self.twitch_live,'interval',minutes=4,jitter=15,misfire_grace_time=20)
            scheduler.add_job(self.twitch_video,'interval',minutes=15,jitter=30,misfire_grace_time=40)
            scheduler.add_job(self.twitch_clip,'interval',minutes=10,jitter=30,misfire_grace_time=40)
            scheduler.add_job(self.twitter_tweets_rss,'interval',minutes=15, jitter=30, misfire_grace_time=40)
            #scheduler.add_job(self.get_mongodb_data,'interval',minutes=3,jitter=30,misfire_grace_time=40)

            if self.bot.user.id == 589744540240314368:
                scheduler.add_job(self.birtday_task,'cron',month=10,day=16,hour=8,minute=0,second=0,jitter=30,misfire_grace_time=60)
                # scheduler.add_job(self.new_years_eve_task, CronTrigger(month=1, day=1, hour=0, minute=0, second=0), misfire_grace_time=60)
        
        # 抽獎
        now = datetime.now(tz)
        for giveaway in sclient.sqldb.get_active_giveaways():
            if now - giveaway.created_at > timedelta(days=28):
                #將超過28天的抽獎自動關閉
                giveaway.is_on = False
                sclient.sqldb.merge(giveaway)
            else:
                view = GiveawayView(giveaway, sqldb=sclient.sqldb, bot=self.bot)
                self.bot.add_view(view)
                if giveaway.end_at:
                    job = scheduler.add_job(giveaway_auto_end, DateTrigger(giveaway.end_at if giveaway.end_at > now else now + timedelta(seconds=10)), args=[self.bot, view])
                    print(f"job: {job}")
                log.debug(f"Loaded giveaway: {giveaway.id}")
        else:
            pass
        
        if not scheduler.running:
            scheduler.start()

    async def earthquake_check(self):
        cache = sclient.sqldb.get_notify_cache(NotifyChannelType.MajorQuakeNotifications)
        timefrom = cache.value if cache else datetime.now(tz) - timedelta(days=1)
        try:
            earthquake_records = cwa_api.get_earthquake_report_auto(timefrom.strftime("%Y-%m-%dT%H:%M:%S"), True)
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
        sclient.sqldb.set_notify_cache(NotifyChannelType.MajorQuakeNotifications, timefrom)

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
        
        cache = sclient.sqldb.get_notify_cache(NotifyChannelType.WeatherWarning)
        report_time = cache.value if cache else datetime.now(tz) - timedelta(days=1)
        datas = [i for i in apidatas if i.datasetInfo.issueTime > report_time]
        for data in datas:
            report_time = data.datasetInfo.issueTime
            await self.bot.send_notify_channel(data.embed(), NotifyChannelType.WeatherWarning)
        sclient.sqldb.set_notify_cache(NotifyChannelType.WeatherWarning, report_time)

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

    async def twitch_live(self):
        log.debug("twitch_live start")
        caches = sclient.sqldb.get_community_caches(NotifyCommunityType.TwitchLive)
        if not caches:
            return
        
        users_id = [user_id for user_id in caches.keys()]
        data = tw_api.get_lives(users_id)
        log.debug(f"twitch_live data: {data}")
        update_data:dict[str, datetime] = {}

        for user_id in users_id:
            if data[user_id] and not caches[user_id]:
                # 直播開始
                update_data[user_id] = data[user_id].started_at

                embed = data[user_id].embed()
                await self.bot.send_notify_communities(embed, NotifyCommunityType.TwitchLive, user_id)

            elif not data[user_id] and caches[user_id]:
                # 直播結束
                update_data[user_id] = None

        sclient.sqldb.set_community_caches(NotifyCommunityType.TwitchLive, update_data)

    async def twitch_video(self):
        caches = sclient.sqldb.get_community_caches(NotifyCommunityType.TwitchVideo)
        if not caches:
            return
        
        update_data:dict[str, datetime] = {}
        for user_id, cache in caches.items():
            videos = tw_api.get_videos(user_id, after=cache.value)
            
            if videos:
                videos.reverse()
                update_data[user_id] = videos[-1].created_at

                for video in videos:
                    embed = video.embed()
                    await self.bot.send_notify_communities(embed, NotifyCommunityType.TwitchVideo, video.user_id)

        sclient.sqldb.set_community_caches(NotifyCommunityType.TwitchVideo, update_data)

    async def twitch_clip(self):
        caches = sclient.sqldb.get_community_caches(NotifyCommunityType.TwitchClip)
        if not caches:
            return
        
        update_data:dict[str, datetime] = {}
        for user_id, cache in caches.items():
            clips = tw_api.get_clips(user_id, started_at=cache.value)
            if clips: 
                newest = clips[0].created_at
                broadcaster_id = clips[0].broadcaster_id
                
                # 取得剪輯的來源影片（直播）
                videos_dict = {clip.video_id: None for clip in clips}
                api_video = tw_api.get_videos(video_ids=list(videos_dict.keys()))
                videos_dict = {video.id: video for video in api_video}

                for clip in clips:
                    video = videos_dict[clip.video_id]
                    newest = clip.created_at if clip.created_at > newest else newest
                    if clip.title != video.title:
                        embed = clip.embed(video)
                        await self.bot.send_notify_communities(embed, NotifyCommunityType.TwitchClip, broadcaster_id)

                update_data[broadcaster_id] = (newest + timedelta(seconds=1))

        sclient.sqldb.set_community_caches(NotifyCommunityType.TwitchClip, update_data)

    async def youtube_video(self):
        caches = sclient.sqldb.get_community_caches(NotifyCommunityType.Youtube)
        if not caches:
            return
        
        update_data:dict[str, datetime] = {}
        for ytchannel_id, cache in caches.items():
            #抓取資料
            rss_data = yt_rss.get_videos(ytchannel_id, cache.value)
            if not rss_data:
                continue

            #整理影片列表&儲存最後更新時間
            rss_data.reverse()
            video_id_list = [d.yt_videoid for d in rss_data]
            update_data[ytchannel_id] = rss_data[-1].uplood_at

            api_videos = yt_api.get_video(video_id_list)
            #發布通知
            for video in api_videos:
                embed = video.embed()
                await self.bot.send_notify_communities(embed, NotifyCommunityType.Youtube, ytchannel_id, no_mention=video.is_live_end)
                
                if video.liveStreamingDetails and video.liveStreamingDetails.scheduledStartTime:
                    scheduler.add_job(self.test_one_times_job, DateTrigger(video.liveStreamingDetails.scheduledStartTime + timedelta(seconds=30)), args=[video])

        sclient.sqldb.set_community_caches(NotifyCommunityType.Youtube, update_data)

    async def twitter_tweets_rss(self):
        log.debug("twitter_tweets start")
        caches = sclient.sqldb.get_community_caches(NotifyCommunityType.TwitterTweet)
        if not caches:
            return
        
        update_data:dict[str, datetime] = {}
        for twitter_user_id, cache in caches.items():
            log.debug(f"twitter_tweets: {twitter_user_id}")
            #tweets = rss_hub.get_twitter(user_name, local=True, after=cache.value)
            try:
                results = cli_api.get_user_timeline(twitter_user_id, after=cache.value)
            except subprocess.CalledProcessError as e:
                log.error(e.stderr)
                continue
            log.debug(f"twitter_tweets data: {results}")
            
            if results is None:
                log.warning(f"twitter_tweets error / not found: {twitter_user_id}")
                sclient.sqldb.remove_notify_community(NotifyCommunityType.TwitterTweet, twitter_user_id)
            elif results.list:
                tweets = results.list
                tweets.reverse()
                newest = tweets[0].createdAt
                for tweet in tweets:
                    newest = tweet.createdAt if tweet.createdAt > newest else newest
                    #await self.bot.send_notify_communities(None, NotifyCommunityType.TwitterTweet, user_name, content=f"{tweet.author} 轉推了推文↩️\n{tweet.link}" if tweet.is_retweet else f"{tweet.author} 發布新推文\n{tweet.link}")
                    await self.bot.send_notify_communities(None, NotifyCommunityType.TwitterTweet, twitter_user_id, defult_content=f"{tweet.tweetBy.fullName} 轉推了推文↩️" if tweet.is_retweet else f"{tweet.tweetBy.fullName} 發布新推文", additional_content=tweet.url)

                update_data[twitter_user_id] = (newest + timedelta(seconds=1))

        sclient.sqldb.set_community_caches(NotifyCommunityType.TwitterTweet, update_data)

    # async def get_mongodb_data(self):
    #     dbdata = mongedb.get_apidata()

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
        callback_url = sqldb.get_bot_token(APIType.Google, 4).callback_uri
        for record in sclient.sqldb.get_expired_push_records():
            yt_push.add_push(record.channel_id, callback_url)
            await asyncio.sleep(3)
            data = yt_push.get_push(record.channel_id, callback_url)

            if data.has_verify:
                record.push_at = data.last_successful_verification
                record.expire_at = data.expiration_time
                sclient.sqldb.merge(record)
                await asyncio.sleep(1)
            else:
                log.warning(f"refresh_yt_push failed: {record.channel_id}")

    async def test_one_times_job(self, video: YoutubeVideo):
        # TODO: 改名並新增開台時間變更的處理方式
        log.info(f"test_one_times_job: {video.snippet.title}")
        for _ in range(30):
            video_now = yt_api.get_video(video.id)[0]
            if video_now.snippet.liveBroadcastContent == "live":
                log.info(f"test_one_times_job: {video_now.snippet.title} is live")

                embed = video_now.embed()
                await self.bot.send_notify_communities(embed, NotifyCommunityType.Youtube, video_now.snippet.channelId)
                break
            await asyncio.sleep(120)

async def giveaway_auto_end(bot:discord.Bot, view:GiveawayView):
    log.debug(f"giveaway_auto_end: {view.giveaway.id}")
    if view.is_finished():
        return
    
    embed = view.end_giveaway()
    channel = bot.get_channel(view.giveaway.channel_id)
    try:
        message = await channel.fetch_message(view.giveaway.message_id)
        await message.edit(embed=embed,view=view)
    except discord.NotFound:
        log.warning(f"giveaway_auto_end: message not found {view.giveaway.message_id}")
        return
    

def setup(bot):
    bot.add_cog(task(bot))