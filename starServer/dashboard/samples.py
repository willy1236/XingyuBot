"""通知範例內容：後台預覽（T-05）與測試通知（T-08）共用的產生器。

文字的組法照現有發送端，預設文字從那裡複製過來，發送端本身不動：
- 頻道通知：`bot.py` 的 send_notify_channel，「預設文字 + 空格 + 提及」。
- 社群推播：`bot.py` 的 send_notify_communities，「提及 + 空格 + 文字」，再接 additional_content。
- 全群公告與機器人更新：`owner.py`，只送提及。
- 成員加入、離開：`bot_event.py`。
卡片一律是固定的範例資料，不呼叫外部平台 API。
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Protocol

import discord

from starlib.database import NotifyChannelType, NotifyCommunityType
from starlib.fileDatabase import Jsondb
from starlib.utils import BotEmbed

from .notify_fields import NotifySpec, parse_key

#: 沒有傳入成員時用的範例成員。預覽元件把這個提及顯示成「@範例成員」
SAMPLE_MEMBER_ID = 100000000000000000
SAMPLE_MEMBER_MENTION = f"<@{SAMPLE_MEMBER_ID}>"
SAMPLE_MEMBER_NAME = "範例成員"
SAMPLE_TWEET_URL = "https://x.com/example/status/0"

_TZ = timezone(timedelta(hours=8))


class MemberLike(Protocol):
    mention: str
    name: str
    discriminator: str


class GuildLike(Protocol):
    name: str


@dataclass
class SampleMessage:
    #: 已經把身分組提及放在正確位置的最終文字
    content: str
    embeds: list[discord.Embed] = field(default_factory=list)
    #: 只給 allowed_mentions 與預覽標示使用，呼叫端不再自己組文字
    mention_role_id: int | None = None


def _now() -> datetime:
    return datetime.now(_TZ)


def _picture(key: str) -> str | None:
    try:
        return Jsondb.get_picture(key)
    except KeyError:
        return None


# ====== 固定的範例卡片 ======
def _radio_embed(author: str) -> discord.Embed:
    embed = discord.Embed(description="這是一則範例公告。", color=0xC4E9FF, timestamp=_now())
    embed.set_author(name=author, icon_url=_picture("radio_001"))
    embed.set_footer(text="Bot Radio System")
    return embed


def _quake_embed(significant: bool) -> discord.Embed:
    embed = discord.Embed(
        title="地震報告",
        description="01/01-12:00左右發生顯著有感地震，最大震度4級。",
        color=0x00BB00,
        url="https://www.cwa.gov.tw/V8/C/E/index.html",
        timestamp=_now(),
    )
    embed.add_field(name="地震編號", value="000" if significant else "000（小規模）")
    embed.add_field(name="發生時間", value=_now().strftime("%Y/%m/%d %H:%M:%S"))
    embed.add_field(name="震源深度", value="10.0 km")
    embed.add_field(name="芮氏規模", value="5.0")
    embed.add_field(name="震央", value="範例縣範例鄉（位於範例縣政府東方 10.0 公里）", inline=False)
    embed.add_field(name="範例縣", value="4級", inline=False)
    embed.set_footer(text="中央氣象暑")
    return embed


def _weather_warning_embed() -> discord.Embed:
    embed = BotEmbed.general("天氣警特報", title="🌧️大雨特報", description="**範例縣市：有局部大雨發生的機率。**")
    embed.add_field(name="發布時間", value=_now().strftime("%Y/%m/%d %H:%M"))
    embed.add_field(name="開始時間", value=_now().strftime("%Y/%m/%d %H:%M"))
    embed.add_field(name="結束時間", value=(_now() + timedelta(hours=12)).strftime("%Y/%m/%d %H:%M"))
    embed.add_field(name="涵蓋區域市", value="範例縣, 範例市")
    embed.timestamp = _now()
    embed.set_footer(text="中央氣象暑")
    return embed


def _forecast_embed() -> discord.Embed:
    embed = BotEmbed.general("天氣預報")
    for name, wx in (("今日白天", "多雲"), ("今晚明晨", "晴"), ("明日白天", "陰短暫雨")):
        embed.add_field(name=name, value=f"{wx}\n高低溫:28/22\n舒適")
    embed.timestamp = _now()
    embed.set_footer(text="範例時間至範例時間")
    return embed


def _apex_embeds() -> list[discord.Embed]:
    embeds = []
    for title in ("Apex地圖：積分", "Apex地圖：大逃殺"):
        embed = BotEmbed.simple(title)
        embed.add_field(name="目前地圖", value="範例地圖")
        embed.add_field(name="開始時間", value=f"<t:{int(_now().timestamp())}:t>")
        embed.add_field(name="結束時間", value=f"<t:{int((_now() + timedelta(hours=1)).timestamp())}:t>")
        embed.add_field(name="下張地圖", value="下一張範例地圖")
        embed.add_field(name="目前地圖剩餘時間", value=f"<t:{int((_now() + timedelta(hours=1)).timestamp())}:R>")
        embed.timestamp = _now()
        embed.set_footer(text="更新時間")
        embeds.append(embed)
    return embeds


def _join_log_embed(member: MemberLike) -> discord.Embed:
    embed = BotEmbed.general(
        name=member.name, title="成員加入", description=f"{member.mention} 加入了伺服器\n第 42 位成員"
    )
    embed.timestamp = _now()
    embed.set_footer(text=f"ID: {SAMPLE_MEMBER_ID}")
    return embed


def _leave_log_embed(member: MemberLike) -> discord.Embed:
    embed = BotEmbed.general(
        name=member.name, title="成員離開", description=f"{member.mention} 離開了伺服器\n加入時長：30 days, 0:00:00"
    )
    embed.timestamp = _now()
    embed.set_footer(text=f"ID: {SAMPLE_MEMBER_ID}")
    return embed


def _voice_log_embed(member: MemberLike, guild: GuildLike) -> discord.Embed:
    embed = discord.Embed(description=f"{member.mention} 進入語音", color=0x4AA0B5, timestamp=_now())
    embed.add_field(name="頻道", value="範例語音頻道", inline=False)
    embed.set_author(name=member.name)
    embed.set_footer(text=guild.name)
    return embed


def _twitch_live_embed() -> discord.Embed:
    embed = discord.Embed(
        title="範例實況標題",
        url="https://www.twitch.tv/example",
        description="範例遊戲",
        color=0x6441A5,
        timestamp=_now(),
    )
    embed.set_author(name="範例實況主 開台啦！", icon_url=_picture("twitch_001"))
    embed.add_field(name="標籤", value="繁體中文, 範例")
    embed.set_footer(text="開始於")
    return embed


def _twitch_video_embed() -> discord.Embed:
    embed = discord.Embed(
        title="範例影片標題",
        url="https://www.twitch.tv/videos/1",
        description="範例影片說明",
        color=0x6441A5,
        timestamp=_now(),
    )
    embed.set_author(name="範例實況主", icon_url=_picture("twitch_001"))
    embed.set_footer(text="上傳時間")
    return embed


def _twitch_clip_embed() -> discord.Embed:
    embed = discord.Embed(title="範例剪輯標題", url="https://clips.twitch.tv/example", color=0x6441A5, timestamp=_now())
    embed.set_author(name="範例實況主", icon_url=_picture("twitch_001"))
    embed.add_field(name="剪輯者", value="範例剪輯者")
    embed.set_footer(text="上傳時間")
    return embed


def _youtube_embed() -> discord.Embed:
    embed = discord.Embed(
        title="範例影片標題",
        url="https://www.youtube.com/watch?v=example",
        description="範例頻道",
        color=0xFF0000,
        timestamp=_now(),
    )
    embed.add_field(name="上傳時間", value=_now().strftime("%Y/%m/%d %H:%M:%S"), inline=False)
    return embed


# ====== 預設文字（現有發送端的寫法） ======
def _username(member: MemberLike) -> str:
    return member.name if member.discriminator == "0" else f"{member.name}#{member.discriminator}"


def _member_text(spec: NotifySpec, message: str | None, member: MemberLike, guild: GuildLike) -> str:
    if message:
        return message.replace("{member}", member.mention).replace("{guild}", guild.name)
    if spec.channel_type == NotifyChannelType.MemberJoin:
        return f"{member.mention} ({_username(member)}) 加入了我們"
    return f"{member.mention} ({_username(member)}) 離開了我們"


#: 頻道通知的預設文字（task.py）；沒列的種類沒有預設文字
_CHANNEL_DEFAULT_TEXT: dict[NotifyChannelType, str] = {
    NotifyChannelType.MajorQuakeNotifications: "顯著有感地震報告",
    NotifyChannelType.SlightQuakeNotifications: "小區域地震報告",
    NotifyChannelType.WeatherForecast: "6小時天氣預報",
}

_CHANNEL_EMBEDS: dict[NotifyChannelType, Callable[[], list[discord.Embed]]] = {
    NotifyChannelType.AllAnnouncements: lambda: [_radio_embed("機器人全群公告")],
    NotifyChannelType.BotUpdates: lambda: [_radio_embed("機器人更新通知")],
    NotifyChannelType.MajorQuakeNotifications: lambda: [_quake_embed(True)],
    NotifyChannelType.SlightQuakeNotifications: lambda: [_quake_embed(False)],
    NotifyChannelType.WeatherWarning: lambda: [_weather_warning_embed()],
    NotifyChannelType.WeatherForecast: lambda: [_forecast_embed()],
    NotifyChannelType.ApexRotation: _apex_embeds,
}

_COMMUNITY_EMBEDS: dict[NotifyCommunityType, Callable[[], discord.Embed]] = {
    NotifyCommunityType.TwitchLive: _twitch_live_embed,
    NotifyCommunityType.TwitchVideo: _twitch_video_embed,
    NotifyCommunityType.TwitchClip: _twitch_clip_embed,
    NotifyCommunityType.Youtube: _youtube_embed,
}


@dataclass
class _SampleMember:
    mention: str = SAMPLE_MEMBER_MENTION
    name: str = SAMPLE_MEMBER_NAME
    discriminator: str = "0"


def _role_mention(role_id: int) -> str:
    return f"<@&{role_id}>"


def _channel_sample(spec: NotifySpec, values: dict, member: MemberLike, guild: GuildLike) -> SampleMessage:
    kind = spec.channel_type
    role_id = _int_or_none(values.get("role_id")) if spec.has_role else None
    message = values.get("message") if spec.has_message else None
    match kind:
        case NotifyChannelType.MemberJoin | NotifyChannelType.MemberLeave:
            return SampleMessage(_member_text(spec, message, member, guild))
        case NotifyChannelType.JoinLog:
            return SampleMessage("", [_join_log_embed(member)])
        case NotifyChannelType.LeaveLog:
            return SampleMessage("", [_leave_log_embed(member)])
        case NotifyChannelType.VoiceLog:
            return SampleMessage("", [_voice_log_embed(member, guild)])

    default = _CHANNEL_DEFAULT_TEXT.get(kind)
    if role_id is not None:
        mention = _role_mention(role_id)
        content = f"{default} {mention}" if default is not None else mention
    else:
        content = default or ""
    return SampleMessage(content, _CHANNEL_EMBEDS[kind](), role_id)


def _community_sample(spec: NotifySpec, values: dict) -> SampleMessage:
    kind = spec.community_type
    role_id = _int_or_none(values.get("role_id")) if spec.has_role else None
    message = values.get("message") if spec.has_message else None
    if kind == NotifyCommunityType.TwitterTweet:
        # task.py：沒有卡片，預設文字之後換行接推文網址
        default_content, additional = "範例使用者 發布新推文", SAMPLE_TWEET_URL
    else:
        default_content, additional = None, None

    text = message or default_content
    if role_id is not None:
        mention = _role_mention(role_id)
        text = f"{mention} {text}" if text is not None else mention
    if additional:
        text = additional if text is None else f"{text}\n{additional}"

    embeds = [_COMMUNITY_EMBEDS[kind]()] if kind in _COMMUNITY_EMBEDS else []
    return SampleMessage(text or "", embeds, role_id)


def _int_or_none(value: object) -> int | None:
    return None if value is None or value == "" else int(value)  # pyright: ignore[reportArgumentType]


def build_sample(
    notify_type: str, values: dict, *, member: MemberLike | None = None, guild: GuildLike
) -> SampleMessage:
    """依通知種類與設定值產生範例訊息。

    Args:
        notify_type: 字串種類鍵，例如 `channel:7`、`community:1`。
        values: 表單的欄位值（`role_id`、`message`）；只採用欄位對照表中該種類打勾的欄位，其他一律忽略。
        member: 成員加入、離開與紀錄類用的成員；不傳入就用範例成員。
        guild: 提供 `{guild}` 與語音紀錄 footer 用的伺服器名稱。

    Raises:
        KeyError: notify_type 不是有效的種類鍵。
        ValueError: role_id 不是整數。
    """
    spec = parse_key(notify_type)
    if spec.kind == "channel":
        return _channel_sample(spec, values, member or _SampleMember(), guild)
    return _community_sample(spec, values)
