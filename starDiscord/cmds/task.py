import asyncio
import random
import time
from datetime import date, datetime, timedelta, timezone

import discord
from discord.ext import commands, tasks
from requests.exceptions import ConnectTimeout

from starlib import BotEmbed, Jsondb, log, sclient, tz, utilities
from starlib.dataExtractor import *
from starlib.models.community import TwitchClip
from starlib.types import NotifyChannelType, NotifyCommunityType

from ..extension import Cog_Extension


def filter_twitch_clip(lst:list[TwitchClip], target:datetime) -> list[TwitchClip]:
    """以target為基準取出更新的影片資訊"""
    return [d for d in lst if d.created_at >= target]
    
rss = YoutubeRSS()
ytapi = YoutubeAPI()
twapi = TwitchAPI()

class task(Cog_Extension):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        #await self.bot.wait_until_ready()
    
    @commands.Cog.listener()
    async def on_ready(self):
        scheduler = sclient.scheduler
        if not Jsondb.config.get("debug_mode",True):
            # scheduler.add_job(self.apex_info_update,'cron',minute='00,15,30,45',second=1,jitter=30,misfire_grace_time=60)
            # scheduler.add_job(self.apex_crafting_update,'cron',hour=1,minute=5,second=0,jitter=30,misfire_grace_time=60)
            scheduler.add_job(self.forecast_update,'cron',hour='00,03,06,09,12,15,18,21',minute=0,second=1,jitter=30,misfire_grace_time=60)

            scheduler.add_job(self.earthquake_check,'interval',minutes=2,jitter=30,misfire_grace_time=40)
            scheduler.add_job(self.youtube_video,'interval',minutes=15,jitter=30,misfire_grace_time=40)
            scheduler.add_job(self.twitch_live,'interval',minutes=3,jitter=15,misfire_grace_time=20)
            scheduler.add_job(self.twitch_video,'interval',minutes=15,jitter=30,misfire_grace_time=40)
            scheduler.add_job(self.twitch_clip,'interval',minutes=10,jitter=30,misfire_grace_time=40)
            #scheduler.add_job(self.get_mongodb_data,'interval',minutes=3,jitter=30,misfire_grace_time=40)

            if self.bot.user.id == 589744540240314368:
                scheduler.add_job(self.birtday_task,'cron',month=10,day=16,hour=8,minute=0,second=0,jitter=30,misfire_grace_time=60)
                

            #self.twitch.start()
        else:
            pass
        
        if not scheduler.running:
            scheduler.start()

    async def earthquake_check(self):
        timefrom = Jsondb.get_cache('earthquake_timefrom')
        try:
            datas = CWA_API().get_earthquake_report_auto(timefrom)
        except ConnectTimeout:
            log.warning("earthquake_check timeout.")
            return
        except:
            return
        
        if not datas:
            return

        for data in datas:
            time = datetime.strptime(data.originTime, "%Y-%m-%d %H:%M:%S") + timedelta(seconds=1)
            Jsondb.write_cache('earthquake_timefrom', time.strftime("%Y-%m-%dT%H:%M:%S"))

            if data.auto_type == 'E-A0015-001':
                text = '顯著有感地震報告'
            elif data.auto_type == 'E-A0016-001':
                text = '小區域地震報告'
            else:
                text = '地震報告'
            
            records = sclient.sqldb.get_notify_channel_by_type(NotifyChannelType.EarthquakeNotifications)
            for i in records:
                channel = self.bot.get_channel(i.channel_id)
                if channel:
                    if i.role_id:
                        try:
                            role = self.bot.get_guild(i.guild_id).get_role(i.role_id)
                            text += f' {role.mention}'
                        except:
                            pass
                    await channel.send(text,embed=data.embed())
                    await asyncio.sleep(0.5)
                else:
                    log.warning(f"earthquake_check fail sending message: guild:{i.guild_id}/channel:{i.channel_id}")

    async def weather_warning_check(self):
        timefrom = Jsondb.get_cache('earthquake_timefrom')
        try:
            data = CWA_API().get_earthquake_report_auto(timefrom)
        except:
            pass

    async def apex_info_update(self):
        aclient = ApexAPI()
        map = aclient.get_map_rotation()
        crafting = aclient.get_crafting_from_chche()
        if map:
            embed_list = []
            if crafting:
                embed_list.append(crafting.embed())
            embed_list.append(map.embed())
            
            records = sclient.sqldb.get_notify_channel_by_type(NotifyChannelType.ApexRotation)
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
        apex_crafting = Jsondb.get_cache("apex_crafting")
        if not apex_crafting or apex_crafting.get("date") != today.isoformat():
            apex_crafting = ApexAPI().get_raw_crafting()
            apex_crafting_dict = {
                "date": today.isoformat(),
                "data": apex_crafting[0:1]
            }
            Jsondb.write_cache("apex_crafting", apex_crafting_dict)


    async def forecast_update(self):
        forecast = CWA_API().get_forecast()
        if forecast:
            records = sclient.sqldb.get_notify_channel_by_type(NotifyChannelType.WeatherForecast)
            for i in records:
                channel = self.bot.get_channel(i.channel_id)
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
                    log.warning(f"forecast_update: {i.guild_id}/{i.channel_id}")

    #@tasks.loop(minutes=3)
    async def twitch_live(self):
        log.debug("twitch_live start")
        users = sclient.dbcache[NotifyCommunityType.TwitchLive]
        if not users:
            return
        twitch_cache = Jsondb.get_cache('twitch') or {}
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

        Jsondb.write_cache('twitch',twitch_cache)

    async def twitch_video(self):
        users = sclient.dbcache[NotifyCommunityType.TwitchVideo]
        if not users:
            return
        twitch_cache = Jsondb.get_cache('twitch_v') or {}
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

        Jsondb.write_cache('twitch_v',twitch_cache)

    async def twitch_clip(self):
        users = sclient.dbcache[NotifyCommunityType.TwitchClip]
        if not users:
            return
        twitch_cache = Jsondb.get_cache('twitch_c') or {}
        for user in users:
            cache_last_update_time = datetime.fromisoformat(twitch_cache.get(user)).replace(tzinfo=tz) if twitch_cache.get(user) else None
            clips = twapi.get_clips(user, started_at=cache_last_update_time)
            # Twitch API 會無視started_at參數回傳錯誤時間的資料，故使用函數過濾掉，解法尚待改進
            clips = filter_twitch_clip(clips, cache_last_update_time)
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

        Jsondb.write_cache('twitch_c',twitch_cache)

    async def youtube_video(self):
        ytchannels = sclient.dbcache[NotifyCommunityType.Youtube]
        if not ytchannels:
            return
        cache_youtube = Jsondb.get_cache('youtube') or {}
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

        Jsondb.write_cache('youtube',cache_youtube)

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
        session = utilities.calculate_eletion_session(datetime.now())
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

    async def remind_eletion(self):
        channel = self.bot.get_channel(1160459117270405222)
        await channel.send("投票時間接近了，提醒大家記得參選喔")
        
    async def birtday_task(self):
        channel = self.bot.get_channel(566533708371329026)
        await channel.send("今天是個特別的日子，別忘記了喔⭐")

def setup(bot):
    bot.add_cog(task(bot))