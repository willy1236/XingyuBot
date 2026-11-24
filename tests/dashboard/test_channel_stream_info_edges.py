"""C-09 實況資訊端點的邊界：沒有變動、長度上限、Twitch 失敗。驗收情境見 test_channel_stream_info.py。"""

import httpx
import pytest

from tests.dashboard.test_channel_stream_info import (  # noqa: F401 (fixtures)
    MINECRAFT,
    NEW_TITLE,
    OLD_GAME,
    OLD_TITLE,
    audit_entries,
    channel_id,
    host,
    save,
    twitch,
)

pytestmark = pytest.mark.usefixtures("dashboard_env")


def test_只改標題時只送標題_紀錄只有標題變動(host, twitch):
    assert save(host, category_id=OLD_GAME[0]).is_success

    assert twitch.patches() == [{"broadcaster_id": twitch.requests[-2][2]["broadcaster_id"], "title": NEW_TITLE}]
    (entry,) = audit_entries(host)
    assert entry["before"]["title"] == OLD_TITLE and entry["after"]["title"] == NEW_TITLE
    assert entry["before"]["game_id"] == entry["after"]["game_id"] == OLD_GAME[0]


def test_標題與分類都沒變不呼叫修改也不寫紀錄(host, twitch):
    assert save(host, title=OLD_TITLE, category_id=OLD_GAME[0]).is_success

    assert twitch.patches() == []
    assert audit_entries(host) == []


def test_標題超過_140_字回_400_不改_Twitch(host, twitch):
    assert save(host, title="字" * 141).status_code == 400
    assert twitch.patches() == []


def test_Twitch_回錯誤時回_502_twitch_failed_不寫紀錄(host, twitch, monkeypatch):
    twitch.categories["x"] = [MINECRAFT]

    async def fail(_client, request, **_kwargs):
        return httpx.Response(500, request=request) if request.method == "PATCH" else twitch.send(request)

    monkeypatch.setattr(httpx.AsyncClient, "send", fail)

    response = save(host)

    assert (response.status_code, response.json()["error"]) == (502, "twitch_failed")
    assert audit_entries(host) == []
