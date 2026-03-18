import asyncio
import ipaddress
from datetime import date, datetime, timedelta

import discord
import genshin
import nmap
from discord.commands import SlashCommandGroup
from discord.ext import commands, pages

from starlib import BotEmbed, ChoiceList, Jsondb, csvdb, log, sclient, tz
from starlib.database import LOLGameCache, LOLGameRecord, PlatformType, UserGame, UserIPDetails
from starlib.exceptions import APIInvokeError
from starlib.providers import *

from ..checks import RegisteredContext, ensure_registered
from ..extension import Cog_Extension
from ..uiElement.modals import HoyolabCookiesModal

game_option = ChoiceList.set("game_set_option")
hoyo_game_option = [
    discord.OptionChoice(name="原神", value=genshin.Game.GENSHIN),
    discord.OptionChoice(name="崩壞3rd", value=genshin.Game.HONKAI),
    discord.OptionChoice(name="崩壞：星穹軌道", value=genshin.Game.STARRAIL),
]

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
    # hoyo = SlashCommandGroup("hoyo", "MiHaYo相關指令")
    match_cmd = SlashCommandGroup("match", "聯賽相關指令")

    @game.command(description="設定遊戲資料", name_localizations=ChoiceList.name("game_set"))
    @ensure_registered()
    async def set(
        self,
        ctx: RegisteredContext,
        game: discord.Option(int, name="遊戲", description="要設定的遊戲", required=True, choices=game_option),
        value: discord.Option(str, name="資料", description="要設定的資料，留空以移除資料", default=None),
    ):
        await ctx.defer()
        id = str(ctx.author.id)
        game = PlatformType(game)
        if not value:
            sclient.sqldb.remove_user_game(id, game)
            await ctx.respond(f"已將{game}資料移除")
            return

        user_game = UserGame(discord_id=ctx.author.id, game=game.value)

        unneed_verify = []
        if game in unneed_verify:
            user_game.player_name = value

        elif game == PlatformType.Steam:
            APIdata = SteamAPI().get_user(value)
            if APIdata:
                user_game.player_name = APIdata.name
                user_game.player_id = (APIdata.id,)
            else:
                await ctx.respond(f"錯誤:找不到此用戶", ephemeral=True)
                return

        elif game == PlatformType.LOL:
            riot_user = riot_api.get_riot_account_byname(value)
            APIdata = riot_api.get_player_bypuuid(riot_user.puuid)
            if APIdata:
                user_game.player_name = riot_user.fullname
                user_game.player_id = APIdata.puuid
            else:
                await ctx.respond(f"錯誤:找不到此用戶", ephemeral=True)
                return

        elif game == PlatformType.Apex:
            APIdata = ApexAPI().get_player(value)
            if APIdata:
                user_game.player_name = APIdata.name
                user_game.player_id = APIdata.id
            else:
                await ctx.respond(f"錯誤:找不到此用戶", ephemeral=True)
                return

        elif game == PlatformType.Osu:
            APIdata = OsuAPI().get_player(value)
            if APIdata:
                user_game.player_name = APIdata.name
                user_game.player_id = APIdata.id
            else:
                await ctx.respond(f"錯誤:找不到此用戶", ephemeral=True)
                return

        sclient.sqldb.merge(user_game)
        await ctx.respond(f"已將{ctx.author.mention}的 {Jsondb.get_tw(game.value, 'game_set_option')} 資料設定為 {user_game.player_name}")

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

    # @hoyo.command(description="如何設定cookies(需先設定才能使用其他功能)")
    # @commands.cooldown(rate=1, per=1)
    # async def help(self, ctx):
    #     embed = BotEmbed.simple(description="1.前往 https://www.hoyolab.com/ 並登入\n2.複製以下代碼```script:d=document.cookie; c=d.includes('account_id') || alert('過期或無效的Cookie,請先登出帳號再重新登入!'); c && document.write(d)```\n3.在網址列打上java後直接貼上複製的代碼\n4.找到`ltuid=`跟`ltoken=`並複製其中的內容\n5.使用指令 </hoyo set:1045323352421711947>")

    #     embed = BotEmbed.simple(description="1.前往 https://www.hoyolab.com/ 並登入\n2.F12->Application(應用程式)->Cookies->點開www.hoyolab.com\n3.找到`ltuid_v2`、`ltmid_v2`跟`ltoken_v2`\n4.使用指令 </hoyo set:1045323352421711947>並在彈出視窗中填入對應的資料")
    #     embed2 = BotEmbed.simple(description="擁有此cookie將可以使機器人以登入帳號的身分瀏覽與操作hoyolab的相關功能，但無法用於登入遊戲與改變遊戲中所持有的內容。\n若對此功能有疑慮，可隨時終止使用，cookie也可以隨時刪除，若使用此功能則代表您允許機器人進行上述操作，並自負相應的風險。")
    #     embed = BotEmbed.deprecated()
    #     await ctx.respond(embeds=[embed])

    # @hoyo.command(description='設定cookies')
    # @commands.cooldown(rate=1,per=1)
    # async def set(self,ctx:discord.ApplicationContext,
    #               remove:discord.Option(bool,name='若要移除資料請設為true',default=False)):
    #     if remove:
    #         sclient.sqldb.remove_hoyo_cookies(ctx.author.id)
    #         await ctx.respond(f'{ctx.author.mention} cookies移除完成',ephemeral=True)
    #         return

    #     await ctx.send_modal(HoyolabCookiesModal())

    # @hoyo.command(description='取得每月原石來源統計（原神）')
    # @commands.cooldown(rate=1,per=1)
    # async def diary(self,ctx):
    #     await ctx.defer()
    #     cookies = sclient.sqldb.get_userdata(str(ctx.author.id),'game_hoyo_cookies')
    #     if not cookies:
    #         raise commands.errors.ArgumentParsingError("沒有設定cookies或已過期")
    #     client = genshin.Client(cookies,lang='zh-tw')
    #     diary = await client.get_diary()

    #     embed_list = []
    #     primogems_gap = diary.data.current_primogems - diary.data.last_primogems
    #     if primogems_gap > 0:
    #         text = f'比上個月多{primogems_gap}顆'
    #     elif primogems_gap < 0:
    #         text = f'比上個月少{primogems_gap*-1}顆'
    #     else:
    #         text = f'與上個月相同'
    #     embed = BotEmbed.simple(title=f'本月總計：{diary.data.current_primogems} 顆原石',description=text)
    #     for category in diary.data.categories:
    #         name = category.name
    #         embed.add_field(name=name,value=f'{category.amount}({category.percentage}%)')
    #     embed_list.append(embed)

    #     mora_gap = diary.data.current_mora - diary.data.last_mora
    #     if primogems_gap > 0:
    #         text = f'比上個月多{mora_gap}個'
    #     elif primogems_gap < 0:
    #         text = f'比上個月少{-mora_gap}個'
    #     else:
    #         text = f'與上個月相同'
    #     embed = BotEmbed.simple(title=f'本月總計：{diary.data.current_mora} 個摩拉',description=text)
    #     embed_list.append(embed)

    #     await ctx.respond(ctx.author.mention,embeds=embed_list)

    # @hoyo.command(description='尋找HoYoLab用戶')
    # @commands.cooldown(rate=1,per=1)
    # async def hoyolab(self,ctx,
    #                hoyolab_name:discord.Option(str,name='hoyolab名稱',description='要查詢的用戶')):
    #     await ctx.defer()
    #     cookies = sclient.sqldb.get_userdata(str(ctx.author.id),'game_hoyo_cookies')
    #     if not cookies:
    #         raise commands.errors.ArgumentParsingError("沒有設定cookies或已過期")
    #     client = genshin.Client(cookies,lang='zh-tw')

    #     hoyolab_user = None
    #     users = await client.search_users(hoyolab_name)
    #     #print(users)
    #     for user in users:
    #         if user.nickname == hoyolab_name:
    #             hoyolab_user = user
    #             break
    #     #print(user.hoyolab_uid)

    #     #自己搜不到自己
    #     if hoyolab_user:
    #         try:
    #             cards = await client.get_record_cards(user.hoyolab_id)
    #             embed_list= []
    #             for card in cards:
    #                 #print(card.uid, card.level, card.nickname)
    #                 #活躍天數days_active 獲得角色數characters 成就達成數achievements 深境螺旋spiral_abyss
    #                 if card.game == genshin.types.Game.GENSHIN:
    #                 #    print(card.data[0].value,card.data[1].value,card.data[2].value,card.data[3].value)
    #                     embed = BotEmbed.simple(title=f'{card.nickname}(LV.{card.level})')
    #                     embed.add_field(name="HoYOLab UID",value=hoyolab_user.hoyolab_id)
    #                     embed.add_field(name="角色UID",value=card.uid)
    #                     embed.add_field(name="活躍天數",value=card.data[0].value)
    #                     embed.add_field(name="獲得角色數",value=card.data[1].value)
    #                     embed.add_field(name="成就達成數",value=card.data[2].value)
    #                     embed.add_field(name="深境螺旋",value=card.data[3].value)
    #                     embed_list.append(embed)
    #                 await ctx.respond(embeds=embed_list)

    #         except genshin.errors.DataNotPublic:
    #             #if e.retcode == 10102:
    #             await ctx.respond('用戶資訊未公開')
    #         except genshin.errors.GenshinException as e:
    #             await ctx.respond(e.msg)
    #     else:
    #         hoyolab_user = await client.get_hoyolab_user()
    #         if hoyolab_user:
    #             #print(hoyolab_user)
    #             accounts = await client.get_game_accounts()

    #             embed = BotEmbed.general(name=f"{hoyolab_user.nickname}(LV.{hoyolab_user.level.level})",
    #                                      icon_url=hoyolab_user.icon,
    #                                      url=f"https://www.hoyolab.com/accountCenter/postList?id={hoyolab_user.hoyolab_id}",
    #                                      description=hoyolab_user.introduction)
    #             embed.add_field(name="HoYOLab ID",value=hoyolab_user.hoyolab_id)
    #             for account in accounts:
    #                 if account.game == genshin.types.Game.GENSHIN:
    #                     gamename = "原神"
    #                 elif account.game == genshin.types.Game.HONKAI:
    #                     gamename = "崩壞3rd"
    #                 embed.add_field(name=f"{account.nickname}({gamename})",value=f'{account.server_name} {account.uid} LV.{account.level}',inline=False)
    #             embed.set_image(url=hoyolab_user.bg_url)
    #             await ctx.respond(embed=embed)
    #         else:
    #             await ctx.respond('用戶未找到')

    # @hoyo.command(description='尋找原神用戶')
    # @commands.cooldown(rate=1,per=1)
    # async def genshin(self,ctx,
    #                genshin_id:discord.Option(str,name='原神uid',description='要查詢的用戶',default=None)):
    #     await ctx.defer()
    #     cookies = sclient.sqldb.get_userdata(str(ctx.author.id),'game_hoyo_cookies')
    #     if not cookies:
    #         raise commands.errors.ArgumentParsingError("沒有設定cookies或已過期")
    #     client = genshin.Client(cookies,lang='zh-tw')

    #     user = await client.get_genshin_user(genshin_id)
    #     #print(user.characters)
    #     #print(user.info)
    #     #print(user.stats)
    #     embed = BotEmbed.simple(title=f'{user.info.nickname}({user.info.server})')
    #     embed.add_field(name="等級",value=user.info.level)
    #     embed.add_field(name="成就",value=user.stats.achievements)
    #     embed.add_field(name="活躍天數",value=user.stats.days_active)
    #     embed.add_field(name="角色",value=user.stats.characters)
    #     embed.add_field(name="本期深淵",value=user.stats.spiral_abyss)
    #     embed.set_image(url=user.info.icon)
    #     await ctx.respond(embed=embed)

    # @hoyo.command(description='尋找崩壞3rd用戶')
    # @commands.cooldown(rate=1,per=1)
    # async def honkai(self,ctx,
    #                honkai_id:discord.Option(str,name='崩壞uid',description='要查詢的用戶',default=None)):
    #     await ctx.defer()
    #     cookies = sclient.sqldb.get_userdata(str(ctx.author.id),'game_hoyo_cookies')
    #     if not cookies:
    #         raise commands.errors.ArgumentParsingError("沒有設定cookies或已過期")
    #     client = genshin.Client(cookies,lang='zh-tw')

    #     user = await client.get_honkai_user(int(honkai_id))
    #     #print(user.characters)
    #     #print(user.info)
    #     #print(user.stats)
    #     #print(user)
    #     embed = BotEmbed.simple(title=f'{user.info.nickname}({user.info.server})')
    #     embed.add_field(name="等級",value=user.info.level)
    #     embed.add_field(name="成就",value=user.stats.achievements)
    #     embed.set_image(url=user.info.icon)
    #     await ctx.respond(embed=embed)

    # @hoyo.command(description='查詢深境螺旋')
    # @commands.cooldown(rate=1,per=1)
    # async def spiral_abyss(self,ctx,
    #                        genshin_id:discord.Option(str,name='原神uid',description='要查詢的用戶',default=None),
    #                        previous:discord.Option(bool,name='是否查詢上期紀錄',description='',default=False)):
    #     await ctx.defer()
    #     cookies = sclient.sqldb.get_userdata(str(ctx.author.id),'game_hoyo_cookies')
    #     if not cookies:
    #         raise commands.errors.ArgumentParsingError("沒有設定cookies或已過期")
    #     client = genshin.Client(cookies,lang='zh-tw')

    #     try:
    #         r_user = await client.get_genshin_user(genshin_id)
    #         r_spiral_abyss = await client.get_genshin_spiral_abyss(genshin_id,previous=previous)
    #     except genshin.errors.DataNotPublic:
    #         await ctx.respond('用戶資訊未公開')
    #         return

    #     start_time = (r_spiral_abyss.start_time+timedelta(hours=8)).strftime("%Y/%m/%d")
    #     end_time = (r_spiral_abyss.end_time+timedelta(hours=8)).strftime("%Y/%m/%d")

    #     embed = BotEmbed.simple(description=f"第{r_spiral_abyss.season}期 {start_time} 至 {end_time}\n挑戰{r_spiral_abyss.total_battles}場中獲勝{r_spiral_abyss.total_wins}場，最深至{r_spiral_abyss.max_floor}層，共獲得{r_spiral_abyss.total_stars}顆星")
    #     if r_user:
    #         embed.title=f"{r_user.info.nickname} 的深境螺旋紀錄"
    #     else:
    #         embed.title=f"深境螺旋紀錄"

    #     ranks = r_spiral_abyss.ranks
    #     dict = {
    #         "角色：最多上場":ranks.most_played,
    #         "角色：最多擊殺": ranks.most_kills,
    #         "角色：最痛一擊": ranks.strongest_strike,
    #         "角色：最多承傷": ranks.most_damage_taken,
    #         "角色：最多技能使用": ranks.most_skills_used,
    #         "角色：最多大招使用": ranks.most_bursts_used
    #     }
    #     for i in dict:
    #         text = ''
    #         for j in dict[i]:
    #             text += f'{j.name} {j.value}\n'
    #         if text:
    #             embed.add_field(name=i,value=text)

    #     #r_spiral_abyss.floors
    #     #print(r_spiral_abyss)
    #     await ctx.respond(embed=embed)

    # @hoyo.command(description='兌換禮包碼')
    # @commands.cooldown(rate=1,per=1)
    # async def code(self,ctx,
    #                game:discord.Option(str,name='遊戲',description='要簽到的遊戲',choices=hoyo_game_option),
    #                code:discord.Option(str,name='禮包碼',description='要兌換的禮包碼'),
    #                uid:discord.Option(str,name='uid',description='要兌換的用戶')):
    #     if not config.get("debug_mode"):
    #         cookies = sclient.sqldb.get_userdata(str(ctx.author.id),'game_hoyo_cookies')
    #     else:
    #         cookies = genshin.utility.get_browser_cookies("chrome")

    #     if not cookies:
    #         raise commands.errors.ArgumentParsingError("沒有設定cookies或已過期")
    #     client = genshin.Client(cookies,lang='zh-tw')
    #     await client.redeem_code(code,uid,game=game)
    #     await ctx.respond('兌換已完成')

    # @hoyo.command(description='簽到設定（多個遊戲請個別設定）（尚在測試可能有bug）')
    # @commands.cooldown(rate=1,per=1)
    # async def reward(self,ctx,
    #                game:discord.Option(str,name='遊戲',description='要簽到的遊戲',choices=hoyo_game_option),
    #                need_mention:discord.Option(bool,name='成功簽到時是否要tag提醒',default=True),
    #                remove:discord.Option(bool,name='若要移除資料請設為true',default=False)):
    #     if remove:
    #         sclient.sqldb.remove_hoyo_reward(ctx.author.id)
    #         await ctx.respond('設定已移除')
    #         return

    #     cookies = sclient.sqldb.get_userdata(str(ctx.author.id),'game_hoyo_cookies')
    #     if not cookies:
    #         raise commands.errors.ArgumentParsingError("沒有設定cookies或已過期")
    #     sclient.sqldb.add_hoyo_reward(ctx.author.id,game,ctx.channel.id,need_mention)
    #     await ctx.respond('設定已完成')

    # @hoyo.command(description='測試',guild_ids=debug_guilds)
    # @commands.cooldown(rate=1,per=1)
    # async def test(self,ctx,
    #                hoyolab_uid:discord.Option(str,name='hoyolab_uid',description='要查詢的用戶',default=None)):
    #     cookies = sclient.sqldb.get_userdata(str(ctx.author.id),'game_hoyo_cookies')
    #     if not cookies:
    #         raise commands.errors.ArgumentParsingError("沒有設定cookies")
    #     client = genshin.Client(cookies,lang='zh-tw')
    #     r = await client.get_genshin_spiral_abyss(hoyolab_uid)
    #     print(r)
    #     await ctx.respond('done')

    # @commands.message_command(name="尋找序號",guild_ids=debug_guilds)
    # async def exchange_code_genshin(self,ctx,message:discord.Message):
    #     textline = message.content.splitlines()
    #     p = re.compile(r'[0-9A-Z]{10,}')
    #     code_list = []
    #     for i in textline:
    #         code = p.match(i)
    #         if code and code not in code_list:
    #             code_list.append(code.group())

    #     if code_list:
    #         codetext = ""
    #         for i in code_list:
    #             codetext+=f"\n[{i}](https://genshin.hoyoverse.com/zh-tw/gift?code={i})"
    #         #await ctx.respond(f"找到以下兌換碼{codetext}\n若有設定cookie及uid則將自動兌換",ephemeral=True)
    #         await ctx.respond(f"找到以下兌換碼{codetext}",ephemeral=True)

    # #         cookies = self.sqldb.get_userdata(str(ctx.author.id),'game_hoyo_cookies')
    # #         dbdata = self.sqldb.get_game_data(str(ctx.author.id),DatabaseGame.GENSHIN.value)
    # #         if not cookies:
    # #             await ctx.send("沒有設定cookies或已過期")
    # #             return
    # #         if dbdata:
    # #             client = genshin.Client(cookies,lang='zh-tw')
    # #             uid = dbdata['player_id']
    # #             for code in code_list:
    # #                 await client.redeem_code(code,uid,game=genshin.Game.GENSHIN)
    # #                 asyncio.sleep(3)
    # #             await ctx.send('兌換已完成')
    #     else:
    #         await ctx.respond(f"沒有找到兌換碼",ephemeral=True)

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
