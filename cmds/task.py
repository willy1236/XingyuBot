import asyncio
import random
import time
from datetime import datetime, timezone, timedelta, date

import discord
import genshin
from discord.ext import commands,tasks
from requests.exceptions import ConnectTimeout

from starcord import Cog_Extension,Jsondb,sclient,log,BotEmbed,Utilities, ChoiceList
from starcord.DataExtractor import *
from starcord.models.community import TwitchVideo, YoutubeVideo
from starcord.types import NotifyCommunityType

def slice_list(lst:list[YoutubeVideo], target) -> list[YoutubeVideo]:
    """以target為基準取出更新的影片資訊"""
    index = next((i for i, d in enumerate(lst) if d.uplood_at > target), None)
    return lst[index:] if index else lst

def slice_list_twitch(lst:list[TwitchVideo], target:datetime) -> list[TwitchVideo]:
    """以target為基準取出更新的影片資訊"""
    index = next((i for i, d in enumerate(lst) if d.created_at > target), None)
    return lst[index:] if index else lst

class task(Cog_Extension):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        #await self.bot.wait_until_ready()
    tz = timezone(timedelta(hours=8))
    
    @commands.Cog.listener()
    async def on_ready(self):
        scheduler = sclient.scheduler
        if not Jsondb.jdata.get("debug_mode",True):
            scheduler.add_job(self.apex_info_update,'cron',minute='00,15,30,45',second=1,jitter=30,misfire_grace_time=60)
            scheduler.add_job(self.apex_crafting_update,'cron',hour=1,minute=5,second=0,jitter=30,misfire_grace_time=60)
            scheduler.add_job(self.forecast_update,'cron',hour='00,03,06,09,12,15,18,21',minute=0,second=1,jitter=30,misfire_grace_time=60)
            #scheduler.add_job(self.auto_hoyo_reward,'cron',hour=19,minute=0,second=0,jitter=30,misfire_grace_time=60)
            #scheduler.add_job(self.update_rpgshop_data,'cron',hour=0,minute=0,second=1,jitter=30,misfire_grace_time=60)
            
            #scheduler.add_job(self.update_channel_dict,'cron',hour='*',minute="0,30",second=0,jitter=30,misfire_grace_time=60)
            scheduler.add_job(self.start_eletion,'cron',day=1,hour=0,minute=0,second=30,jitter=30,misfire_grace_time=60)
            scheduler.add_job(self.remind_eletion,'cron',day=28,hour=21,minute=0,second=0,jitter=30,misfire_grace_time=60)

            scheduler.add_job(self.earthquake_check,'interval',minutes=2,jitter=30,misfire_grace_time=40)
            scheduler.add_job(self.youtube_video,'interval',minutes=15,jitter=30,misfire_grace_time=40)
            scheduler.add_job(self.twitch_video,'interval',minutes=15,jitter=30,misfire_grace_time=40)
            scheduler.add_job(self.twitch_clip,'interval',minutes=10,jitter=30,misfire_grace_time=40)
            #scheduler.add_job(self.city_battle,'interval',minutes=1,jitter=30,misfire_grace_time=60)
            #scheduler.add_job(self.get_mongodb_data,'interval',minutes=3,jitter=30,misfire_grace_time=40)

            scheduler.add_job(sclient.init_NoticeClient,"date")

            self.twitch.start()
        else:
            pass
            #scheduler.add_job(self.start_eletion,"date")
        
        if not scheduler.running:
            scheduler.start()

    async def earthquake_check(self):
        timefrom = Jsondb.read_cache('earthquake_timefrom')
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
            Jsondb.write_cache('earthquake_timefrom',time.strftime("%Y-%m-%dT%H:%M:%S"))

            if data.auto_type == 'E-A0015-001':
                text = '顯著有感地震報告'
            elif data.auto_type == 'E-A0016-001':
                text = '小區域地震報告'
            else:
                text = '地震報告'
            
            records = sclient.sqldb.get_notify_channel_by_type('earthquake')
            for i in records:
                channel = self.bot.get_channel(i['channel_id'])
                if channel:
                    if i.get('role_id'):
                        try:
                            role = self.bot.get_guild(i['guild_id']).get_role(i['role_id'])
                            text += f' {role.mention}'
                        except:
                            pass
                    await channel.send(text,embed=data.embed())
                    await asyncio.sleep(0.5)
                else:
                    log.warning(f"earthquake_check fail sending message: guild:{i['guild_id']}/channel:{i['channel_id']}")

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
            
            records = sclient.sqldb.get_notify_channel_by_type('apex_info')
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
                "data": apex_crafting[0:1]
            }
            Jsondb.write_cache("apex_crafting",apex_crafting_dict)


    async def forecast_update(self):
        forecast = CWA_API().get_forecast()
        if forecast:
            records = sclient.sqldb.get_notify_channel_by_type('forecast')
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
                guilds = sclient.sqldb.get_notify_community_guild(NotifyCommunityType.Twitch.value, user)
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
                del twitch_cache[user]

        Jsondb.write_cache('twitch',twitch_cache)

    async def twitch_video(self):
        users = sclient.get_notice_dict("twitch_v")
        if not users:
            return
        twitch_cache = Jsondb.read_cache('twitch_v') or {}
        api = TwitchAPI()
        for user in users:
            videos = api.get_videos(user)
            cache_last_update_time = datetime.fromisoformat(twitch_cache.get(user)) if twitch_cache.get(user) else None
            if not cache_last_update_time or videos[0].created_at > cache_last_update_time:
                videos.reverse()
                video_list = slice_list_twitch(videos, cache_last_update_time)
                twitch_cache[user] = video_list[-1].created_at.isoformat()

                for data in video_list:
                    embed = data.embed()
                    guilds = sclient.sqldb.get_notify_community_guild(NotifyCommunityType.TwitchVideo.value,data.user_id)
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

    async def twitch_clip(self):
        users = sclient.get_notice_dict("twitch_c")
        if not users:
            return
        twitch_cache = Jsondb.read_cache('twitch_c') or {}
        api = TwitchAPI()
        for user in users:
            cache_last_update_time = datetime.fromisoformat(twitch_cache.get(user)) if twitch_cache.get(user) else None
            clips = api.get_clips(user, started_at=cache_last_update_time.strftime('%Y-%m-%dT%H:%M:%SZ') if cache_last_update_time else None)
            if clips:
                newest = clips[0].created_at
                broadcaster_id = clips[0].broadcaster_id
                for clip in clips:
                    newest = clip.created_at if clip.created_at > newest else newest
                    embed = clip.embed()
                    guilds = sclient.sqldb.get_notify_community_guild(NotifyCommunityType.TwitchClip.value,broadcaster_id)
                    
                    for guildid in guilds:
                        guild = self.bot.get_guild(guildid)
                        channel = self.bot.get_channel(guilds[guildid][0])
                        role = guild.get_role(guilds[guildid][1])
                        if channel:
                            if role:
                                await channel.send(f'{role.mention} 新剪輯上傳啦~',embed=embed)
                            else:
                                await channel.send(f'新剪輯上傳啦~',embed=embed)
                            await asyncio.sleep(0.5)
                        else:
                            log.warning(f"twitch_c: {guild.id}/{channel.id}")

                twitch_cache[broadcaster_id] = newest.isoformat()

        Jsondb.write_cache('twitch_c',twitch_cache)

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
            if not cache_last_update_time or rss_data[0].uplood_at > cache_last_update_time:
                #整理影片列表&儲存最後更新時間
                rss_data.reverse()
                video_list = slice_list(rss_data, cache_last_update_time)
                cache_youtube[ytchannel_id] = rss_data[-1].uplood_at.isoformat()
                #發布通知
                for video in video_list:
                    embed = video.embed()
                    guilds = sclient.sqldb.get_notify_community_guild(NotifyCommunityType.Youtube.value,ytchannel_id)
                    for guildid in guilds:
                        guild = self.bot.get_guild(guildid)
                        channel = self.bot.get_channel(guilds[guildid][0])
                        role = guild.get_role(guilds[guildid][1])
                        text = "新影片上傳啦~"
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
        list = sclient.sqldb.get_hoyo_reward()
        for user in list:
            user_id = user['user_id']
            user_dc = self.bot.get_user(int(user_id))
            channel_id = user['channel_id']
            channel = self.bot.get_channel(int(channel_id))
            cookies = sclient.sqldb.get_userdata(user_id,'game_hoyo_cookies')
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
        sclient.sqldb.rpg_shop_daily()

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
        session = Utilities.calculate_eletion_session()
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

            position_name = ChoiceList.get_tw(position, "position_option")
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
        

def setup(bot):
    bot.add_cog(task(bot))