"""C-07：實況主與 mod 在後台管理 Twitch Blocked Terms。

web 端點經 `rpc.request` 轉給 Twitch bot 的真 handler，Helix 在 HTTP 層以有狀態替身取代（見
`tests/twitch/test_blocked_terms_rpc.py`），所以 RPC 回傳形狀不是測試的前提，只看後台與 Twitch 清單的行為。
"""

import asyncio
import concurrent.futures

import pytest
from fastapi.testclient import TestClient

from starlib.messaging import rpc
from tests.dashboard.test_channel_moderation import (
    MOD,
    channel_id,  # noqa: F401 (fixture)
    host,  # noqa: F401 (fixture)
    start_chat,  # noqa: F401 (fixture)
)
from tests.helpers.dashboard_auth import FRONTEND, make_app, make_twitch_session
from tests.twitch.test_blocked_terms_rpc import handlers, helix  # noqa: F401 (fixture)


class Bot:
    """`rpc.request` 的替身：交給 bot 端真的 handler；`online = False` 時模擬 bot 沒在跑。"""

    def __init__(self, helix):
        self.helix = helix
        self.online = True
        self.methods: list[str] = []
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)

    def request(self, service, method, payload, **_):
        assert service == "twitch"
        self.methods.append(method)
        if not self.online:
            future = concurrent.futures.Future()
            future.set_exception(rpc.RpcUnavailable())
            return future
        return self.pool.submit(lambda: asyncio.run(self.helix.handlers[method](payload)))


@pytest.fixture
def bot(monkeypatch, helix):  # noqa: F811
    fake = Bot(helix)
    monkeypatch.setattr(rpc, "request", fake.request)
    yield fake
    fake.pool.shutdown()


@pytest.fixture
def twitch(helix):  # noqa: F811
    return helix.stub


def audit_entries(host, kind="blocked_term"):
    return [entry for entry in host.get("audit").json()["entries"] if entry["target_kind"] == kind]


def term_id_of(twitch, text):
    (term_id,) = (key for key, value in twitch.terms.items() if value == text)
    return term_id


# ---- 查看 ----


def test_在_Twitch_創作者後台新增的詞重新載入後台就看得到(host, bot, twitch):
    twitch.terms["t-1"] = "創作者後台加的"

    response = host.get("blocked-terms")

    assert response.status_code == 200, response.text
    assert "創作者後台加的" in str(response.json())

    twitch.terms["t-2"] = "之後又加的"
    assert "之後又加的" in str(host.get("blocked-terms").json())


# ---- 新增與刪除 ----


def test_在後台新增後_Twitch_清單有該詞並記修改紀錄(host, bot, twitch):
    response = host.post("blocked-terms", json={"text": "壞詞"})

    assert response.is_success, response.text
    assert list(twitch.terms.values()) == ["壞詞"]
    assert "壞詞" in str(host.get("blocked-terms").json())
    (entry,) = audit_entries(host)
    assert (entry["action"], entry["source"]) == ("create", "dashboard")
    assert "壞詞" in str(entry["after"])


def test_在後台刪除後_Twitch_清單不再有該詞並記修改紀錄(host, bot, twitch):
    twitch.terms.update({"t-1": "留著", "t-2": "要刪"})
    assert "要刪" in str(host.get("blocked-terms").json())

    response = host.delete("blocked-terms/t-2")

    assert response.is_success, response.text
    assert twitch.terms == {"t-1": "留著"}
    assert "要刪" not in str(host.get("blocked-terms").json())
    (entry,) = audit_entries(host)
    assert entry["action"] == "delete"
    assert "要刪" in str(entry["before"])


def test_新增與刪除都留在修改紀錄(host, bot, twitch):
    assert host.post("blocked-terms", json={"text": "壞詞"}).is_success
    assert host.delete(f"blocked-terms/{term_id_of(twitch, '壞詞')}").is_success
    assert [entry["action"] for entry in audit_entries(host)] == ["delete", "create"]


# ---- bot 不是 mod ----


def test_bot_不是頻道_mod_時查看回_409_不給清單(host, bot, twitch):
    twitch.terms["t-1"] = "不該露出"
    twitch.status = 403

    response = host.get("blocked-terms")

    assert (response.status_code, response.json()["error"]) == (409, "bot_not_mod")
    assert "不該露出" not in response.text


def test_bot_不是頻道_mod_時新增與刪除回_409_且不寫修改紀錄(host, bot, twitch):
    twitch.status = 403

    added = host.post("blocked-terms", json={"text": "壞詞"})
    deleted = host.delete("blocked-terms/t-1")

    assert [(r.status_code, r.json()["error"]) for r in (added, deleted)] == [(409, "bot_not_mod")] * 2
    assert audit_entries(host) == []


# ---- bot 離線 ----


def test_bot_離線時查看回_503_恢復後重試成功(host, bot, twitch):
    twitch.terms["t-1"] = "壞詞"
    bot.online = False

    response = host.get("blocked-terms")
    assert (response.status_code, response.json()["error"]) == (503, "bot_offline")

    bot.online = True
    retry = host.get("blocked-terms")
    assert retry.status_code == 200 and "壞詞" in str(retry.json())


def test_bot_離線時新增與刪除回_503_且不寫修改紀錄(host, bot, twitch):
    twitch.terms["t-1"] = "留著"
    bot.online = False

    added = host.post("blocked-terms", json={"text": "壞詞"})
    deleted = host.delete("blocked-terms/t-1")

    assert [(r.status_code, r.json()["error"]) for r in (added, deleted)] == [(503, "bot_offline")] * 2
    assert audit_entries(host) == []
    assert twitch.terms == {"t-1": "留著"}


# ---- 權限 ----


def mod_client(host, repo, channel_id):
    client = TestClient(make_app(), base_url=host.base_url, headers={"Origin": FRONTEND})
    sid = make_twitch_session(repo, twitch_id=MOD, session_id="blocked-terms-mod", login="mod", name="Mod")
    client.cookies.set("dashboard_session", sid)
    return client


def test_mod_協作開啟時能查看與新增_關閉後都不行(host, bot, twitch, repo, twitch_mods, channel_id):
    twitch_mods.set(channel_id, (MOD, "Mod"))
    mod = mod_client(host, repo, channel_id)
    assert mod.get("blocked-terms").status_code == 200
    assert mod.post("blocked-terms", json={"text": "壞詞"}).is_success
    (entry,) = audit_entries(host)
    assert entry["actor"]["name"] == "Mod"

    assert host.put("mod-collab", json={"enabled": False}).is_success

    forbidden = [mod.get("blocked-terms"), mod.post("blocked-terms", json={"text": "另一個"})]
    assert [(r.status_code, r.json()) for r in forbidden] == [(403, {"error": "channel_forbidden"})] * 2
    assert list(twitch.terms.values()) == ["壞詞"]
