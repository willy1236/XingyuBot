from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

import discord

from starlib.database.postgresql.models import (
    BackupCategory,
    BackupChannel,
    BackupMessage,
    BackupRole,
    HappycampApplicationForm,
    UserModerate,
)
from starlib.database.postgresql.rpg import RPGEquipment, RPGPlayer, RPGUser
from starlib.fileDatabase import Jsondb
from starlib.providers.game.models import (
    ApexMapRotation,
    ApexPlayer,
    DBDPlayer,
    LOLActiveMatch,
    LOLMatch,
    LOLPlayer,
    LOLPlayerRank,
    OsuBeatmap,
    OsuPlayer,
    RiotUser,
    SteamUser,
)
from starlib.providers.general.models import (
    EarthquakeReport,
    Forecast,
    McssServer,
    TyphoonWarningReport,
    WeatherWarningReport,
    weather_warning_emojis,
)
from starlib.settings import tz


class BaseBotEmbed:
    @staticmethod
    def bot(bot: discord.Bot, title: str | None = None, description: str | None = None, url: str | None = None):
        """機器人 格式"""
        assert bot.user is not None, "Bot user must be set before creating an embed."
        embed = discord.Embed(title=title, description=description, color=0xC4E9FF, url=url)
        embed.set_author(name=bot.user.name, icon_url=bot.user.display_avatar.url)
        return embed

    @staticmethod
    def user(user: discord.User, title: str | None = None, description: str | None = None, url: str | None = None):
        """使用者 格式"""
        embed = discord.Embed(title=title, description=description, color=0x00FFFF, url=url)
        embed.set_author(name=user.name, icon_url=user.display_avatar.url)
        return embed

    @staticmethod
    def simple(title: str | None = None, description: str | None = None, url: str | None = None):
        """簡易:不帶作者"""
        embed = discord.Embed(title=title, description=description, color=0xC4E9FF, url=url)
        return embed

    @staticmethod
    def general(
        name: str | None = None,
        icon_url: str | None = None,
        url: str | None = None,
        title: str | None = None,
        description: str | None = None,
        title_url: str | None = None,
    ):
        """普通:自訂作者"""
        embed = discord.Embed(title=title, description=description, color=0xC4E9FF, url=title_url)
        embed.set_author(name=name, icon_url=icon_url, url=url)
        return embed

    @staticmethod
    def deprecated():
        """棄用:展示棄用訊息"""
        embed = discord.Embed(title="此功能目前為棄用狀態", description="此功能目前不開放使用，請洽機器人管理員或支援伺服器", color=0xC4E9FF)
        return embed

    @staticmethod
    def rpg(title: str | None = None, description: str | None = None):
        """RPG系統 格式"""
        embed = discord.Embed(title=title, description=description, color=0xC4E9FF)
        embed.set_footer(text="RPG系統 | 開發時期所有東西皆有可能重置")
        return embed

    @staticmethod
    def info(title: str | None = None, description: str | None = None, url: str | None = None):
        """一般資訊 格式"""
        embed = discord.Embed(title=title, description=description, color=0xC4E9FF, url=url)
        return embed

    @staticmethod
    def simple_warn_sheet(
        warn_user: discord.User | discord.Member,
        moderate_user: discord.abc.User | discord.Member | discord.ClientUser,
        create_at: datetime | None = None,
        last: timedelta = timedelta(seconds=15),
        reason: str = "未提供原因",
        title: str = "已被禁言",
    ):
        """簡易警告表格"""
        if create_at is None:
            create_at = datetime.now()
        timestamp = create_at + last
        embed = discord.Embed(description=f"{warn_user.mention}：{reason}", color=0xC4E9FF)
        embed.set_author(name=f"{warn_user.name} {title}", icon_url=warn_user.display_avatar.url)
        embed.add_field(name="執行人員", value=moderate_user.mention)
        embed.add_field(name="結束時間", value=f"{discord.utils.format_dt(timestamp, style='t')}（{last.total_seconds():.0f}s）")
        embed.timestamp = create_at
        return embed


class BotEmbed(BaseBotEmbed):
    """Embed 格式化工具註冊器。
    提供了註冊模型對應格式化函數的功能，並繼承了 BaseBotEmbed 的所有靜態方法，以兼容之前的使用方式。
    """

    _registry: dict[type, Callable[[Any], discord.Embed]] = {}

    @classmethod
    def register(cls, model_class: type):
        def decorator(func):
            cls._registry[model_class] = func
            return func

        return decorator

    @classmethod
    def create(cls, model: Any) -> discord.Embed:
        formatter = cls._registry.get(type(model))
        if not formatter:
            raise ValueError(f"找不到對應的 Embed 格式化工具: {type(model)}")
        return formatter(model)


# 註冊對應關係
# @BotEmbed.register(ErrorReportModel)
# def format_error_report_model(model: ErrorReportModel) -> discord.Embed:
#     embed = BaseBotEmbed.general(name=str(model.ctx.author), icon_url=model.ctx.author.display_avatar.url, title="❌錯誤回報")
#     embed.add_field(name="錯誤訊息", value=f"```py\n{model.error}```", inline=True)
#     if model.ctx.command:
#         embed.add_field(name="使用指令", value=f"```{model.ctx.command}```", inline=False)
#         embed.add_field(name="參數", value=f"```{model.ctx.selected_options}```", inline=False)
#     embed.add_field(name="使用者", value=f"{model.ctx.author}\n{model.ctx.author.id}", inline=False)
#     embed.add_field(name="發生頻道", value=f"{model.ctx.channel}\n{model.ctx.channel.id}", inline=True)
#     embed.add_field(name="發生群組", value=f"{model.ctx.guild}\n{model.ctx.guild.id}", inline=True)
#     embed.timestamp = datetime.now()
#     return embed


# @BotEmbed.register(ReportModel)
# def format_report_model(model: ReportModel) -> discord.Embed:
#     embed = BaseBotEmbed.general(name=str(model.refer_msg.author), icon_url=model.refer_msg.author.display_avatar.url, title="📢使用者回報")
#     if model.refer_msg:
#         embed.add_field(name="回報訊息", value=f"```{model.msg}```", inline=True)
#         embed.add_field(name="回報對象", value=f"{model.refer_msg.author}\n{model.refer_msg.author.id}", inline=False)
#         embed.add_field(name="發生頻道", value=f"{model.refer_msg.channel}\n{model.refer_msg.channel.id}", inline=True)
#         embed.add_field(name="發生群組", value=f"{model.refer_msg.guild}\n{model.refer_msg.guild.id}", inline=True)
#     else:
#         embed.add_field(name="訊息ID", value="無", inline=True)
#     embed.timestamp = datetime.now()
#     return embed


# @BotEmbed.register(FeedbackModel)
# def format_feedback_model(model: FeedbackModel) -> discord.Embed:
#     embed = BaseBotEmbed.general(name=str(model.ctx.author), icon_url=model.ctx.author.display_avatar.url, title="💡使用者回饋")
#     embed.add_field(name="回饋訊息", value=f"{model.msg.content}", inline=True)
#     embed.add_field(name="回饋使用者", value=f"{model.ctx.author}\n{model.ctx.author.id}", inline=False)
#     embed.add_field(name="發生頻道", value=f"{model.msg.channel}\n{model.msg.channel.id}", inline=True)
#     embed.add_field(name="發生群組", value=f"{model.msg.guild}\n{model.msg.guild.id}", inline=True)
#     embed.timestamp = datetime.now()
#     return embed


# @BotEmbed.register(DMModel)
# def format_dm_model(model: DMModel) -> discord.Embed:
#     embed = BaseBotEmbed.general(name=str(model.msg.author), icon_url=model.msg.author.display_avatar.url, title="📩使用者私訊")
#     embed.add_field(name="私訊內容", value=f"{model.msg.content}", inline=True)
#     if model.msg.channel.recipient:
#         embed.add_field(name="發送者", value=f"{model.msg.author}->{model.msg.channel.recipient}\n{model.msg.author.id}->{model.msg.channel.recipient.id}", inline=False)
#     else:
#         embed.add_field(name="發送者", value=f"{model.msg.author}\n{model.msg.author.id}", inline=False)
#     embed.timestamp = datetime.now()
#     return embed


# @BotEmbed.register(mentionModel)
# def format_mention_model(model: mentionModel) -> discord.Embed:
#     embed = BaseBotEmbed.general(name=str(model.msg.author), icon_url=model.msg.author.display_avatar.url, title="📢使用者提及")
#     embed.add_field(name="提及內容", value=f"{model.msg.content}\n{model.msg.jump_url}", inline=True)
#     embed.add_field(name="提及使用者", value=f"{model.msg.author}\n{model.msg.author.id}", inline=False)
#     embed.add_field(name="發生頻道", value=f"{model.msg.channel}\n{model.msg.channel.id}", inline=True)
#     embed.add_field(name="發生群組", value=f"{model.msg.guild}\n{model.msg.guild.id}", inline=True)
#     embed.timestamp = datetime.now()
#     return embed


@BotEmbed.register(UserModerate)
def format_user_moderate(model: UserModerate) -> discord.Embed:
    user_mention = f"<@{model.discord_id}>"
    moderator_mention = f"<@{model.moderate_user}>"
    warning_type = Jsondb.get_tw(model.moderate_type, "warning_type")
    status_text = (
        f"**編號：{model.warning_id}（{warning_type}）**\n- 被警告用戶：{user_mention}\n- 管理員：<@{model.create_guild}>/{moderator_mention}\n- 原因：{model.reason}\n- 時間：{model.create_time.strftime('%Y-%m-%d %H:%M:%S')}"
    )
    if model.last_time:
        status_text += f"\n- 禁言時長：{model.last_time}"
    if model.officially_given:
        status_text += "\n- 官方認證警告"
    if model.guild_only:
        status_text += "\n- 伺服器內警告"

    embed = discord.Embed(title=f"{user_mention} 的警告單", description=status_text, color=0xC4E9FF)
    return embed


@BotEmbed.register(HappycampApplicationForm)
def format_happycamp_application_form(model: HappycampApplicationForm) -> discord.Embed:
    status_dict = {0: "待審核", 1: "已通過", 2: "已拒絕"}
    embed = discord.Embed(
        title=f"申請表單 #{model.form_id} - {status_dict.get(model.status, '未知狀態')}",
        description=f"- 申請人：<@{model.discord_id}>\n- 提交時間：{model.submitted_at.strftime('%Y-%m-%d %H:%M:%S')}\n- 審核時間：{model.reviewed_at.strftime('%Y-%m-%d %H:%M:%S') if model.reviewed_at else '尚未審核'}\n- 審核者：{f'<@{model.reviewer_id}>' if model.reviewer_id else '尚未審核'}\n- 審核意見：{model.review_comment if model.review_comment else '無'}",
        color=0xC4E9FF,
    )
    embed.add_field(name="申請內容", value=model.content or "無")
    embed.add_field(name="變更 VIP 等級", value=str(model.change_vip_level) if model.change_vip_level is not None else "無")
    return embed


@BotEmbed.register(BackupRole)
def format_backup_role(model: BackupRole) -> discord.Embed:
    embed = BaseBotEmbed.simple(model.role_name, model.description)
    embed.add_field(name="創建於", value=model.created_at.strftime("%Y/%m/%d %H:%M:%S"))
    embed.add_field(name="顏色", value=f"({model.colour_r}, {model.colour_g}, {model.colour_b})")
    if model.members:
        embed.add_field(name="成員", value=",".join(f"<@{member.discord_id}>" for member in model.members), inline=False)
    return embed


@BotEmbed.register(BackupCategory)
def format_backup_category(model: BackupCategory) -> discord.Embed:
    embed = BaseBotEmbed.simple(model.name, model.description)
    embed.add_field(name="創建於", value=model.created_at.strftime("%Y/%m/%d %H:%M:%S"))
    return embed


@BotEmbed.register(BackupChannel)
def format_backup_channel(model: BackupChannel) -> discord.Embed:
    embed = BaseBotEmbed.simple(model.name, model.description)
    embed.add_field(name="創建於", value=model.created_at.strftime("%Y/%m/%d %H:%M:%S"))
    return embed


@BotEmbed.register(BackupMessage)
def format_backup_message(model: BackupMessage) -> discord.Embed:
    embed = BaseBotEmbed.simple(f"Message from <@{model.author_id}>", model.content or "No content")
    embed.add_field(name="Created at", value=model.created_at.strftime("%Y/%m/%d %H:%M:%S"))
    return embed


@BotEmbed.register(RPGPlayer)
def format_rpg_player(model: RPGPlayer) -> discord.Embed:
    embed = BaseBotEmbed.general(name=model.name)
    embed.add_field(name="健康值", value=model.health)
    embed.add_field(name="金錢", value=model.money)
    embed.add_field(name="壓力", value=model.stress)
    return embed


@BotEmbed.register(RPGUser)
def format_rpg_user(model: RPGUser) -> discord.Embed:
    embed = BaseBotEmbed.general(name=f"<@{model.discord_id}>")
    embed.add_field(name="生命/最大生命", value=f"{model.hp} / {model.maxhp}")
    embed.add_field(name="攻擊力", value=model.atk)
    embed.add_field(name="物理防禦力", value=model.pdef)
    embed.add_field(name="命中率", value=f"{model.hrt}%")
    embed.add_field(name="敏捷", value=model.dex)
    return embed


@BotEmbed.register(RPGEquipment)
def format_rpg_equipment(model: RPGEquipment) -> discord.Embed:
    embed = BaseBotEmbed.rpg(model.customized_name if model.customized_name else model.template.name)
    embed.add_field(name="生命", value=model.maxhp)
    embed.add_field(name="攻擊力", value=model.atk)
    embed.add_field(name="物理防禦力", value=model.pdef)
    embed.add_field(name="命中率", value=f"{model.hrt}%")
    embed.add_field(name="敏捷", value=model.dex)
    return embed


@BotEmbed.register(RiotUser)
def format_riot_user(model: RiotUser) -> discord.Embed:
    embed = BaseBotEmbed.general(name=model.fullname)
    embed.add_field(name="puuid", value=model.puuid, inline=False)
    embed.timestamp = datetime.now()
    return embed


@BotEmbed.register(LOLPlayer)
def format_lol_player(model: LOLPlayer) -> discord.Embed:
    embed = BaseBotEmbed.general(name=None)
    embed.add_field(name="召喚師等級", value=model.summonerLevel, inline=False)
    embed.add_field(name="最後遊玩/修改資料時間", value=model.revisionDate.strftime("%Y/%m/%d %H:%M:%S"), inline=False)
    embed.add_field(name="puuid", value=model.puuid, inline=False)
    try:
        embed.set_thumbnail(url=f"https://ddragon.leagueoflegends.com/cdn/15.10.1/img/profileicon/{model.profileIconId}.png")
    except Exception:
        embed.set_thumbnail(url="https://i.imgur.com/B0TMreW.png")
    embed.set_footer(text="puuid是全球唯一的ID，不隨帳號移動地區而改變")
    return embed


@BotEmbed.register(LOLMatch)
def format_lol_match(model: LOLMatch) -> discord.Embed:
    embed = BaseBotEmbed.simple("LOL對戰")
    gamemode = model.info.gameMode
    embed.add_field(name="遊戲模式", value=gamemode, inline=False)
    embed.add_field(name="對戰ID", value=model.metadata.matchId, inline=False)
    embed.add_field(name="遊戲版本", value=model.info.gameVersion, inline=False)
    minutes = str(model.info.gameDuration // 60)
    seconds = str(model.info.gameDuration % 60)
    embed.add_field(name="遊戲時長", value=f"{minutes}:{seconds}", inline=False)
    blue = "\n".join(player.desplaytext() for player in model.info.participants[:5])
    red = "\n".join(player.desplaytext() for player in model.info.participants[5:10])
    if model.info.teams[0].win:
        embed.add_field(name="藍方👑", value=blue, inline=True)
        embed.add_field(name="紅方", value=red, inline=True)
    else:
        embed.add_field(name="藍方", value=blue, inline=True)
        embed.add_field(name="紅方👑", value=red, inline=True)
    return embed


@BotEmbed.register(LOLActiveMatch)
def format_lol_active_match(model: LOLActiveMatch) -> discord.Embed:
    embed = BaseBotEmbed.simple("LOL對戰")
    embed.add_field(name="遊戲模式", value=model.gameMode, inline=False)
    embed.add_field(name="開始時間", value=f"<t:{str(model.gameStartTime)[:-3]}>", inline=False)
    if model.gameLength <= 0:
        time = "尚未開始"
    else:
        minutes = str(model.gameLength // 60)
        seconds = str(model.gameLength % 60)
        time = f"{minutes}:{seconds}"
    embed.add_field(name="遊戲時長", value=time, inline=False)
    if model.bannedChampions:
        ban_champions = [ban_champion.name for ban_champion in model.bannedChampions]
        embed.add_field(name="禁用角色", value=" ".join(ban_champions), inline=False)
    blue = "\n".join(player.desplaytext() for player in model.participants[:5])
    red = "\n".join(player.desplaytext() for player in model.participants[5:10])
    embed.add_field(name="藍方", value=blue, inline=True)
    embed.add_field(name="紅方", value=red, inline=True)
    return embed


@BotEmbed.register(LOLPlayerRank)
def format_lol_player_rank(model: LOLPlayerRank) -> discord.Embed:
    embed = BaseBotEmbed.simple(Jsondb.lol_jdict["type"].get(model.queueType, model.queueType))
    embed.add_field(name="牌位", value=f"{model.tier} {model.rank}")
    embed.add_field(name="聯盟分數", value=model.leaguePoints)
    embed.add_field(name="勝敗", value=f"{model.wins}/{model.losses} {(round(model.wins / (model.wins + model.losses), 3)) * 100}%")
    return embed


@BotEmbed.register(OsuPlayer)
def format_osu_player(model: OsuPlayer) -> discord.Embed:
    embed = discord.Embed(title="Osu玩家資訊", url=model.url, color=0xC4E9FF)
    embed.add_field(name="名稱", value=model.name)
    embed.add_field(name="id", value=model.id)
    embed.add_field(name="全球排名", value=model.global_rank)
    embed.add_field(name="地區排名", value=model.country_rank)
    embed.add_field(name="pp", value=model.pp)
    embed.add_field(name="國家", value=model.country)
    embed.add_field(name="等級", value=f"{model.level}({model.max_level}%)")
    embed.add_field(name="最多連擊數", value=model.max_combo)
    embed.add_field(name="最後線上", value="Online" if model.is_online else model.last_visit)
    embed.set_thumbnail(url=model.avatar_url)
    return embed


@BotEmbed.register(OsuBeatmap)
def format_osu_beatmap(model: OsuBeatmap) -> discord.Embed:
    embed = discord.Embed(title="Osu圖譜資訊", color=0xC4E9FF)
    embed.add_field(name="名稱", value=model.title)
    embed.add_field(name="歌曲長度(秒)", value=model.time)
    embed.add_field(name="星數", value=model.star)
    embed.add_field(name="模式", value=model.mode)
    embed.add_field(name="combo數", value=model.max_combo)
    embed.add_field(name="圖譜狀態", value=model.status)
    embed.add_field(name="圖譜id", value=model.id)
    embed.add_field(name="圖譜組id", value=model.beatmapset_id)
    embed.add_field(name="通過率", value=model.pass_rate)
    embed.add_field(name="BPM", value=model.bpm)
    embed.add_field(name="網址", value=f"[點我]({model.url})")
    embed.set_image(url=model.cover)
    return embed


@BotEmbed.register(ApexPlayer)
def format_apex_player(model: ApexPlayer) -> discord.Embed:
    embed = discord.Embed(title="Apex玩家資訊", color=0xC4E9FF)
    embed.add_field(name="名稱", value=model.name)
    embed.add_field(name="id", value=model.id)
    embed.add_field(name="平台", value=model.platform)
    embed.add_field(name="等級", value=model.level)
    embed.add_field(name="牌位階級", value=model.rank)
    embed.add_field(name="牌位分數", value=model.rank_score)
    embed.add_field(name="競技場牌位階級", value=model.arena_rank)
    embed.add_field(name="競技場牌位分數", value=model.arena_score)
    embed.add_field(name="目前狀態", value=model.now_state)
    embed.add_field(name="目前ban狀態", value=model.bans["remainingSeconds"] if model.bans["isActive"] else model.bans["isActive"])
    embed.add_field(name="目前選擇角色", value=model.legends_selected_name)
    embed.set_image(url=model.legends_selected_banner)
    return embed


@BotEmbed.register(ApexMapRotation)
def format_apex_map_rotation(model: ApexMapRotation) -> list[discord.Embed]:
    tl: dict = Jsondb.jdict["ApexMap"]
    event_tl: dict = Jsondb.jdict["ApexEvent"]
    now = datetime.now(tz=tz)
    embeds: list[discord.Embed] = []

    if model.ranked is not None:
        embed_rank = BaseBotEmbed.simple("Apex地圖：積分")
        embed_rank.add_field(name="目前地圖", value=tl.get(model.ranked.current.map, model.ranked.current.map))
        embed_rank.add_field(name="開始時間", value=model.ranked.current.start.strftime("%Y/%m/%d %H:%M"))
        embed_rank.add_field(name="結束時間", value=model.ranked.current.end.strftime("%Y/%m/%d %H:%M"))
        embed_rank.add_field(name="下張地圖", value=tl.get(model.ranked.next.map, model.ranked.next.map))
        embed_rank.add_field(name="開始時間", value=model.ranked.next.start.strftime("%Y/%m/%d %H:%M"))
        embed_rank.add_field(name="結束時間", value=model.ranked.next.end.strftime("%Y/%m/%d %H:%M"))
        embed_rank.add_field(name="目前地圖剩餘時間", value=model.ranked.current.remainingTimer)
        embed_rank.set_image(url=model.ranked.current.asset)
        embed_rank.timestamp = now
        embed_rank.set_footer(text="更新時間")
        embeds.append(embed_rank)

    embed_battle_royale = BaseBotEmbed.simple("Apex地圖：大逃殺")
    embed_battle_royale.add_field(name="目前地圖", value=tl.get(model.battle_royale.current.map, model.battle_royale.current.map))
    embed_battle_royale.add_field(name="開始時間", value=model.battle_royale.current.start.strftime("%Y/%m/%d %H:%M"))
    embed_battle_royale.add_field(name="結束時間", value=model.battle_royale.current.end.strftime("%Y/%m/%d %H:%M"))
    embed_battle_royale.add_field(name="下張地圖", value=tl.get(model.battle_royale.next.map, model.battle_royale.next.map))
    embed_battle_royale.add_field(name="開始時間", value=model.battle_royale.next.start.strftime("%Y/%m/%d %H:%M"))
    embed_battle_royale.add_field(name="結束時間", value=model.battle_royale.next.end.strftime("%Y/%m/%d %H:%M"))
    embed_battle_royale.add_field(name="目前地圖剩餘時間", value=model.battle_royale.current.remainingTimer)
    embed_battle_royale.set_image(url=model.battle_royale.current.asset)
    embed_battle_royale.timestamp = now
    embed_battle_royale.set_footer(text="更新時間")
    embeds.append(embed_battle_royale)

    embed_ltm = BaseBotEmbed.simple("Apex地圖：限時模式")
    embed_ltm.add_field(
        name="目前地圖",
        value=f"{event_tl.get(model.ltm.current.eventName, model.ltm.current.eventName)}：{tl.get(model.ltm.current.map, model.ltm.current.map)}",
    )
    embed_ltm.add_field(name="開始時間", value=model.ltm.current.start.strftime("%Y/%m/%d %H:%M"))
    embed_ltm.add_field(name="結束時間", value=model.ltm.current.end.strftime("%Y/%m/%d %H:%M"))
    embed_ltm.add_field(
        name="下張地圖",
        value=f"{event_tl.get(model.ltm.next.eventName, model.ltm.next.eventName)}：{tl.get(model.ltm.next.map, model.ltm.next.map)}",
    )
    embed_ltm.add_field(name="開始時間", value=model.ltm.next.start.strftime("%Y/%m/%d %H:%M"))
    embed_ltm.add_field(name="結束時間", value=model.ltm.next.end.strftime("%Y/%m/%d %H:%M"))
    embed_ltm.add_field(name="目前地圖剩餘時間", value=model.ltm.current.remainingTimer)
    embed_ltm.set_image(url=model.ltm.current.asset)
    embed_ltm.timestamp = now
    embed_ltm.set_footer(text="更新時間")
    embeds.append(embed_ltm)

    return embeds


@BotEmbed.register(SteamUser)
def format_steam_user(model: SteamUser) -> discord.Embed:
    embed = discord.Embed(title=model.personaname, color=0xC4E9FF)
    embed.add_field(name="用戶id", value=model.steamid)
    embed.add_field(name="個人檔案連結", value=f"[點我]({model.profileurl})")
    embed.add_field(name="帳號狀態", value=model._get_persona_state(), inline=True)
    embed.add_field(name="可見性", value=model._get_visibility_state(), inline=True)
    if model.loccountrycode:
        embed.add_field(name="國家", value=model.loccountrycode)
    embed.add_field(name="帳號建立時間", value=f"<t:{model.timecreated}>", inline=False)
    embed.add_field(name="最後離線時間", value=f"<t:{model.lastlogoff}>", inline=False)
    embed.set_thumbnail(url=model.avatarfull)
    return embed


@BotEmbed.register(DBDPlayer)
def format_dbd_player(model: DBDPlayer) -> discord.Embed:
    embed = discord.Embed(title="DBD玩家資訊", color=0xC4E9FF)
    embed.add_field(name="玩家名稱", value=model.name)
    embed.add_field(name="血點數", value=model.bloodpoints)
    embed.add_field(name="倖存者等級", value=model.survivor_rank)
    embed.add_field(name="殺手等級", value=model.killer_rank)
    embed.add_field(name="升階次數", value=model.evilwithintierup)
    embed.add_field(name="完美殺手場次", value=model.killer_perfectgames)
    embed.add_field(name="勞改次數", value=model.cagesofatonement)
    embed.add_field(name="詛咒次數", value=model.condemned)
    embed.add_field(name="獻祭次數", value=model.sacrificed)
    embed.add_field(name="送入夢境數", value=model.dreamstate)
    embed.add_field(name="頭套安裝數", value=model.rbtsplaced)
    embed.add_field(name="鬼影步命中", value=model.blinkattacks)
    embed.add_field(name="電鋸衝刺命中", value=model.chainsawhits)
    embed.add_field(name="電擊命中", value=model.shocked)
    embed.add_field(name="斧頭命中", value=model.hatchetsthrown)
    embed.add_field(name="飛刀命中", value=model.lacerations)
    embed.add_field(name="鎖鏈命中", value=model.possessedchains)
    embed.add_field(name="致命衝刺命中", value=model.lethalrushhits)
    embed.add_field(name="喪鐘襲擊", value=model.uncloakattacks)
    embed.add_field(name="陷阱捕捉", value=model.beartrapcatches)
    embed.add_field(name="汙泥陷阱觸發", value=model.phantasmstriggered)
    return embed


@BotEmbed.register(EarthquakeReport)
def format_earthquake_report(model: EarthquakeReport) -> discord.Embed:
    match model.reportColor:
        case "綠色":
            color = 0x00BB00
        case "橙色":
            color = 0xF75000
        case "黃色":
            color = 0xFFFF37
        case _:
            color = 0xEA0000
    embed = discord.Embed(title="地震報告", description=model.reportContent, color=color, url=model.web)
    if model.is_significant:
        embed.add_field(name="地震編號", value=f"{model.earthquakeNo}")
    else:
        embed.add_field(name="地震編號", value=f"{model.earthquakeNo}（小規模）")
    embed.add_field(name="發生時間", value=model.originTime.strftime("%Y/%m/%d %H:%M:%S"))
    embed.add_field(name="震源深度", value=f"{model.depth} km")
    embed.add_field(name="芮氏規模", value=f"{model.magnitude}")
    embed.add_field(name="震央", value=model.location, inline=False)
    if model.intensity and model.earthquakeNo[3:] != "000":
        for key, value in sorted(model.intensity.items(), key=lambda x: x[0], reverse=True):
            embed.add_field(name=key, value=value, inline=False)
    embed.set_image(url=model.reportImageURI)
    embed.set_footer(text="中央氣象暑")
    embed.timestamp = model.originTime
    return embed


@BotEmbed.register(Forecast)
def format_forecast(model: Forecast) -> discord.Embed:
    embed = BaseBotEmbed.general("天氣預報")
    for data in model.forecast_all:
        text = f"{data['Wx']}\n高低溫:{data['maxT']}/{data['minT']}\n{data['Cl']}"
        embed.add_field(name=data["name"], value=text)
    embed.timestamp = datetime.now()
    embed.set_footer(text=f"{model.timestart}至{model.timeend}")
    return embed


@BotEmbed.register(WeatherWarningReport)
def format_weather_warning_report(model: WeatherWarningReport) -> discord.Embed:
    emoji = weather_warning_emojis.get(model.datasetInfo.datasetDescription, "🚨")
    embed = BaseBotEmbed.general("天氣警特報", title=f"{emoji}{model.datasetInfo.datasetDescription}", description=f"**{model.contents.content.contentText[1:]}**")
    embed.add_field(name="發布時間", value=model.datasetInfo.issueTime.strftime("%Y/%m/%d %H:%M"))
    embed.add_field(name="開始時間", value=model.datasetInfo.validTime.startTime.strftime("%Y/%m/%d %H:%M"))
    embed.add_field(name="結束時間", value=model.datasetInfo.validTime.endTime.strftime("%Y/%m/%d %H:%M"))
    if model.hazardConditions:
        embed.add_field(name="涵蓋區域市", value=", ".join([i.locationName for i in model.hazardConditions.hazards.hazard[0].info.affectedAreas.location]))
    embed.timestamp = datetime.now()
    embed.set_footer(text="中央氣象暑")
    return embed


@BotEmbed.register(TyphoonWarningReport)
def format_typhoon_warning_report(model: TyphoonWarningReport) -> discord.Embed:
    embed = BaseBotEmbed.general("颱風警報", title=model.title, description=model.summary.replace("＊", "\n- "))
    embed.add_field(name="發布時間", value=model.updated.strftime("%Y/%m/%d %H:%M"))
    embed.timestamp = model.updated
    embed.set_footer(text="NCDR")
    return embed


@BotEmbed.register(McssServer)
def format_mcss_server(model: McssServer) -> discord.Embed:
    embed = BaseBotEmbed.simple(model.name, model.description)
    embed.add_field(name="Minecraft類型", value=model.type)
    embed.add_field(name="伺服器狀態", value=f"{model.status.value}（{str(model.status)}）")
    embed.add_field(name="創建日期", value=model.creation_date.strftime("%Y-%m-%d %H:%M:%S"))
    embed.add_field(name="記憶體分配", value=f"{model.java_allocated_memory} MB")
    embed.set_footer(text=f"伺服器ID：{model.server_id}")
    return embed
