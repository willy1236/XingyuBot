"""C-09：實況主與 mod 在後台查看與修改實況資訊（標題、分類）。

web 端點用實況主 token 直接打 Helix（`GET /channels`、`GET /streams`、`PATCH /channels`、`GET /search/categories`），
Helix 在 HTTP 層以有狀態的替身取代（`httpx.AsyncClient.send`，同 `test_channel_regulars.py`）。
卡片只定了端點、`can_edit`、`scope_missing` 與 PUT 的 `{title, category_id}`，其餘回應欄位名稱沒定，測試只比對內容有沒有出現在回應裡。
"""

import json
from datetime import UTC, datetime, timedelta
from importlib import import_module
from importlib.util import find_spec
from unittest.mock import AsyncMock, Mock
from zlib import crc32

import httpx
import pytest
from fastapi.testclient import TestClient

from starlib import twitch_audit, twitch_commands, twitch_tokens
from starlib.database import APIType, OAuthToken, TwitchBotJoinChannel
from starlib.messaging import cache_invalidation
from starServer.dashboard import channel_settings, channels, twitch_control
from tests.helpers.dashboard_auth import FRONTEND, make_app, make_twitch_session

pytestmark = pytest.mark.usefixtures("dashboard_env")

MOD = "2000000972"
SCOPE = "channel:manage:broadcast"
OLD_TITLE = "原本的標題"
OLD_GAME = ("509658", "Just Chatting")
NEW_TITLE = "新標題 abc"
MINECRAFT = ("27471", "Minecraft")
STARTED = "2026-11-24T03:04:05Z"


class StubHelix:
    """Helix `channels`（GET／PATCH）、`streams`、`search/categories` 的替身；頻道的標題與分類存在記憶體。"""

    def __init__(self):
        self.title = OLD_TITLE
        self.game_id, self.game_name = OLD_GAME
        self.live_since: str | None = None
        self.categories: dict[str, list[tuple[str, str]]] = {}
        self.requests: list[tuple[str, str, dict]] = []

    def patches(self):
        return [params for method, _, params in self.requests if method == "PATCH"]

    def send(self, request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        if request.content:
            params.update(json.loads(request.content))
        self.requests.append((request.method, request.url.path, params))
        path = request.url.path
        if request.method == "PATCH" and path.endswith("/channels"):
            if "title" in params:
                self.title = params["title"]
            if "game_id" in params:
                self.game_id = params["game_id"]
                self.game_name = next(
                    (n for found in self.categories.values() for i, n in found if i == self.game_id), self.game_name
                )
            return httpx.Response(204, request=request)
        if path.endswith("/search/categories"):
            found = self.categories.get(params["query"], [])
            data = [{"id": i, "name": n, "box_art_url": ""} for i, n in found]
            return httpx.Response(200, json={"data": data}, request=request)
        if path.endswith("/streams"):
            data = []
            if self.live_since:
                data = [
                    {
                        "id": "1",
                        "user_id": params.get("user_id", ""),
                        "type": "live",
                        "title": self.title,
                        "game_id": self.game_id,
                        "game_name": self.game_name,
                        "started_at": self.live_since,
                    }
                ]
            return httpx.Response(200, json={"data": data}, request=request)
        if path.endswith("/channels"):
            channel = {
                "broadcaster_id": params.get("broadcaster_id", ""),
                "broadcaster_login": "host",
                "broadcaster_name": "Host",
                "broadcaster_language": "zh",
                "game_id": self.game_id,
                "game_name": self.game_name,
                "title": self.title,
                "delay": 0,
                "tags": [],
                "content_classification_labels": [],
                "is_branded_content": False,
            }
            return httpx.Response(200, json={"data": [channel]}, request=request)
        raise AssertionError(f"沒預期的 Helix 呼叫：{request.method} {path}")


@pytest.fixture
def channel_id(request):
    return 2120000000 + crc32(request.node.nodeid.encode()) % 10000000


def seed_token(repo, channel_id, scope):
    credential = repo.get_oauth_client(APIType.Twitch, twitch_tokens.BROADCASTER_CLIENT_SEQ).credential_id
    repo.merge(
        OAuthToken(
            user_id=str(channel_id),
            client_credential_id=credential,
            access_token="broadcaster-token",
            refresh_token="refresh",
            scope=scope,
            expires_at=datetime.now(UTC) + timedelta(hours=2),
        )
    )


@pytest.fixture
def twitch(monkeypatch):
    stub = StubHelix()

    async def send(_client, request, **_kwargs):
        return stub.send(request)

    monkeypatch.setattr(httpx.AsyncClient, "send", send)
    return stub


@pytest.fixture
def host(monkeypatch, repo, channel_id, twitch):
    for module in (channel_settings, channels, twitch_audit, twitch_commands, twitch_tokens):
        monkeypatch.setattr(module, "sqldb", repo)
    for name in ("starlib.twitch_stream_info", "starServer.dashboard.channel_stream_info"):
        if find_spec(name) is not None and hasattr(module := import_module(name), "sqldb"):
            monkeypatch.setattr(module, "sqldb", repo)
    repo.add(TwitchBotJoinChannel(twitch_id=channel_id, state="enabled"))
    seed_token(repo, channel_id, [*twitch_tokens.ENABLE_SCOPES, SCOPE])
    monkeypatch.setattr(cache_invalidation, "invalidate", Mock())
    monkeypatch.setattr(twitch_tokens, "broadcaster_token_blocking", lambda _: "test-broadcaster-token")
    monkeypatch.setattr(twitch_control, "check_template", AsyncMock(return_value="ok"))
    sid = make_twitch_session(repo, twitch_id=str(channel_id), login="host", name="Host")
    client = TestClient(
        make_app(), base_url=f"https://testserver/dashboard/channels/{channel_id}/", headers={"Origin": FRONTEND}
    )
    client.cookies.set("dashboard_session", sid)
    return client


def grant_only_enable_scopes(repo, channel_id):
    """模擬沒有重新授權的既有頻道：token 沒有 `channel:manage:broadcast`。"""
    seed_token(repo, channel_id, list(twitch_tokens.ENABLE_SCOPES))


def audit_entries(host):
    return [entry for entry in host.get("audit").json()["entries"] if entry["target_kind"] == "stream_info"]


def save(host, title=NEW_TITLE, category_id=MINECRAFT[0]):
    return host.put("stream-info", json={"title": title, "category_id": category_id})


# ---- 查看 ----


def test_沒開台時顯示目前標題與分類_不顯示開台時間(host, twitch):
    response = host.get("stream-info")

    assert response.status_code == 200, response.text
    assert OLD_TITLE in str(response.json())
    assert OLD_GAME[1] in str(response.json())
    assert "03:04:05" not in str(response.json())


def test_開台中顯示開始時間_與沒開台的回應不同(host, twitch):
    offline = host.get("stream-info").json()
    twitch.live_since = STARTED

    response = host.get("stream-info")

    assert response.status_code == 200, response.text
    assert "03:04:05" in str(response.json())
    assert response.json() != offline


def test_有改標題權限時_can_edit_為_True(host):
    assert host.get("stream-info").json()["can_edit"] is True


def test_每次載入都向_Twitch_取最新資訊(host, twitch):
    assert OLD_TITLE in str(host.get("stream-info").json())
    twitch.title = "在 Twitch 後台改的"
    assert "在 Twitch 後台改的" in str(host.get("stream-info").json())


# ---- 搜尋分類 ----


def test_搜尋分類回傳符合的分類名稱與_id(host, twitch):
    twitch.categories["mine"] = [MINECRAFT, ("1", "Minecraft Dungeons")]

    response = host.get("stream-info/categories", params={"q": "mine"})

    assert response.status_code == 200, response.text
    body = str(response.json())
    assert all(token in body for token in (MINECRAFT[0], MINECRAFT[1], "Minecraft Dungeons"))


def test_搜尋不到分類回_200_空結果(host, twitch):
    response = host.get("stream-info/categories", params={"q": "不存在的分類"})

    assert response.status_code == 200, response.text
    assert MINECRAFT[1] not in str(response.json())


# ---- 修改 ----


def test_在後台改標題與分類後_Twitch_立即生效並記來源是後台(host, twitch):
    twitch.categories["mine"] = [MINECRAFT]

    response = save(host)

    assert response.is_success, response.text
    assert (twitch.title, twitch.game_id) == (NEW_TITLE, MINECRAFT[0])
    assert NEW_TITLE in str(host.get("stream-info").json())
    (entry,) = audit_entries(host)
    assert (entry["source"], entry["action"]) == ("dashboard", "update")
    assert OLD_TITLE in str(entry["before"]) and NEW_TITLE in str(entry["after"])
    assert OLD_GAME[1] in str(entry["before"]) and MINECRAFT[1] in str(entry["after"])


# ---- 既有頻道沒有重新授權 ----


def test_沒有重新授權時頁面照常顯示_但_can_edit_為_False(host, repo, channel_id):
    grant_only_enable_scopes(repo, channel_id)

    response = host.get("stream-info")

    assert response.status_code == 200, response.text
    assert OLD_TITLE in str(response.json())
    assert response.json()["can_edit"] is False


def test_沒有重新授權時修改回_409_scope_missing_且不改_Twitch_不寫紀錄(host, twitch, repo, channel_id):
    grant_only_enable_scopes(repo, channel_id)

    response = save(host)

    assert (response.status_code, response.json()["error"]) == (409, "scope_missing")
    assert twitch.patches() == []
    assert twitch.title == OLD_TITLE
    assert audit_entries(host) == []


def test_實況主重新授權後可以修改(host, twitch, repo, channel_id):
    grant_only_enable_scopes(repo, channel_id)
    assert save(host).status_code == 409

    seed_token(repo, channel_id, [*twitch_tokens.ENABLE_SCOPES, SCOPE])

    assert host.get("stream-info").json()["can_edit"] is True
    assert save(host).is_success
    assert twitch.title == NEW_TITLE


# ---- mod ----


def mod_client(host, repo):
    client = TestClient(make_app(), base_url=host.base_url, headers={"Origin": FRONTEND})
    sid = make_twitch_session(repo, twitch_id=MOD, session_id="stream-info-mod", login="mod", name="Mod")
    client.cookies.set("dashboard_session", sid)
    return client


def test_mod_協作開啟時能查看與修改_紀錄的操作者是_mod(host, twitch, repo, twitch_mods, channel_id):
    twitch_mods.set(channel_id, (MOD, "Mod"))
    mod = mod_client(host, repo)

    assert mod.get("stream-info").status_code == 200
    assert mod.get("stream-info/categories", params={"q": "x"}).status_code == 200
    assert save(mod).is_success
    assert twitch.title == NEW_TITLE
    (entry,) = audit_entries(host)
    assert entry["actor"]["name"] == "Mod"
    assert entry["source"] == "dashboard"


def test_mod_協作關閉後進不了頻道後台(host, twitch, repo, twitch_mods, channel_id):
    twitch_mods.set(channel_id, (MOD, "Mod"))
    mod = mod_client(host, repo)
    assert host.put("mod-collab", json={"enabled": False}).is_success

    forbidden = [mod.get("stream-info"), mod.get("stream-info/categories", params={"q": "x"}), save(mod)]

    assert [(r.status_code, r.json()) for r in forbidden] == [(403, {"error": "channel_forbidden"})] * 3
    assert twitch.title == OLD_TITLE
