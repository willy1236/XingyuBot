import asyncio
import subprocess
from datetime import datetime, timedelta, timezone

import discord
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from discord.ext import commands, tasks
from requests.exceptions import ConnectTimeout, RequestException

from starlib import BotEmbed, Jsondb, log, sclient, sqldb, tz, utils
from starlib.instance import *
from starlib.models.community import YoutubeVideo
from starlib.models.postgresql import UsersCountRecord, VoiceTime
from starlib.types import APIType, NotifyChannelType, NotifyCommunityType

from ..bot import DiscordBot
from ..extension import Cog_Extension
from ..uiElement.view import GiveawayView

voice_times: dict[int, timedelta] = {}

class task(Cog_Extension):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_ready(self):
        scheduler = self.bot.scheduler
        if not Jsondb.config.get("debug_mode", True):
            # 即時通知 - 保留misfire_grace_time
            scheduler.add_job(self.forecast_update, "cron", hour="0/3", minute=0, second=1, misfire_grace_time=60)
            scheduler.add_job(self.weather_check, "cron", minute="20,35", second=30, misfire_grace_time=60)
            scheduler.add_job(self.apex_map_rotation, "cron", minute="0/15", second=10, misfire_grace_time=60)
            scheduler.add_job(self.earthquake_check, "interval", minutes=3, misfire_grace_time=60)
            scheduler.add_job(self.weather_warning_check, "interval", minutes=15, misfire_grace_time=120)
            # scheduler.add_job(self.typhoon_warning_check, "cron", minute="0/15", second=30, jitter=30, misfire_grace_time=40)
            # scheduler.add_job(self.youtube_video, "interval", minutes=5, jitter=30, misfire_grace_time=40)
            scheduler.add_job(self.twitch_live, "interval", minutes=4, misfire_grace_time=20)
            scheduler.add_job(self.twitch_video, "interval", minutes=10, misfire_grace_time=40)
            scheduler.add_job(self.twitch_clip, "interval", minutes=5, misfire_grace_time=40)
            scheduler.add_job(self.notify_twitter_tweet_updates, "interval", minutes=10, misfire_grace_time=40)
            # scheduler.add_job(self.get_mongodb_data,'interval',minutes=3,jitter=30,misfire_grace_time=40)

            # 背景刷新 - 保留 jitter
            scheduler.add_job(refresh_yt_push, "cron", hour="2/12", minute=0, second=0, jitter=300)
            scheduler.add_job(refresh_ip_last_seen, "cron", minute="0/20", second=0, jitter=60, misfire_grace_time=90)
            scheduler.add_job(self.save_voice_time, "cron", hour="0/1", minute="0/30", second=0, jitter=60, misfire_grace_time=90)

            # 統計任務 - 保留 misfire_grace_time + max_instances
            scheduler.add_job(self.add_voice_time, "cron", minute="*/1", second=30, misfire_grace_time=20, max_instances=1)

            if self.bot.user and self.bot.user.id == 589744540240314368:
                scheduler.add_job(self.birthday_task, "cron", month=10, day=16, hour=8, minute=0, second=0, misfire_grace_time=60)
                scheduler.add_job(record_users_count, "cron", args=[self.bot], hour=0, minute=0, second=0, jitter=240, max_instances=1)
                # scheduler.add_job(self.new_years_eve_task, CronTrigger(month=1, day=1, hour=0, minute=0, second=0), misfire_grace_time=60)

        # 抽獎
        now = datetime.now(tz)
        for giveaway in sclient.sqldb.get_active_giveaways():
            if now - giveaway.created_at > timedelta(days=28):
                # 將超過28天的抽獎自動關閉
                giveaway.is_on = False
                sclient.sqldb.merge(giveaway)
                log.debug("Ended giveaway: %s", giveaway.id)
            else:
                view = GiveawayView(giveaway, sqldb=sclient.sqldb, bot=self.bot)
                self.bot.add_view(view)
                if giveaway.end_at:
                    job = scheduler.add_job(
                        giveaway_auto_end, DateTrigger(giveaway.end_at if giveaway.end_at > now else now + timedelta(seconds=10)), args=[self.bot, view]
                    )
                    log.debug("job added: %s", job)
                log.debug("Loaded giveaway: %s", giveaway.id)
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
            log.exception("earthquake_check error")
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
        weathers = cwa_api.get_weather_data()
        if not weathers:
            return
        weather = weathers[0]
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

    async def typhoon_warning_check(self):
        cache = sclient.sqldb.get_notify_cache(NotifyChannelType.TyphoonWarning)
        report_time = cache.value if cache else datetime.now(tz) - timedelta(days=1)

        apidatas = ncdr_rss.get_typhoon_warning(after=report_time)
        log.info(f"typhoon_warning_check: found {len(apidatas)} new warnings, after {report_time}")
        if not apidatas:
            return

        datas = [i for i in apidatas if i.updated > report_time]
        for data in datas:
            report_time = data.updated
            await self.bot.send_notify_channel(data.embed(), NotifyChannelType.TyphoonWarning)
        sclient.sqldb.set_notify_cache(NotifyChannelType.TyphoonWarning, report_time)

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
            log.exception("apex_map_rotation error")

    async def twitch_live(self):
        log.debug("twitch_live start")
        caches = sclient.sqldb.get_community_caches(NotifyCommunityType.TwitchLive)
        if not caches:
            return

        users_id = [user_id for user_id in caches.keys()]
        data = tw_api.get_lives(users_id)
        log.debug(f"twitch_live data: {data}")
        update_data: dict[str, datetime | None] = {}

        for user_id in users_id:
            live_data = data[user_id]
            cache_data = caches[user_id]
            if live_data and not cache_data:
                # 直播開始
                update_data[user_id] = live_data.started_at

                embed = live_data.embed()
                await self.bot.send_notify_communities(embed, NotifyCommunityType.TwitchLive, user_id)

            elif not live_data and cache_data:
                # 直播結束
                update_data[user_id] = None

        sclient.sqldb.set_community_caches(NotifyCommunityType.TwitchLive, update_data)

    async def twitch_video(self):
        caches = sclient.sqldb.get_community_caches(NotifyCommunityType.TwitchVideo)
        if not caches:
            return

        update_data: dict[str, datetime] = {}
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

        update_data: dict[str, datetime | None] = {}
        for user_id, cache in caches.items():
            clips = tw_api.get_clips(user_id, started_at=cache.value)
            if clips:
                newest = clips[0].created_at
                broadcaster_id = clips[0].broadcaster_id

                # 取得剪輯的來源影片（直播）
                videos_dict = {clip.video_id: None for clip in clips}
                api_video = tw_api.get_videos(video_ids=list(videos_dict.keys()))
                if not api_video:
                    continue
                videos_dict = {video.id: video for video in api_video}

                for clip in clips:
                    video = videos_dict[clip.video_id]
                    newest = clip.created_at if clip.created_at > newest else newest
                    if clip.title != video.title:
                        embed = clip.embed(video)
                        await self.bot.send_notify_communities(embed, NotifyCommunityType.TwitchClip, broadcaster_id)

                update_data[broadcaster_id] = newest + timedelta(seconds=1)

        sclient.sqldb.set_community_caches(NotifyCommunityType.TwitchClip, update_data)

    async def youtube_video(self):
        caches = sclient.sqldb.get_community_caches(NotifyCommunityType.Youtube)
        if not caches:
            return

        update_data: dict[str, datetime] = {}
        for ytchannel_id, cache in caches.items():
            # 抓取資料
            rss_data = yt_rss.get_videos(ytchannel_id, cache.value)
            if not rss_data:
                continue

            # 整理影片列表&儲存最後更新時間
            rss_data.reverse()
            video_id_list = [d.yt_videoid for d in rss_data]
            update_data[ytchannel_id] = rss_data[-1].uplood_at

            api_videos = google_api.get_video(video_id_list)
            # 發布通知
            for video in api_videos:
                embed = video.embed()
                await self.bot.send_notify_communities(embed, NotifyCommunityType.Youtube, ytchannel_id, no_mention=video.is_live_end)

                if video.is_live_upcoming_with_time:
                    assert video.liveStreamingDetails.scheduledStartTime is not None, "Scheduled start time should not be None for upcoming live videos"
                    self.bot.scheduler.add_job(
                        youtube_start_live_notify, DateTrigger(video.liveStreamingDetails.scheduledStartTime + timedelta(seconds=30)), args=[self.bot, video]
                    )

        sclient.sqldb.set_community_caches(NotifyCommunityType.Youtube, update_data)

    async def notify_twitter_tweet_updates(self):
        log.debug("notify_twitter_tweet_updates start")
        caches = sclient.sqldb.get_community_caches(NotifyCommunityType.TwitterTweet)
        if not caches:
            return

        update_data: dict[str, datetime] = {}
        for twitter_user_id, cache in caches.items():
            try:
                log.debug(f"notify_twitter_tweet_updates: {twitter_user_id}")
                # tweets = rss_hub.get_twitter(user_name, local=True, after=cache.value)
                results = cli_api.get_user_timeline(twitter_user_id, after=cache.value)

                log.debug(f"notify_twitter_tweet_updates data: {results}")

                if results is None:
                    log.warning(f"notify_twitter_tweet_updates error / not found: {twitter_user_id}")
                    # sclient.sqldb.remove_notify_community(NotifyCommunityType.TwitterTweet, twitter_user_id)
                elif results.list:
                    tweets = results.list
                    tweets.reverse()
                    newest = tweets[0].createdAt
                    for tweet in tweets:
                        newest = tweet.createdAt if tweet.createdAt > newest else newest
                        # await self.bot.send_notify_communities(None, NotifyCommunityType.TwitterTweet, user_name, content=f"{tweet.author} 轉推了推文↩️\n{tweet.link}" if tweet.is_retweet else f"{tweet.author} 發布新推文\n{tweet.link}")
                        await self.bot.send_notify_communities(
                            None,
                            NotifyCommunityType.TwitterTweet,
                            twitter_user_id,
                            default_content=f"{tweet.tweetBy.fullName} 轉推了推文↩️" if tweet.is_retweet else f"{tweet.tweetBy.fullName} 發布新推文",
                            additional_content=tweet.url,
                        )

                    update_data[twitter_user_id] = newest + timedelta(seconds=1)
                await asyncio.sleep(1)
            except subprocess.CalledProcessError as e:
                log.error(e.stderr)
                continue
            except Exception as e:
                log.error(f"notify_twitter_tweet_updates error (id: %s): %s", twitter_user_id, e)
                continue

        sclient.sqldb.set_community_caches(NotifyCommunityType.TwitterTweet, update_data)

    async def add_voice_time(self):
        log.debug("add_voice_time start")
        guild = self.bot.get_guild(happycamp_guild[0])

        for channel in guild.voice_channels:
            if channel == guild.afk_channel:
                continue
            for member in channel.members:
                if not member.voice.deaf and not member.voice.mute:
                    if voice_times.get(member.id) is None:
                        voice_times[member.id] = timedelta(minutes=1)
                    else:
                        voice_times[member.id] += timedelta(minutes=1)

    async def save_voice_time(self):
        # 2025-10-26
        log.debug("save_voice_time start")
        if not voice_times:
            return

        guild = self.bot.get_guild(happycamp_guild[0])
        discord_ids = list(voice_times.keys())
        voice_time_records = sclient.sqldb.get_voice_times(discord_ids, guild.id)

        for discord_id, delta in voice_times.items():
            if discord_id not in voice_time_records:
                voice_time_records[discord_id] = VoiceTime(discord_id=discord_id, guild_id=guild.id, total_minute=delta)
            else:
                voice_time_records[discord_id].total_minute += delta

        sqldb.batch_merge(list(voice_time_records.values()))
        voice_times.clear()

    # async def get_mongodb_data(self):
    #     dbdata = mongedb.get_apidata()

    async def start_eletion(self):
        log.info("start_eletion start")
        session = utils.calculate_eletion_session(datetime.now())
        channel = self.bot.get_channel(1163127708839071827)

        embed = sclient.election_format(session, self.bot)
        await channel.send(embed=embed)

        dbdata = sclient.sqldb.get_election_full_by_session(session)
        results = {}
        for position in Jsondb.options["position_option"].keys():
            results[position] = []

        for data in dbdata:
            user_id = data["discord_id"]
            # party_name = i['party_name'] or "無黨籍"
            position = data["position"]

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
            # count = count_dict[position]
            if len(results[position]) <= 0:
                continue

            position_name = Jsondb.get_tw(position, "position_option")
            title = f"第{session}屆中央選舉：{position_name}"
            # options = [f"{i}號" for i in range(1,count + 1)]
            i = 1
            options = []
            for username in results[position]:
                options.append(f"{i}號 {username}")
                i += 1

            view = sclient.create_election_poll(title, options, self.bot.user.id, channel.guild.id, self.bot)

            message = await channel.send(embed=view.embed(channel.guild), view=view)
            await asyncio.sleep(1)

        await channel.send(f"第{session}屆中央選舉投票已開始，請大家把握時間踴躍投票!")

        tz = timezone(timedelta(hours=8))
        start_time = datetime.now(tz)
        if start_time.hour < 20:
            end_time = datetime(start_time.year, start_time.month, start_time.day, 20, 0, 0, tzinfo=tz)
        else:
            end_time = start_time + timedelta(days=1)

        start_time += timedelta(seconds=10)
        event = await channel.guild.create_scheduled_event(
            name="【快樂營中央選舉】投票階段", start_time=start_time, end_time=end_time, location="<#1163127708839071827>"
        )

    async def birthday_task(self):
        channel = self.bot.get_channel(566533708371329026)
        assert channel, "Channel not found"
        await channel.send("今天是個特別的日子，別忘記了喔⭐")

    async def new_years_eve_task(self):
        channel = self.bot.get_channel(643764975663448064)
        assert channel, "Channel not found"
        msg = await channel.send("新的一年 祝大家新年快樂~🎉\n來自快樂營的2025新年轟炸 @everyone ", allowed_mentions=discord.AllowedMentions(everyone=True))
        await msg.add_reaction("🎉")

async def refresh_yt_push():
    config = sqldb.get_websub_config(APIType.Google, 4)
    assert config.callback_uri, "Callback URL is not set"
    # TODO: 改用 WebSubInstance統一處理
    for record in sclient.sqldb.get_expiring_push_records():
        # TODO: 需要處理 secret
        yt_push.add_push(record.channel_id, config.callback_uri, config.hub_secret)
        await asyncio.sleep(3)
        data = yt_push.get_push(record.channel_id, config.callback_uri, config.hub_secret)

        if data and data.has_verify:
            record.push_at = data.last_successful_verification
            record.expire_at = data.expiration_time
            sclient.sqldb.merge(record)
            log.info("refresh_yt_push: %s 已更新到期為 %s", record.channel_id, record.expire_at)
            await asyncio.sleep(1)
        else:
            log.warning(f"refresh_yt_push failed: {record.channel_id}")


async def youtube_start_live_notify(bot: DiscordBot, video: YoutubeVideo):
    log.info(f"youtube_start_live_notify: {video.snippet.title}")
    for _ in range(30):
        video_now = google_api.get_video(video.id)[0]
        if video_now.snippet.liveBroadcastContent == "live":
            log.info(f"youtube_start_live_notify: {video_now.snippet.title} is live")

            embed = video_now.embed()
            await bot.send_notify_communities(embed, NotifyCommunityType.Youtube, video_now.snippet.channelId)
            break
        await asyncio.sleep(120)


async def giveaway_auto_end(bot: discord.Bot, view: GiveawayView):
    log.debug("giveaway_auto_end: id=%s", view.giveaway.id)
    if view.is_finished():
        return

    embed = view.end_giveaway()
    channel = bot.get_channel(view.giveaway.channel_id)
    try:
        message = await channel.fetch_message(view.giveaway.message_id)
        await message.edit(embed=embed, view=view)
    except discord.NotFound:
        log.warning("giveaway_auto_end: message %s not found", view.giveaway.message_id)
        return

async def refresh_ip_last_seen():
    """定時更新IP最後出現時間"""
    log.debug("refresh_ip_last_seen start")
    now = datetime.now(tz)
    arp_list = utils.get_arp_list()
    sqldb.set_ips_last_seen({ip_and_mac: now for ip_and_mac in arp_list})

async def record_users_count(bot: DiscordBot):
    """定時記錄用戶數量"""
    log.debug("record_users_count start")
    users_count = len(bot.users)
    servers_count = len(bot.guilds)
    shard_id = bot.shard_id
    record = UsersCountRecord(record_date=datetime.now(tz).date(), users_count=users_count, servers_count=servers_count, shard_id=shard_id)
    sqldb.add(record)


def setup(bot):
    bot.add_cog(task(bot))
