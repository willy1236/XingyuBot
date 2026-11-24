"""C-06：bot owner 在營運入口查看各頻道的執法紀錄。"""

from datetime import timedelta

import pytest

from starlib.database import TwitchEnforcementLog
from starlib.utils import nowtz
from tests.dashboard.test_ops import (
    BASE,
    CHANNEL_ID,
    OTHER_ID,
    _clean_channels,  # noqa: F401 (autouse fixture)
    add_channel,
    client_for,
    owner,  # noqa: F401 (fixture)
    spy,  # noqa: F401 (fixture)
)
from tests.helpers.dashboard_auth import make_session, make_twitch_session

pytestmark = pytest.mark.usefixtures("dashboard_env")


def log_row(repo, twitch_id, **fields):
    values = {
        "twitch_id": twitch_id,
        "at": nowtz(),
        "user_id": 2000000971,
        "user_login": "alice",
        "user_name": "Alice",
        "filter": "link",
        "strike": 1,
        "action": "timeout",
        "duration": 600,
        "message": "abc.com",
        "status": "ok",
    }
    repo.add(TwitchEnforcementLog(**{**values, **fields}))
    repo.session.flush()


def rows_of(response):
    assert response.status_code == 200, response.text
    lists = [value for value in response.json().values() if isinstance(value, list)]
    assert len(lists) == 1, response.json()
    return lists[0]


def test_bot_owner_看得到頻道的執法紀錄(owner, repo):
    add_channel(repo)
    add_channel(repo, OTHER_ID)
    log_row(repo, CHANNEL_ID, message="本頻道", strike=2, status="failed")
    log_row(repo, OTHER_ID, message="別的頻道")

    (row,) = rows_of(owner.get(f"{BASE}/{CHANNEL_ID}/enforcement"))

    assert (row["message"], row["user_login"], row["filter"], row["strike"], row["action"], row["status"]) == (
        "本頻道",
        "alice",
        "link",
        2,
        "timeout",
        "failed",
    )


def test_停用的頻道也看得到執法紀錄(owner, repo):
    add_channel(repo, state="disabled")
    log_row(repo, CHANNEL_ID)
    assert len(rows_of(owner.get(f"{BASE}/{CHANNEL_ID}/enforcement"))) == 1


def test_每頁_50_筆新的在前並排除超過_30_天的紀錄(owner, repo):
    add_channel(repo)
    base = nowtz() - timedelta(hours=1)
    for index in range(55):
        log_row(repo, CHANNEL_ID, at=base + timedelta(seconds=index), message=f"m{index}")
    log_row(repo, CHANNEL_ID, at=nowtz() - timedelta(days=31), message="太舊")

    first = rows_of(owner.get(f"{BASE}/{CHANNEL_ID}/enforcement"))
    second = rows_of(owner.get(f"{BASE}/{CHANNEL_ID}/enforcement", params={"offset": 50}))

    assert [row["message"] for row in first] == [f"m{index}" for index in range(54, 4, -1)]
    assert [row["message"] for row in second] == [f"m{index}" for index in range(4, -1, -1)]


def test_不是_bot_owner_看不到(repo, spy):
    add_channel(repo)
    log_row(repo, CHANNEL_ID)
    spy.owners.clear()

    discord = client_for(make_session(repo)).get(f"{BASE}/{CHANNEL_ID}/enforcement")
    twitch = client_for(make_twitch_session(repo)).get(f"{BASE}/{CHANNEL_ID}/enforcement")

    assert [(r.status_code, r.json().get("error")) for r in (discord, twitch)] == [(403, "not_bot_owner")] * 2
