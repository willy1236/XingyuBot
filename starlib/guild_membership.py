"""bot 加入、離開伺服器的歷史紀錄。

Discord bot 收到加入、離開事件時呼叫 `record`；啟動時呼叫 `sync`，補記離線期間錯過的異動，
第一次啟動時也會把目前所在的伺服器依 bot 的加入時間補成加入紀錄。
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

import discord

from starlib.database import GuildMembershipEvent, sqldb
from starlib.utils import nowtz

type MembershipEvent = Literal["join", "leave"]

#: 事件時間與 bot 在伺服器的 joined_at 之間容許的誤差；超過才視為離線期間重新加入過
_REJOIN_TOLERANCE = timedelta(minutes=1)


@dataclass(frozen=True, slots=True)
class GuildSnapshot:
    """bot 所在的一個伺服器。`joined_at` 是 bot 加入的時間，伺服器暫時不可用時可能是 None。"""

    id: int
    name: str | None
    member_count: int | None
    joined_at: datetime | None

    @classmethod
    def of(cls, guild: discord.Guild) -> GuildSnapshot:
        me = guild.me
        return cls(guild.id, guild.name, guild.member_count, me.joined_at if me else None)


def record(guild: discord.Guild, event: MembershipEvent) -> None:
    """記一筆即時收到的加入或離開。"""
    sqldb.add(
        GuildMembershipEvent(
            guild_id=guild.id,
            guild_name=guild.name,
            event=event,
            member_count=guild.member_count,
            at=nowtz(),
            source="gateway",
        )
    )


def sync(guilds: Iterable[discord.Guild]) -> int:
    """比對目前所在的伺服器與最後一筆紀錄，補記錯過的異動，回傳補記的筆數。可重複呼叫。"""
    latest = {row.guild_id: row for row in sqldb.get_latest_guild_membership_events()}
    events = reconcile([GuildSnapshot.of(g) for g in guilds], latest, nowtz())
    if events:
        sqldb.add_guild_membership_events(events)
    return len(events)


def reconcile(
    guilds: list[GuildSnapshot], latest: dict[int, GuildMembershipEvent], now: datetime
) -> list[GuildMembershipEvent]:
    """算出要補記的事件。

    - 在伺服器裡、沒有紀錄或最後是離開：補加入，時間用 joined_at。
    - 在伺服器裡、最後是加入但 joined_at 比它晚：離線期間離開又回來，補一筆離開再補加入。
    - 不在伺服器裡、最後是加入：補離開，時間是現在。
    joined_at 是 None 的伺服器資料不完整，不動它。
    """
    events: list[GuildMembershipEvent] = []
    present: set[int] = set()
    for guild in guilds:
        present.add(guild.id)
        if guild.joined_at is None:
            continue
        last = latest.get(guild.id)
        if last is not None and last.event == "join":
            if guild.joined_at - last.at <= _REJOIN_TOLERANCE:
                continue
            events.append(_startup_event(guild.id, last.guild_name, "leave", None, guild.joined_at))
        events.append(_startup_event(guild.id, guild.name, "join", guild.member_count, guild.joined_at))

    for guild_id, last in latest.items():
        if guild_id not in present and last.event == "join":
            events.append(_startup_event(guild_id, last.guild_name, "leave", None, now))
    return events


def _startup_event(
    guild_id: int, name: str | None, event: MembershipEvent, member_count: int | None, at: datetime
) -> GuildMembershipEvent:
    return GuildMembershipEvent(
        guild_id=guild_id, guild_name=name, event=event, member_count=member_count, at=at, source="startup"
    )
