"""starServer.dashboard.twitch_control：web 端呼叫 Twitch bot 的 RPC 與快取失效。"""

import asyncio
import concurrent.futures
from unittest.mock import MagicMock

import pytest

from starlib.messaging import rpc
from starServer.dashboard import twitch_control as control
from starServer.dashboard.twitch_control import BotOffline, BotStatus, ChannelStatus, SubscriptionStatus, SyncResult

TWITCH_ID = 900000000000000001


def future(*, result=None, exception=None) -> concurrent.futures.Future:
    done = concurrent.futures.Future()
    if exception is not None:
        done.set_exception(exception)
    else:
        done.set_result(result)
    return done


@pytest.fixture
def request_mock(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr(control.rpc, "request", mock)
    return mock


def run(coro):
    return asyncio.run(coro)


def test_sync_sends_twitch_id_to_twitch_service(request_mock):
    request_mock.return_value = future(result={"accepted": True, "joined": True})

    assert run(control.sync_channel(TWITCH_ID)) == SyncResult(joined=True)
    request_mock.assert_called_once_with("twitch", "channel.sync", {"twitch_id": TWITCH_ID})


def test_sync_reports_bot_offline_instead_of_raising(request_mock):
    request_mock.return_value = future(exception=rpc.RpcUnavailable("沒有回應"))
    assert run(control.sync_channel(TWITCH_ID)) == BotOffline()


def test_sync_handler_error_is_not_reported_as_offline(request_mock):
    request_mock.return_value = future(exception=rpc.RpcHandlerError("boom"))
    with pytest.raises(rpc.RpcHandlerError):
        run(control.sync_channel(TWITCH_ID))


def test_status_parses_subscriptions(request_mock):
    request_mock.return_value = future(
        result={"joined": True, "subscriptions": {"ok": ["stream online"], "failed": ["channel raid"], "pending": True}}
    )

    assert run(control.channel_status(TWITCH_ID)) == ChannelStatus(
        joined=True, subscriptions=SubscriptionStatus(ok=["stream online"], failed=["channel raid"], pending=True)
    )
    request_mock.assert_called_once_with("twitch", "channel.status", {"twitch_id": TWITCH_ID})


def test_status_reports_bot_offline(request_mock):
    request_mock.return_value = future(exception=rpc.RpcUnavailable("Redis 連不上"))
    assert run(control.channel_status(TWITCH_ID)) == BotOffline()


@pytest.mark.parametrize("cache", ["twitch_channel", "twitch_cmd", "twitch_timer", "twitch_event_response"])
def test_invalidate_uses_twitch_id_string_as_key(monkeypatch, cache):
    mock = MagicMock()
    monkeypatch.setattr(control.cache_invalidation, "invalidate", mock)

    control.invalidate(cache, TWITCH_ID)

    mock.assert_called_once_with(cache, str(TWITCH_ID))


def test_broadcaster_token_runs_on_dashboard_db_executor(monkeypatch):
    """web 端取 token 的 DB 工作走 run_db（後台專屬、限制連線數的 executor），不走 asyncio 預設 executor。"""
    seen = []

    async def fake_run_db(fn):
        seen.append("run_db")
        return fn()

    monkeypatch.setattr(control, "run_db", fake_run_db)
    monkeypatch.setattr(control.twitch_tokens, "broadcaster_token_blocking", lambda twitch_id: f"token-{twitch_id}")

    assert run(control.broadcaster_token(TWITCH_ID)) == f"token-{TWITCH_ID}"
    assert seen == ["run_db"]


def test_bot_status_sends_empty_payload(request_mock):
    request_mock.return_value = future(result={"started_at": "2026-11-20T00:00:00+08:00", "rooms": 3})

    assert run(control.bot_status()) == BotStatus(started_at="2026-11-20T00:00:00+08:00", rooms=3)
    request_mock.assert_called_once_with("twitch", "bot.status", {})


def test_bot_status_offline_and_handler_error(request_mock):
    request_mock.return_value = future(exception=rpc.RpcUnavailable("沒有回應"))
    assert run(control.bot_status()) == BotOffline()
    request_mock.return_value = future(exception=rpc.RpcHandlerError("boom"))
    with pytest.raises(rpc.RpcHandlerError):
        run(control.bot_status())
