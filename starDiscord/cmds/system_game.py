import asyncio
import ipaddress
from datetime import date, datetime, timedelta

import discord
import nmap
from discord.commands import SlashCommandGroup
from discord.ext import commands, pages

from starlib import BotEmbed, ChoiceList, Jsondb, csvdb, log, sclient, tz
from starlib.database import LOLGameCache, LOLGameRecord, PlatformType, UserIPDetails
from starlib.exceptions import APIInvokeError
from starlib.providers import *

from ..checks import RegisteredContext, ensure_registered
from ..extension import Cog_Extension

game_option = ChoiceList.set("game_set_option")
riot_api = RiotAPI()

def get_riot_account_puuid(user: discord.User, riot_id: str = None) -> str | None:
    user_game = sclient.sqldb.get_user_game(user.id, PlatformType.LOL)
    if user_game:
        return user_game.other_id

    if riot_id:
        account = riot_api.get_riot_account_byname(riot_id)
        if account:
            return account.puuid

class system_game(Cog_Extension):
    game = SlashCommandGroup("game", "遊戲資訊相關指令", name_localizations=ChoiceList.name("game"))
    lol = SlashCommandGroup("lol", "League of Legends相關指令", name_localizations=ChoiceList.name("lol"))
    osu = SlashCommandGroup("osu", "Osu相關指令", name_localizations=ChoiceList.name("osu"))
    apex = SlashCommandGroup("apex", "Apex相關指令", name_localizations=ChoiceList.name("apex"))
    dbd = SlashCommandGroup("dbd", "Dead by Daylight相關指令", name_localizations=ChoiceList.name("dbd"))
    steam = SlashCommandGroup("steam", "Steam相關指令", name_localizations=ChoiceList.name("steam"))
    minecraft_cmd = SlashCommandGroup("minecraft", "Minecraft相關指令", name_localizations=ChoiceList.name("minecraft"))
    match_cmd = SlashCommandGroup("match", "聯賽相關指令")

    @game.command(description="查詢遊戲資料", name_localizations=ChoiceList.name("game_player"))
    async def player(self, ctx, user: discord.Option(discord.Member, name="用戶", description="要查詢的用戶", default=None)):
        await ctx.defer()
        user = user or ctx.author
        userid = user.id

        player_data = sclient.sqldb.get_user_game_all(userid)
        if player_data:
            embed = BotEmbed.user(user, "遊戲資料")
            for data in player_data:
                embed.add_field(name=Jsondb.get_tw(data.game, "game_set_option"), value=data.player_name)
            await ctx.respond(f"查詢成功", embed=embed)
        else:
            await ctx.respond(f"錯誤：找不到用戶或尚未註冊資料", ephemeral=True)

    @lol.command(description="查詢Riot帳號資料", name_localizations=ChoiceList.name("lol_riot"))
    async def riot(self, ctx, riot_id: discord.Option(str, name="riot_id", description="名稱#tag")):
        api = RiotAPI()
        user = api.get_riot_account_byname(riot_id)
        if user:
            await ctx.respond("查詢成功", embed=user.embed())
        else:
            await ctx.respond("查詢失敗：查無此ID", ephemeral=True)

    @lol.command(name="user", description="查詢League of Legends用戶資料", name_localizations=ChoiceList.name("lol_user"))
    async def lol_user(self, ctx, riot_id: discord.Option(str, name="riot_id", description="名稱#tag，留空則使用資料庫查詢", required=False)):
        assert isinstance(riot_id, str) or riot_id is None, "riot_id must be a string or None"

        if not riot_id:
            user_game = sclient.sqldb.get_user_game(ctx.author.id, PlatformType.LOL)
            if not user_game:
                await ctx.respond("查詢失敗：無設定ID", ephemeral=True)
                return
            riot_id = user_game.player_name

        account = riot_api.get_riot_account_byname(riot_id)
        if not account:
            await ctx.respond("查詢失敗：查無此ID", ephemeral=True)
            return

        player = riot_api.get_player_bypuuid(account.puuid)
        if player:
            await ctx.respond("查詢成功", embed=player.embed(account.fullname))
        else:
            await ctx.respond("查詢失敗：查無此ID", ephemeral=True)

    @lol.command(description="查詢League of Legends對戰資料", name_localizations=ChoiceList.name("lol_match"))
    async def match(self, ctx, matchid: discord.Option(str, name="對戰id", description="要查詢的對戰")):
        match = riot_api.get_match(matchid)
        if match:
            await ctx.respond("查詢成功", embed=match.desplay())
        else:
            await ctx.respond("查詢失敗:查無此ID", ephemeral=True)

    @lol.command(description="查詢最近一次的League of Legends對戰", name_localizations=ChoiceList.name("lol_playermatch"))
    async def playermatch(self, ctx, riot_id: discord.Option(str, name="riot_id", description="名稱#tag，留空則使用資料庫查詢", required=False)):
        puuid = get_riot_account_puuid(ctx.author, riot_id)
        if not puuid:
            await ctx.respond("查詢失敗：查無此玩家", ephemeral=True)
            return

        match_list = riot_api.get_player_matchs(puuid, 1)
        if not match_list:
            await ctx.respond("查詢失敗：此玩家查無對戰紀錄", ephemeral=True)
            return

        match = riot_api.get_match(match_list[0])
        if match:
            await ctx.respond("查詢成功", embed=match.desplay())
        else:
            raise APIInvokeError("playermatch occurred error while getting match data.")

    @lol.command(description="查詢League of Legends專精英雄", name_localizations=ChoiceList.name("lol_masteries"))
    async def masteries(self, ctx, riot_id: discord.Option(str, name="riot_id", description="名稱#tag，留空則使用資料庫查詢", required=False)):
        puuid = get_riot_account_puuid(ctx.author, riot_id)
        if not puuid:
            await ctx.respond("查詢失敗：查無此玩家", ephemeral=True)
            return

        masteries_list = riot_api.get_summoner_masteries(puuid)
        if not masteries_list:
            await ctx.respond("查詢失敗：此玩家查無專精資料", ephemeral=True)

        player = riot_api.get_riot_account_bypuuid(puuid)
        embed = BotEmbed.simple(f"{player.fullname} 專精英雄")
        for data in masteries_list:
            text_list = [
                f"專精等級： {data.championLevel}",
                f"專精分數： {data.championPoints} ({data.championPointsUntilNextLevel} 升級)",
                f"上次遊玩： <t:{int(data.lastPlayTime.timestamp())}>",
                f"賽季里程碑： {data.championSeasonMilestone}",
            ]
            champion_name = csvdb.get_row(csvdb.lol_champion, "champion_id", data.championId)
            embed.add_field(
                name=champion_name.loc["name_tw"] if not champion_name.empty else f"ID: {data.championId}", value="\n".join(text_list), inline=False
            )
        await ctx.respond("查詢成功", embed=embed)

    @lol.command(description="查詢League of Legends的玩家積分資訊", name_localizations=ChoiceList.name("lol_rank"))
    async def rank(self, ctx, riot_id: discord.Option(str, name="riot_id", description="名稱#tag，留空則使用資料庫查詢", required=False)):
        puuid = get_riot_account_puuid(ctx.author, riot_id)
        if not puuid:
            await ctx.respond("查詢失敗：查無此玩家", ephemeral=True)
            return

        rank_data = riot_api.get_summoner_rank(puuid)
        if rank_data:
            embed_list = [rank.embed() for rank in rank_data]
        else:
            player = riot_api.get_riot_account_bypuuid(puuid)
            embed_list = [BotEmbed.simple(f"{player.fullname} 本季未進行過積分對戰")]
        await ctx.respond("查詢成功", embeds=embed_list)

    # ! name_localizations=ChoiceList.name("lol_recentmatches") 會報錯
    @lol.command(description="查詢最近的League of Legends對戰ID（僅取得ID，需另行用查詢對戰內容）")
    async def recentmatches(self, ctx, riot_id: discord.Option(str, name="riot_id", description="名稱#tag，留空則使用資料庫查詢", required=False)):
        puuid = get_riot_account_puuid(ctx.author, riot_id)
        if not puuid:
            await ctx.respond("查詢失敗：查無此玩家", ephemeral=True)
            return

        match_list = riot_api.get_player_matchs(puuid, 20)
        if not match_list:
            await ctx.respond("查詢失敗:此玩家查無對戰紀錄", ephemeral=True)
            return

        player = riot_api.get_riot_account_bypuuid(puuid)
        embed = BotEmbed.simple(f"{player.fullname} 的近期對戰", "此排序由新到舊\n" + "\n".join(match_list))
        await ctx.respond("查詢成功", embed=embed)

    @lol.command(description="查詢正在進行的League of Legends對戰（無法查詢聯盟戰棋）", name_localizations=ChoiceList.name("lol_activematches"))
    async def activematches(self, ctx, riot_id: discord.Option(str, name="riot_id", description="名稱#tag，留空則使用資料庫查詢", required=False)):
        puuid = get_riot_account_puuid(ctx.author, riot_id)
        if not puuid:
            await ctx.respond("查詢失敗：查無此玩家", ephemeral=True)
            return

        active_match = riot_api.get_summoner_active_match(puuid)
        if not active_match:
            player = riot_api.get_riot_account_bypuuid(puuid)
            await ctx.respond(f"{player.fullname} 沒有進行中的對戰", ephemeral=True)
            return

        await ctx.respond("查詢成功", embed=active_match.desplay())

    @lol.command(description="統計近20場League of Legends對戰的所有玩家牌位", name_localizations=ChoiceList.name("lol_recentplayer"))
    @commands.cooldown(rate=60, per=1)
    async def recentplayer(self, ctx, riot_id: discord.Option(str, name="riot_id", description="名稱#tag")):
        await ctx.defer()
        api = RiotAPI()
        msg = await ctx.respond("查詢中，請稍待片刻，查詢過程需時約3~5分鐘")
        df = api.get_rank_dataframe(riot_id, 1)
        if df is None:
            await msg.edit("查詢失敗:查無此玩家")
            return
        counts = df["tier"].value_counts()
        await ctx.channel.send(embed=BotEmbed.simple(title="查詢結果", description=str(counts)))

    @lol.command(description="取得指定日期的League of Legends職業聯賽比賽結果", name_localizations=ChoiceList.name("lol_progame"))
    async def progame(self, ctx, match_date: discord.Option(str, name="日期", description="要查詢的日期，格式為YYYY-MM-DD", required=False)):
        await ctx.defer()
        match_date = datetime.strptime(match_date, "%Y-%m-%d").date() if match_date else date.today()
        results = LOLMediaWikiAPI().get_date_games(match_date)
        if not results:
            await ctx.respond("查詢失敗：查無此日期的比賽", ephemeral=True)
            return

        tournament_dict: dict[str, discord.Embed] = {}
        for r in results:
            if r["Tournament"] not in tournament_dict:
                tournament_name = r["Tournament"]
                tournament_dict[tournament_name] = BotEmbed.simple(
                    title=tournament_name, description=f"{match_date.strftime('%Y/%m/%d')} 比賽戰果\nPatch：{r['Patch']}"
                )

            embed = tournament_dict[r["Tournament"]]
            name = f"👑{r['Team1']} vs {r['Team2']} {r['Gamename']}" if r["Winner"] == "1" else f"{r['Team1']} vs 👑{r['Team2']} {r['Gamename']}"
            value = f"\n⏱️{r['Gamelength']} ⚔️{r['Team1Kills']} : {r['Team2Kills']}"
            value += f"\n`{r['Team1Players']}` vs `{r['Team2Players']}`"
            team1_picks = []
            for i in r["Team1Picks"].split(","):
                champion_name = csvdb.get_row(csvdb.lol_champion, "name_en", i.replace(" ", ""))
                if not champion_name.empty:
                    team1_picks.append(champion_name.loc["name_tw"])
                else:
                    team1_picks.append(i)

            team2_picks = []
            for i in r["Team2Picks"].split(","):
                champion_name = csvdb.get_row(csvdb.lol_champion, "name_en", i.replace(" ", ""))
                if not champion_name.empty:
                    team2_picks.append(champion_name.loc["name_tw"])
                else:
                    team2_picks.append(i)
            value += f"\n{','.join(team1_picks)} vs {','.join(team2_picks)}"

            embed.add_field(name=name, value=value, inline=False)

        paginator = pages.Paginator(
            pages=[pages.PageGroup([page], page.title) for page in list(tournament_dict.values())],
            use_default_buttons=False,
            show_menu=True,
            menu_placeholder="請選擇賽區",
        )
        await paginator.respond(ctx.interaction, ephemeral=False, target_message="查詢成功")

    @lol.command(description="建立今年度的戰績資料", name_localizations=ChoiceList.name("lol_setyearly"))
    @commands.max_concurrency(number=1, wait=True)
    async def setyearly(
        self, ctx: discord.ApplicationContext, riot_id: discord.Option(str, name="riot_id", description="名稱#tag，留空則使用資料庫查詢", required=False)
    ):
        await ctx.defer()
        puuid = get_riot_account_puuid(ctx.author, riot_id)
        if not puuid:
            await ctx.respond("查詢失敗：查無此玩家", ephemeral=True)
            return

        cache = sclient.sqldb.get_lol_cache(puuid)
        startTime = max(datetime(date.today().year, 1, 1, tzinfo=tz), cache.newest_game_time) if cache else datetime(date.today().year, 1, 1, tzinfo=tz)

        i = 0
        match_list: list[str] = []
        while True:
            lst = riot_api.get_player_matchs(puuid, 100, start=i * 100, startTime=startTime)
            log.info(f"查詢第{i}頁，數量：{len(lst)}")
            match_list.extend(lst)
            if not lst or len(lst) < 100:
                break
            i += 1

        if not match_list:
            await ctx.respond("查詢失敗：此玩家查無對戰紀錄", ephemeral=True)
            return

        msg = await ctx.respond(f"開始查詢中，請稍待片刻，查詢過程預計需{int(len(match_list) / 20) + 1}分鐘")

        records: list[LOLGameRecord] = []
        newest_game_time = datetime.min
        for match_id in match_list:
            try:
                match = riot_api.get_match(match_id)
                if match:
                    if (time := datetime.fromtimestamp(match.info.gameCreation / 1000)) > newest_game_time:
                        newest_game_time = time

                    player = match.get_player_by_puuid(puuid)
                    records.append(
                        LOLGameRecord(
                            puuid=puuid,
                            game_id=match.info.gameId,
                            game_type=match.info.gameType,
                            game_mode=match.info.gameMode,
                            champion_id=player.championId,
                            teamId=player.teamId,
                            created_at=time,
                            timePlayed=timedelta(seconds=player.timePlayed),
                            totalTimeSpentDead=timedelta(seconds=player.totalTimeSpentDead),
                            win=player.win,
                            kills=player.kills,
                            deaths=player.deaths,
                            assists=player.assists,
                            visionScore=player.visionScore,
                            damage_dealt=player.totalDamageDealtToChampions,
                            damage_taken=player.totalDamageTaken,
                            double_kills=player.doubleKills,
                            triple_kills=player.tripleKills,
                            quadra_kills=player.quadraKills,
                            penta_kills=player.pentaKills,
                            gold_earned=player.goldEarned,
                            total_minions_killed=player.totalMinionsKilled,
                            turretKills=player.turretKills,
                            inhibitorKills=player.inhibitorKills,
                            baronKills=player.baronKills,
                            dragonKills=player.dragonKills,
                            item0=player.item0,
                            item1=player.item1,
                            item2=player.item2,
                            item3=player.item3,
                            item4=player.item4,
                            item5=player.item5,
                            item6=player.item6,
                            firstBloodKill=player.firstBloodKill,
                            firstTowerKill=player.firstTowerKill,
                            allInPings=player.allInPings,
                            assistMePings=player.assistMePings,
                            basicPings=player.basicPings,
                            commandPings=player.commandPings,
                            dangerPings=player.dangerPings,
                            enemyMissingPings=player.enemyMissingPings,
                            enemyVisionPings=player.enemyVisionPings,
                            getBackPings=player.getBackPings,
                            holdPings=player.holdPings,
                            needVisionPings=player.needVisionPings,
                            onMyWayPings=player.onMyWayPings,
                            pushPings=player.pushPings,
                            retreatPings=player.retreatPings,
                            visionClearedPings=player.visionClearedPings,
                        )
                    )
            except Exception as e:
                log.error(f"Error processing match {match_id} for puuid {puuid}: {e}")

            await asyncio.sleep(3)

        log.info(f"共查詢到{len(records)}場對戰")
        sclient.sqldb.batch_merge(records)
        cache = LOLGameCache(puuid=puuid, newest_game_time=newest_game_time)
        sclient.sqldb.merge(cache)
        await msg.edit(f"查詢完成，共查詢到{len(records)}場對戰，已儲存至資料庫。最新對戰時間：{newest_game_time.strftime('%Y-%m-%d %H:%M:%S')}")

    @lol.command(description="查詢今年度的戰績資料（目前需手動執行儲存資料後才能統計）", name_localizations=ChoiceList.name("lol_yearly"))
    @commands.cooldown(rate=1, per=30)
    async def yearly(
        self, ctx: discord.ApplicationContext, riot_id: discord.Option(str, name="riot_id", description="名稱#tag，留空則使用資料庫查詢", required=False)
    ):
        await ctx.defer()
        puuid = get_riot_account_puuid(ctx.author, riot_id)
        if not puuid:
            await ctx.respond("查詢失敗：查無此玩家", ephemeral=True)
            return

        embed = BotEmbed.simple("2025年戰績統計")
        lst = sclient.sqldb.get_lol_record_with_champion(puuid)
        champion_lst = []
        for id, count in lst[:10]:
            champion_name = csvdb.get_row(csvdb.lol_champion, "champion_id", id)
            if not champion_name.empty:
                champion_lst.append(f"{champion_name.loc['name_tw']}: {count}")
            else:
                champion_lst.append(f"ID. {id}: {count} 場")
        embed.add_field(name="英雄遊玩次數", value="\n".join(champion_lst) if champion_lst else "無戰績資料", inline=False)

        data = sclient.sqldb.get_lol_record_with_win(puuid)
        win_cnt = data.get(True, 0)
        lose_cnt = data.get(False, 0)
        win_rate = (win_cnt / (win_cnt + lose_cnt) * 100) if (win_cnt + lose_cnt) > 0 else 0
        embed.add_field(name="勝率統計", value=f"勝場: {win_cnt} 場\n敗場: {lose_cnt} 場\n勝率: {win_rate:.2f}%", inline=False)

        await ctx.respond("查詢成功", embed=embed)

    @osu.command(name="user", description="查詢Osu用戶資料", name_localizations=ChoiceList.name("osu_user"))
    @commands.cooldown(rate=1, per=1)
    async def osu_user(self, ctx, username: discord.Option(str, name="玩家名稱", description="要查詢的玩家", default=None)):
        player = OsuAPI().get_player(username)
        if player:
            await ctx.respond("查詢成功", embed=player.desplay())
        else:
            await ctx.respond("查詢失敗:查無此玩家", ephemeral=True)

    @osu.command(name="map", description="查詢Osu圖譜資料", name_localizations=ChoiceList.name("osu_map"))
    @commands.cooldown(rate=1, per=1)
    async def osu_map(self, ctx, mapid: discord.Option(str, name="圖譜id", description="要查詢的圖譜ID", default=None)):
        map = OsuAPI().get_beatmap(mapid)
        if map:
            await ctx.respond("查詢成功", embed=map.desplay())
        else:
            await ctx.respond("查詢失敗:查無此圖譜", ephemeral=True)

    @apex.command(name="user", description="查詢Apex玩家資料", name_localizations=ChoiceList.name("apex_user"))
    @commands.cooldown(rate=1, per=3)
    async def apex_user(self, ctx: discord.ApplicationContext, username: discord.Option(str, name="玩家名稱", description="要查詢的玩家")):
        player = ApexAPI().get_player(username)
        if player:
            await ctx.respond(content="查詢成功", embed=player.desplay())
        else:
            await ctx.respond(content="查詢失敗:查無此ID", ephemeral=True)

    @apex.command(description="查詢Apex地圖資料", name_localizations=ChoiceList.name("apex_map"))
    @commands.cooldown(rate=1, per=3)
    async def map(self, ctx):
        embeds = ApexAPI().get_map_rotation().embeds()
        await ctx.respond(content="查詢成功", embeds=embeds)

    # @apex.command(description='查詢Apex伺服器資料',enabled=False)
    # @commands.cooldown(rate=1,per=3)
    # async def server(self,ctx):
    #     return await ctx.respond(content='暫未開放')
    #     embed = ApexInterface().get_server_status().desplay()
    #     await ctx.respond(content='查詢成功',embed=embed)

    @dbd.command(name="user", description="查詢Dead by daylight玩家資料", name_localizations=ChoiceList.name("dbd_user"))
    @commands.cooldown(rate=1, per=1)
    async def dbd_user(self, ctx, userid: discord.Option(str, name="steamid", description="要查詢的玩家id", default=None)):
        player = DBDInterface().get_player(userid)
        if player:
            await ctx.respond(content="查詢成功", embed=player.embed())
        else:
            await ctx.respond(content="查詢失敗:查無此ID或個人資料設定私人", ephemeral=True)

    @steam.command(description="查詢Steam用戶資料", name_localizations=ChoiceList.name("steam_user"))
    @commands.cooldown(rate=1, per=1)
    async def user(self, ctx, userid: discord.Option(str, name="用戶id", description="要查詢的用戶", default=None)):
        user = SteamAPI().get_user(userid)
        if user:
            await ctx.respond(content="查詢成功", embed=user.embed())
        else:
            await ctx.respond(content="查詢失敗:查無此ID", ephemeral=True)

    @minecraft_cmd.command(name="set", description="設定Minecraft帳號資料", name_localizations=ChoiceList.name("minecraft_set"))
    @ensure_registered()
    @commands.cooldown(rate=1, per=1)
    async def minecraft_set(self, ctx: RegisteredContext, username: discord.Option(str, name="玩家名稱", description="要設定的Minecraft玩家名稱，留空以刪除", default=None)):
        if not username:
            sclient.sqldb.remove_external_account(ctx.cuser.id, PlatformType.Minecraft)
            await ctx.respond(content="已刪除Minecraft帳號資料", ephemeral=True)
            return

        user = MojangAPI().get_uuid(username)
        if user:
            sclient.sqldb.upsert_external_account(ctx.cuser.id, PlatformType.Minecraft, user.id, username)
            await ctx.respond(content=f"設定成功 {user.name}", ephemeral=True)
        else:
            await ctx.respond(content="設定失敗：查無此玩家", ephemeral=True)


    @game.command(description="註冊Radmin VPN帳號", name_localizations=ChoiceList.name("game_radmin"))
    @ensure_registered()
    async def radmin(
        self,
        ctx: RegisteredContext,
        ip_str: discord.Option(
            str,
            name="ipv4位置",
            description="Radmin VPN分配給你的IP位址",
        ),
        name: discord.Option(str, name="使用者名稱", description="你的Radmin VPN名稱", required=False),
    ):
        await ctx.defer(ephemeral=True)
        try:
            ip = ipaddress.IPv4Network(ip_str)
        except ipaddress.AddressValueError:
            await ctx.respond(f"此IP位址格式錯誤，請確認後再試", ephemeral=True)
            return
        if not ip.subnet_of(ipaddress.IPv4Network("26.0.0.0/8")):
            await ctx.respond(f"此IP位址不是Radmin VPN的位置", ephemeral=True)
            return
        account = sclient.sqldb.get_registed_ips_last_seen(ip)
        if account:
            await ctx.respond(f"此IP位址已註冊過，請確認後再試", ephemeral=True)
            return

        nm = nmap.PortScanner()
        nm.scan(hosts=str(ip.network_address), arguments="-sn")
        if nm[str(ip.network_address)].state() != "up":
            await ctx.respond(f"此IP位址目前不在線上，請確認後再試", ephemeral=True)
            return

        now = datetime.now(tz)
        account = UserIPDetails(ip=str(ip), last_seen=now, discord_id=ctx.author.id, registration_at=now)
        if name:
            account.name = name
        sclient.sqldb.merge(account)
        await ctx.respond(f"{ctx.author.mention} 註冊成功，IP：`{ip.network_address}`，使用者名稱：`{name if name else '未登記'}`", ephemeral=True)

    @game.command(description="註冊ZeroTier帳號", name_localizations=ChoiceList.name("game_zerotier"))
    @ensure_registered()
    async def zerotier(
        self,
        ctx: RegisteredContext,
        address_str: discord.Option(
            str,
            name="address",
            description="ZeroTier分配給你的位址",
        ),
        name: discord.Option(str, name="使用者名稱", description="'想在ZeroTier上顯示的名稱", required=False),
    ):
        await ctx.defer(ephemeral=True)
        zt_api = ZeroTierAPI()
        member = zt_api.authorize_member(Jsondb.config.get("zerotier_network_id"), address_str, name=name)
        if not member:
            await ctx.respond(f"ZeroTier帳號註冊失敗，請確認位址是否正確", ephemeral=True)
            return

        now = datetime.now(tz)
        account = UserIPDetails(
            ip=str(member["config"]["ipAssignments"][0]), last_seen=now, discord_id=ctx.author.id, address=member["nodeId"], name=name, registration_at=now
        )
        sclient.sqldb.merge(account)

        await ctx.respond(f"ZeroTier帳號註冊成功，你的IP位址：`{member['config']['ipAssignments'][0]}`", ephemeral=True)

    @game.command(description="查詢VPN登記資料", name_localizations=ChoiceList.name("game_vpn"))
    @ensure_registered()
    async def vpn(self, ctx: RegisteredContext):
        await ctx.defer(ephemeral=True)
        records = sclient.sqldb.get_user_ip_details(ctx.author.id)
        if not records:
            await ctx.respond("查無登記資料，請先登記Radmin或ZeroTier帳號", ephemeral=True)
            return

        embed = BotEmbed.simple(title="VPN登記資料")
        for r in records:
            value = f"最後上線時間：{r.last_seen.strftime('%Y-%m-%d %H:%M:%S')}\n註冊時間：{r.registration_at.strftime('%Y-%m-%d %H:%M:%S') if r.registration_at else '未知'}"
            if r.address:
                value += f"\nZeroTier位址：`{r.address}`"
            embed.add_field(name=f"IP位址：`{r.ip}` 使用者名稱：`{r.name if r.name else '未登記'}`", value=value, inline=False)
        embed.set_footer(text="資料可能不完整，請以實際VPN的紀錄為準")

        await ctx.respond("查詢成功", embed=embed, ephemeral=True)


def setup(bot):
    bot.add_cog(system_game(bot))
