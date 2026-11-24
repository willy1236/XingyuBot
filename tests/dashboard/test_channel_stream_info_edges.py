"""C-09 實況資訊端點的邊界：沒有變動、長度上限、Twitch 失敗。驗收情境見 test_channel_stream_info.py。"""

import httpx
import pytest

from starlib import twitch_tokens
from starlib.messaging import cache_invalidation
from starServer.dashboard import twitch_control
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
    assert host.put("stream-info", json={"title": NEW_TITLE}).is_success

    assert twitch.patches() == [{"broadcaster_id": twitch.requests[-2][2]["broadcaster_id"], "title": NEW_TITLE}]
    (entry,) = audit_entries(host)
    assert entry["before"]["title"] == OLD_TITLE and entry["after"]["title"] == NEW_TITLE
    assert entry["before"]["game_id"] == entry["after"]["game_id"] == OLD_GAME[0]


def test_partial_update_accepts_missing_existing_fields_and_skips_post_patch_lookup(host, twitch, channel_id):
    twitch.game_id = twitch.game_name = ""
    assert host.put("stream-info", json={"title": NEW_TITLE}).status_code == 204
    assert [method for method, _, _ in twitch.requests] == ["GET", "PATCH"]
    cache_invalidation.invalidate.assert_called_once_with("twitch_stream_info", str(channel_id))
    (entry,) = audit_entries(host)
    assert entry["target_key"] == "stream"
    assert entry["after"] == {"title": NEW_TITLE, "game": "", "game_id": ""}


def test_partial_category_update_accepts_empty_existing_title(host, twitch):
    twitch.title = ""
    assert host.put("stream-info", json={"category_id": MINECRAFT[0]}).status_code == 204
    assert [method for method, _, _ in twitch.requests] == ["GET", "GET", "PATCH"]
    assert twitch.title == "" and twitch.game_id == MINECRAFT[0]


def test_empty_update_request_is_rejected(host, twitch):
    assert host.put("stream-info", json={}).status_code == 400
    assert twitch.requests == []


def test_scope_is_checked_again_after_token_refresh(host, twitch, monkeypatch):
    granted = True

    async def refreshed_credentials(_):
        nonlocal granted
        granted = False
        return "refreshed", "client-id"

    monkeypatch.setattr(twitch_control, "broadcaster_credentials", refreshed_credentials)
    monkeypatch.setattr(twitch_tokens, "stream_info_granted", lambda _: granted)

    response = host.put("stream-info", json={"title": NEW_TITLE})

    assert response.status_code == 409
    assert response.json()["error"] == "scope_missing"
    assert twitch.requests == []


def test_標題與分類都沒變不呼叫修改也不寫紀錄(host, twitch):
    assert save(host, title=OLD_TITLE, category_id=OLD_GAME[0]).is_success

    assert twitch.patches() == []
    assert audit_entries(host) == []
    cache_invalidation.invalidate.assert_not_called()


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
    cache_invalidation.invalidate.assert_not_called()
