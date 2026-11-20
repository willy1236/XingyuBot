"""啟動時比對伺服器加入、離開紀錄要補記的事件。"""

from datetime import datetime, timedelta

from starlib.database.postgresql.models import GuildMembershipEvent
from starlib.guild_membership import GuildSnapshot, reconcile
from starlib.utils import nowtz

NOW = nowtz()
JOINED = NOW - timedelta(days=30)


def guild(guild_id: int, joined_at: datetime | None = JOINED, name: str = "新名字") -> GuildSnapshot:
    return GuildSnapshot(guild_id, name, 10, joined_at)


def last(guild_id: int, event: str, at: datetime = JOINED, name: str = "舊名字") -> GuildMembershipEvent:
    return GuildMembershipEvent(guild_id=guild_id, guild_name=name, event=event, at=at, source="gateway")


def summary(events: list[GuildMembershipEvent]) -> list[tuple[int, str, datetime, str | None]]:
    assert all(e.source == "startup" for e in events)
    return [(e.guild_id, e.event, e.at, e.guild_name) for e in events]


def test_first_run_backfills_joins_with_joined_at():
    assert summary(reconcile([guild(1), guild(2)], {}, NOW)) == [
        (1, "join", JOINED, "新名字"),
        (2, "join", JOINED, "新名字"),
    ]


def test_already_recorded_join_is_left_alone():
    assert reconcile([guild(1)], {1: last(1, "join", JOINED + timedelta(seconds=30))}, NOW) == []


def test_rejoin_after_recorded_leave():
    assert summary(reconcile([guild(1)], {1: last(1, "leave", JOINED - timedelta(days=1))}, NOW)) == [
        (1, "join", JOINED, "新名字"),
    ]


def test_left_and_rejoined_while_offline():
    events = reconcile([guild(1)], {1: last(1, "join", JOINED - timedelta(days=5))}, NOW)
    assert summary(events) == [(1, "leave", JOINED, "舊名字"), (1, "join", JOINED, "新名字")]


def test_left_while_offline():
    assert summary(reconcile([], {1: last(1, "join")}, NOW)) == [(1, "leave", NOW, "舊名字")]


def test_already_recorded_leave_is_left_alone():
    assert reconcile([], {1: last(1, "leave")}, NOW) == []


def test_guild_without_joined_at_is_not_treated_as_left():
    assert reconcile([guild(1, joined_at=None)], {1: last(1, "join")}, NOW) == []
