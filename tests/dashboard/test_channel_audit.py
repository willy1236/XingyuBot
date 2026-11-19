"""實況主後台的擋下紀錄端點（W-04）：只有該頻道的擁有者看得到，最近 20 筆（真實 PostgreSQL）。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from starServer.dashboard import channel_audit
from tests.helpers.dashboard_auth import make_app, make_session, make_twitch_session

pytestmark = pytest.mark.usefixtures("dashboard_env")

CHANNEL_ID = 2000000051


@pytest.fixture(autouse=True)
def _db(monkeypatch, repo):
    monkeypatch.setattr(channel_audit, "sqldb", repo)


def client_for(session_id: str) -> TestClient:
    c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False)
    c.cookies.set("dashboard_session", session_id)
    return c


def test_列出最近_20_筆_新的在前(repo):
    for i in range(25):
        repo.add_twitch_automod_block(CHANNEL_ID, "command", "hi", f"t{i}", "automod")
    repo.add_twitch_automod_block(CHANNEL_ID + 1, "timer", "1", "別人的", "automod")
    sid = make_twitch_session(repo, twitch_id=str(CHANNEL_ID))

    r = client_for(sid).get(f"/dashboard/channels/{CHANNEL_ID}/automod-blocks")

    assert r.status_code == 200
    blocks = r.json()["blocks"]
    assert [b["text"] for b in blocks] == [f"t{i}" for i in range(24, 4, -1)]
    assert set(blocks[0]) == {"id", "at", "source_kind", "source_key", "text", "reason"}
    assert (blocks[0]["source_kind"], blocks[0]["source_key"], blocks[0]["reason"]) == ("command", "hi", "automod")


def test_沒有紀錄回空清單(repo):
    sid = make_twitch_session(repo, twitch_id=str(CHANNEL_ID))
    r = client_for(sid).get(f"/dashboard/channels/{CHANNEL_ID}/automod-blocks")
    assert r.status_code == 200 and r.json() == {"blocks": []}


def test_看不到別的頻道(repo):
    sid = make_twitch_session(repo, twitch_id=str(CHANNEL_ID))
    r = client_for(sid).get(f"/dashboard/channels/{CHANNEL_ID + 1}/automod-blocks")
    assert r.status_code == 403 and r.json() == {"error": "channel_forbidden"}


def test_沒登入回_401():
    r = client_for("nope").get(f"/dashboard/channels/{CHANNEL_ID}/automod-blocks")
    assert r.status_code == 401


def test_只有_Discord_身分沒有任何頻道(repo):
    r = client_for(make_session(repo)).get(f"/dashboard/channels/{CHANNEL_ID}/automod-blocks")
    assert r.status_code == 403
