"""C-06：實況主與 mod 在後台查看執法紀錄並處理誤判（真實 PostgreSQL，RPC 在 `rpc.request` 層替身）。"""

import concurrent.futures
import sys
from datetime import timedelta
from unittest.mock import AsyncMock, Mock
from zlib import crc32

import pytest
from fastapi.testclient import TestClient

from starlib import sqldb as real_sqldb
from starlib.database import TwitchBotJoinChannel, TwitchEnforcementLog
from starlib.messaging import cache_invalidation, rpc
from starlib.utils import nowtz
from starServer.dashboard import twitch_control
from tests.helpers.dashboard_auth import FRONTEND, make_app, make_twitch_session

pytestmark = pytest.mark.usefixtures("dashboard_env")

ALICE = 2000000971
BOB = 2000000972
MOD = "2000000973"


def use_repo(monkeypatch, repo) -> None:
    """把已載入的 starlib、starServer 模組裡的 `sqldb` 都換成測試用的交易 repo。"""
    make_app()
    for name, module in list(sys.modules.items()):
        if name.startswith(("starlib", "starServer")) and getattr(module, "sqldb", None) is real_sqldb:
            monkeypatch.setattr(module, "sqldb", repo)


@pytest.fixture
def channel_id(request):
    return 2120000000 + crc32(request.node.nodeid.encode()) % 10000000


class FakeBot:
    """`rpc.request` 的替身：記錄呼叫，回應由測試指定。"""

    def __init__(self):
        self.calls: list[tuple[str, str, dict]] = []
        self.replies: dict[str, object] = {"moderation.lift": {"result": "lifted"}, "moderation.clear_strikes": {}}

    def request(self, service, method, payload, **_):
        self.calls.append((service, method, payload))
        future = concurrent.futures.Future()
        reply = self.replies.get(method, {})
        if isinstance(reply, Exception):
            future.set_exception(reply)
        else:
            future.set_result(reply)
        return future

    def methods(self):
        return [method for _, method, _ in self.calls]


@pytest.fixture
def bot(monkeypatch):
    fake = FakeBot()
    monkeypatch.setattr(rpc, "request", fake.request)
    return fake


def client_for(repo, channel_id, session_id, twitch_id, login, name):
    sid = make_twitch_session(repo, twitch_id=str(twitch_id), session_id=session_id, login=login, name=name)
    client = TestClient(
        make_app(), base_url=f"https://testserver/dashboard/channels/{channel_id}/", headers={"Origin": FRONTEND}
    )
    client.cookies.set("dashboard_session", sid)
    return client


@pytest.fixture
def host(monkeypatch, repo, channel_id, bot):
    use_repo(monkeypatch, repo)
    repo.add(TwitchBotJoinChannel(twitch_id=channel_id, state="enabled"))
    monkeypatch.setattr(cache_invalidation, "invalidate", Mock())
    monkeypatch.setattr(twitch_control, "check_template", AsyncMock(return_value="ok"))
    return client_for(repo, channel_id, "enforcement-host", channel_id, "host", "Host")


def log_row(repo, channel_id, **fields) -> int:
    values = {
        "twitch_id": channel_id,
        "at": nowtz(),
        "user_id": ALICE,
        "user_login": "alice",
        "user_name": "Alice",
        "filter": "link",
        "strike": 1,
        "action": "timeout",
        "duration": 600,
        "message": "看這個 abc.com",
        "status": "ok",
        "lifted_at": None,
    }
    row = TwitchEnforcementLog(**{**values, **fields})
    repo.add(row)
    repo.session.flush()
    return row.id


def rows_of(response):
    assert response.status_code == 200, response.text
    lists = [value for value in response.json().values() if isinstance(value, list)]
    assert len(lists) == 1, response.json()
    return lists[0]


def audit_kinds(host):
    return [(entry["target_kind"], entry["action"]) for entry in host.get("audit").json()["entries"]]


def lifted_at(repo, log_id):
    return repo.session.get(TwitchEnforcementLog, log_id, populate_existing=True).lifted_at


# ---- 查看 ----


def test_實況主看得到時間觀眾過濾器次數動作與原訊息且失敗的有標示(host, repo, channel_id):
    log_row(repo, channel_id, at=nowtz() - timedelta(minutes=2), strike=2, filter="link")
    log_row(
        repo,
        channel_id,
        user_id=BOB,
        user_login="bob",
        user_name="Bob",
        action="delete",
        duration=None,
        status="failed",
        message="失敗那則",
    )

    failed, ok = rows_of(host.get("enforcement"))

    assert (failed["message"], failed["user_login"], failed["action"], failed["status"]) == (
        "失敗那則",
        "bob",
        "delete",
        "failed",
    )
    assert (ok["user_login"], ok["user_name"], ok["filter"], ok["strike"], ok["action"], ok["duration"]) == (
        "alice",
        "Alice",
        "link",
        2,
        "timeout",
        600,
    )
    assert (ok["status"], ok["message"]) == ("ok", "看這個 abc.com")
    assert ok["at"]


def test_mod_協作開啟時看得到_關閉後看不到(host, repo, channel_id, twitch_mods):
    log_row(repo, channel_id)
    twitch_mods.set(channel_id, (MOD, "Mod"))
    mod = client_for(repo, channel_id, "enforcement-mod", MOD, "mod", "Mod")
    assert len(rows_of(mod.get("enforcement"))) == 1

    assert host.put("mod-collab", json={"enabled": False}).is_success

    response = mod.get("enforcement")
    assert response.status_code == 403 and response.json() == {"error": "channel_forbidden"}


def test_只列出自己頻道的紀錄(host, repo, channel_id):
    log_row(repo, channel_id)
    log_row(repo, channel_id + 1, message="別的頻道")
    assert [row["message"] for row in rows_of(host.get("enforcement"))] == ["看這個 abc.com"]


def test_每頁_50_筆新的在前並可用_offset_翻頁(host, repo, channel_id):
    base = nowtz() - timedelta(hours=1)
    for index in range(55):
        log_row(repo, channel_id, at=base + timedelta(seconds=index), message=f"m{index}")

    first = rows_of(host.get("enforcement"))
    second = rows_of(host.get("enforcement", params={"offset": 50}))

    assert [row["message"] for row in first] == [f"m{index}" for index in range(54, 4, -1)]
    assert [row["message"] for row in second] == [f"m{index}" for index in range(4, -1, -1)]


def test_超過_30_天的紀錄不再出現(host, repo, channel_id):
    log_row(repo, channel_id, at=nowtz() - timedelta(days=31), message="太舊")
    log_row(repo, channel_id, at=nowtz() - timedelta(days=29), message="還在")
    assert [row["message"] for row in rows_of(host.get("enforcement"))] == ["還在"]


# ---- 解除處罰 ----


def test_解除未到期的_timeout_呼叫_bot_標示已解除並記修改紀錄(host, repo, channel_id, bot):
    log_id = log_row(repo, channel_id, at=nowtz() - timedelta(minutes=1), duration=600)

    response = host.post(f"enforcement/{log_id}/lift")

    assert response.is_success, response.text
    ((service, method, payload),) = bot.calls
    assert (service, method) == ("twitch", "moderation.lift")
    assert (int(payload["twitch_id"]), int(payload["user_id"])) == (channel_id, ALICE)
    assert lifted_at(repo, log_id) is not None
    assert [kind for kind, _ in audit_kinds(host)] == ["enforcement"]
    assert rows_of(host.get("enforcement"))[0]["lifted_at"] is not None


def test_ban_紀錄也能解除(host, repo, channel_id, bot):
    log_id = log_row(repo, channel_id, action="ban", duration=None)
    assert host.post(f"enforcement/{log_id}/lift").is_success
    assert bot.methods() == ["moderation.lift"]
    assert lifted_at(repo, log_id) is not None


def test_已到期的_timeout_回已不在處罰中且不呼叫_bot(host, repo, channel_id, bot):
    log_id = log_row(repo, channel_id, at=nowtz() - timedelta(minutes=20), duration=600)

    response = host.post(f"enforcement/{log_id}/lift")

    assert response.is_success and response.json() == {"result": "not_punished"}
    assert bot.calls == []
    assert audit_kinds(host) == []


def test_已解除的紀錄回已不在處罰中且不呼叫_bot(host, repo, channel_id, bot):
    log_id = log_row(repo, channel_id, lifted_at=nowtz() - timedelta(seconds=30))
    response = host.post(f"enforcement/{log_id}/lift")
    assert response.is_success and response.json() == {"result": "not_punished"}
    assert bot.calls == []


def test_只刪除訊息的紀錄不能解除(host, repo, channel_id, bot):
    log_id = log_row(repo, channel_id, action="delete", duration=None)
    response = host.post(f"enforcement/{log_id}/lift")
    assert response.status_code == 400, response.text
    assert bot.calls == []
    assert lifted_at(repo, log_id) is None


def test_Twitch_說觀眾沒在處罰中時回已不在處罰中(host, repo, channel_id, bot):
    bot.replies["moderation.lift"] = {"result": "not_punished"}
    log_id = log_row(repo, channel_id)
    response = host.post(f"enforcement/{log_id}/lift")
    assert response.is_success and response.json() == {"result": "not_punished"}
    assert audit_kinds(host) == []


def test_bot_不是頻道_mod_回_409(host, repo, channel_id, bot):
    bot.replies["moderation.lift"] = {"result": "not_mod"}
    log_id = log_row(repo, channel_id)
    response = host.post(f"enforcement/{log_id}/lift")
    assert (response.status_code, response.json()["error"]) == (409, "bot_not_mod")
    assert lifted_at(repo, log_id) is None
    assert audit_kinds(host) == []


def test_bot_離線回_503_且可重試(host, repo, channel_id, bot):
    bot.replies["moderation.lift"] = rpc.RpcUnavailable()
    log_id = log_row(repo, channel_id)
    response = host.post(f"enforcement/{log_id}/lift")
    assert (response.status_code, response.json()["error"]) == (503, "bot_offline")
    assert lifted_at(repo, log_id) is None

    bot.replies["moderation.lift"] = {"result": "lifted"}
    assert host.post(f"enforcement/{log_id}/lift").is_success
    assert lifted_at(repo, log_id) is not None


def test_Twitch_呼叫失敗時不標示已解除且可重試(host, repo, channel_id, bot):
    bot.replies["moderation.lift"] = rpc.RpcHandlerError("TwitchAPIException")
    log_id = log_row(repo, channel_id)
    response = host.post(f"enforcement/{log_id}/lift")
    assert response.status_code >= 400
    assert lifted_at(repo, log_id) is None
    assert audit_kinds(host) == []

    bot.replies["moderation.lift"] = {"result": "lifted"}
    assert host.post(f"enforcement/{log_id}/lift").is_success
    assert lifted_at(repo, log_id) is not None


def test_不能處理別的頻道的紀錄(host, repo, channel_id, bot):
    own = log_row(repo, channel_id)
    assert host.post(f"enforcement/{own}/clear-strikes").is_success
    bot.calls.clear()

    log_id = log_row(repo, channel_id + 1)
    for action in ("lift", "clear-strikes", "regular"):
        assert host.post(f"enforcement/{log_id}/{action}").status_code in (403, 404)
    assert bot.calls == []


# ---- 清除犯規次數 ----


def test_清除犯規次數呼叫_bot_並記修改紀錄(host, repo, channel_id, bot):
    log_id = log_row(repo, channel_id)

    response = host.post(f"enforcement/{log_id}/clear-strikes")

    assert response.is_success, response.text
    ((_, method, payload),) = bot.calls
    assert method == "moderation.clear_strikes"
    assert (int(payload["twitch_id"]), int(payload["user_id"])) == (channel_id, ALICE)
    assert [kind for kind, _ in audit_kinds(host)] == ["enforcement"]


def test_清除犯規次數時_bot_離線回_503(host, repo, channel_id, bot):
    bot.replies["moderation.clear_strikes"] = rpc.RpcUnavailable()
    log_id = log_row(repo, channel_id)
    response = host.post(f"enforcement/{log_id}/clear-strikes")
    assert (response.status_code, response.json()["error"]) == (503, "bot_offline")
    assert audit_kinds(host) == []


# ---- 加入常客 ----


def regular_ids(host):
    return {str(row["user_id"]) for row in host.get("regulars").json()["regulars"]}


def test_加入常客後名單出現該觀眾_已是常客時不重複(host, repo, channel_id, bot):
    log_id = log_row(repo, channel_id)

    response = host.post(f"enforcement/{log_id}/regular")

    assert response.is_success, response.text
    assert regular_ids(host) == {str(ALICE)}
    assert ("regular", "create") in audit_kinds(host)

    again = host.post(f"enforcement/{log_id}/regular")
    assert again.status_code == 409, again.text
    assert regular_ids(host) == {str(ALICE)}
    assert bot.calls == []
