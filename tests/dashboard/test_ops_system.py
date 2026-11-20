"""營運入口的系統部分：Discord bot、Twitch bot、匯流排與後台 DB 的狀態總覽。"""

from __future__ import annotations

import asyncio
import threading
import time
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from starlib import sclient
from starlib.messaging import rpc
from starlib.utils import nowtz
from starServer.dashboard import db, ops_system, twitch_control
from starServer.dashboard.twitch_control import BotOffline, BotStatus
from tests.helpers.dashboard_auth import FRONTEND, USER_ID, make_app, make_session

pytestmark = pytest.mark.usefixtures("dashboard_env")

STATUS = "/dashboard/ops/system/status"
STARTED = nowtz().replace(microsecond=0) - timedelta(hours=2)


def client_for(session_id: str) -> TestClient:
    c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False)
    c.cookies.set("dashboard_session", session_id)
    c.headers["Origin"] = FRONTEND
    return c


@pytest.fixture
def env(monkeypatch):
    """假的 Discord bot、Twitch RPC 與匯流排，各測試可調整。"""
    state = SimpleNamespace(
        owners={int(USER_ID)},
        ready=True,
        latency=0.0426,
        guilds=[SimpleNamespace(chunked=True), SimpleNamespace(chunked=False), SimpleNamespace(chunked=False)],
        twitch=BotStatus(started_at=STARTED.isoformat(), rooms=4),
        bus=SimpleNamespace(state="up"),
    )

    class FakeBot:
        started_at = STARTED
        guilds = state.guilds

        async def is_owner(self, user):
            return user.id in state.owners

        def is_ready(self):
            return state.ready

        @property
        def latency(self):
            if isinstance(state.latency, Exception):
                raise state.latency
            return state.latency

    monkeypatch.setattr(sclient, "bot", FakeBot())

    async def bot_status():
        if isinstance(state.twitch, Exception):
            raise state.twitch
        return state.twitch

    monkeypatch.setattr(twitch_control, "bot_status", bot_status)
    monkeypatch.setattr(ops_system, "get_bus", lambda: state.bus)
    return state


@pytest.fixture
def owner(repo, env) -> TestClient:
    return client_for(make_session(repo))


def test_non_owner_is_forbidden(repo, env):
    env.owners.clear()
    r = client_for(make_session(repo)).get(STATUS)
    assert (r.status_code, r.json()["error"]) == (403, "not_bot_owner")


def test_all_sections_up(owner, env):
    body = owner.get(STATUS).json()
    assert body["discord"] == {
        "state": "up",
        "ready": True,
        "latency_ms": 43,
        "started_at": STARTED.isoformat(),
        "guild_count": 3,
        "unchunked_guilds": 2,
    }
    assert body["twitch"] == {"state": "up", "started_at": STARTED.isoformat(), "rooms": 4}
    assert body["bus"] == {"state": "up"}
    assert body["db"]["state"] == "up"
    assert body["db"]["executor"] == {"workers": db.MAX_WORKERS, "busy": 0, "queued": 0}
    assert body["db"]["pool"]["limit"] > 0


@pytest.mark.parametrize("latency", [float("nan"), float("inf")])
def test_unknown_latency_is_null(owner, env, latency):
    env.latency = latency
    assert owner.get(STATUS).json()["discord"]["latency_ms"] is None


def test_offline_is_down_not_error(env, monkeypatch):
    # bot 為 None 時無法判定 owner，直接呼叫端點函式驗狀態區塊
    monkeypatch.setattr(sclient, "bot", None)
    env.twitch = BotOffline()
    env.bus.state = "unconfigured"
    body = asyncio.run(ops_system.status(None))  # type: ignore[arg-type]
    assert body["discord"] == {"state": "down"}
    assert body["twitch"] == {"state": "down"}
    assert body["bus"] == {"state": "unconfigured"}


def test_one_failing_section_does_not_affect_others(owner, env, monkeypatch):
    env.twitch = rpc.RpcHandlerError("boom")

    def broken_pool():
        raise RuntimeError("pool")

    monkeypatch.setattr(db, "pool_stats", broken_pool)
    env.latency = RuntimeError("latency")

    body = owner.get(STATUS).json()
    assert body["twitch"] == {"state": "error"}
    assert body["db"] == {"state": "error"}
    assert body["discord"] == {"state": "error"}
    assert body["bus"] == {"state": "up"}


def test_status_answers_while_db_executor_is_saturated(env):
    # 權限檢查本身走 run_db，executor 塞滿時會排隊；這裡只驗狀態區塊不經 executor，直接呼叫端點函式
    release = threading.Event()
    futures = [db._executor.submit(db._run, release.wait) for _ in range(db.MAX_WORKERS + 2)]
    try:
        deadline = time.monotonic() + 5
        while db.executor_stats()["busy"] < db.MAX_WORKERS and time.monotonic() < deadline:
            time.sleep(0.01)
        body = asyncio.run(asyncio.wait_for(ops_system.status(None), 5))  # type: ignore[arg-type]
        executor = body["db"]["executor"]
        assert executor == {"workers": db.MAX_WORKERS, "busy": db.MAX_WORKERS, "queued": 2}
    finally:
        release.set()
        for f in futures:
            f.result(5)


def test_discord_started_at_is_kept_on_reidentify():
    from starDiscord.bot import DiscordBot

    bot = SimpleNamespace(started_at=None)
    asyncio.run(DiscordBot._record_started(bot))  # type: ignore[arg-type]
    first = bot.started_at
    assert first is not None
    asyncio.run(DiscordBot._record_started(bot))  # type: ignore[arg-type]
    assert bot.started_at is first
