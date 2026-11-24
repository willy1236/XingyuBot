"""C-06：執法紀錄超過 30 天後由排程清除。"""

from datetime import timedelta

from starlib import twitch_enforcement
from starlib.database import TwitchEnforcementLog
from starlib.utils import nowtz

CHANNEL = 2130000001


def add_log(repo, days: int, message: str) -> None:
    repo.add(
        TwitchEnforcementLog(
            twitch_id=CHANNEL,
            at=nowtz() - timedelta(days=days),
            user_id=1,
            user_login="alice",
            user_name="Alice",
            filter="link",
            strike=1,
            action="delete",
            message=message,
            status="ok",
        )
    )


def test_清除只刪除超過_30_天的紀錄(monkeypatch, repo):
    monkeypatch.setattr(twitch_enforcement, "sqldb", repo)
    add_log(repo, 31, "太舊")
    add_log(repo, 29, "還在")
    repo.session.flush()

    assert twitch_enforcement.purge_expired() >= 1

    remaining = twitch_enforcement.list_page(repo.session, CHANNEL)
    assert [row.message for row in remaining] == ["還在"]
    assert twitch_enforcement.purge_expired() == 0
