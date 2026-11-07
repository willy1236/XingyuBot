"""starlib.messaging 的請求／回應（T-06）與快取失效（T-07）：用真的 Redis，同一個 process 內建立多個 MessageBus 模擬多個 process。

共用 test_messaging 的 fixture 與 FlakyProxy。
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from test_messaging import (  # noqa: F401  fixture 靠 import 進來
    FlakyProxy,
    _is_up,
    fast_timings,
    handler_loop,
    make_bus,
    prefix,
    proxy,
    raw,
    redis_url,
    wait_until,
)

from starlib.messaging import cache_invalidation, rpc
from starlib.messaging.cache_invalidation import invalidate, on_invalidate
from starlib.messaging.rpc import RpcHandlerError, RpcUnavailable, handle, request

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def fast_extension_timings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rpc, "READ_BLOCK_MS", 300)
    monkeypatch.setattr(rpc, "RETRY_DELAY", 0.2)
    monkeypatch.setattr(rpc, "MAINTENANCE_INTERVAL", 0.3)
    monkeypatch.setattr(cache_invalidation, "POLL_TIMEOUT", 0.2)
    monkeypatch.setattr(cache_invalidation, "RESUBSCRIBE_INITIAL_DELAY", 0.1)


# ── 請求／回應 ───────────────────────────────────────────

SERVER = "svc-a"


async def echo(payload: dict) -> dict:
    return {"echo": payload}


@pytest.mark.parametrize("register_first", [True, False])
def test_request_gets_handler_result(make_bus, handler_loop, register_first):
    server, client = make_bus(), make_bus()
    if register_first:
        handle("echo", echo, handler_loop, bus=server)
        server.start(SERVER, "c1")
    else:
        server.start(SERVER, "c1")
        handle("echo", echo, handler_loop, bus=server)

    result = request(SERVER, "echo", {"x": "中文", "n": 1}, bus=client).result(10)

    assert result == {"echo": {"x": "中文", "n": 1}}


def test_handler_runs_on_registered_loop(make_bus, handler_loop):
    server, client = make_bus(), make_bus()
    seen: list[asyncio.AbstractEventLoop] = []

    async def which_loop(payload: dict) -> dict:
        seen.append(asyncio.get_running_loop())
        return {}

    handle("where", which_loop, handler_loop, bus=server)
    server.start(SERVER, "c1")
    request(SERVER, "where", {}, bus=client).result(10)

    assert seen == [handler_loop]


def test_no_response_within_five_seconds_is_unavailable(make_bus):
    client = make_bus()

    started = time.monotonic()
    with pytest.raises(RpcUnavailable):
        request(SERVER, "echo", {}, bus=client).result(15)

    assert 4.5 <= time.monotonic() - started <= 7


def test_service_without_handle_times_out(make_bus, monkeypatch):
    monkeypatch.setattr(rpc, "REQUEST_TIMEOUT", 1.0)
    server, client = make_bus(), make_bus()
    server.start(SERVER, "c1")

    with pytest.raises(RpcUnavailable):
        request(SERVER, "echo", {}, bus=client).result(10)


def test_redis_down_is_unavailable_immediately(make_bus, proxy):
    p, url = proxy
    p.set_down(True)
    client = make_bus(url)

    started = time.monotonic()
    with pytest.raises(RpcUnavailable):
        request(SERVER, "echo", {}, bus=client).result(10)

    assert time.monotonic() - started < 2


def test_handler_error_is_distinct_from_unavailable(make_bus, handler_loop):
    server, client = make_bus(), make_bus()

    async def boom(payload: dict) -> dict:
        raise ValueError("壞掉了")

    handle("boom", boom, handler_loop, bus=server)
    server.start(SERVER, "c1")

    with pytest.raises(RpcHandlerError, match="壞掉了"):
        request(SERVER, "boom", {}, bus=client).result(10)
    with pytest.raises(RpcHandlerError, match="nope"):
        request(SERVER, "nope", {}, bus=client).result(10)
    assert not issubclass(RpcHandlerError, RpcUnavailable)
    assert not issubclass(RpcUnavailable, RpcHandlerError)


def test_two_instances_each_request_handled_once(make_bus, handler_loop):
    s1, s2, client = make_bus(), make_bus(), make_bus()
    handled: list[tuple[str, int]] = []

    def make(name: str):
        async def h(payload: dict) -> dict:
            handled.append((name, payload["n"]))
            return {"n": payload["n"]}

        return h

    handle("count", make("a"), handler_loop, bus=s1)
    handle("count", make("b"), handler_loop, bus=s2)
    s1.start(SERVER, "a")
    s2.start(SERVER, "b")

    futures = [request(SERVER, "count", {"n": n}, bus=client) for n in range(10)]
    results = [f.result(10) for f in futures]

    assert results == [{"n": n} for n in range(10)]
    assert sorted(n for _, n in handled) == list(range(10))


def test_expired_request_is_dropped_without_reply(make_bus, handler_loop, raw, prefix):
    server = make_bus()
    called: list[dict] = []

    async def spy(payload: dict) -> dict:
        called.append(payload)
        return {}

    handle("spy", spy, handler_loop, bus=server)
    server.start(SERVER, "c1")
    stream = f"{prefix}:rpc:{SERVER}"
    assert wait_until(lambda: _group_info(raw, stream) is not None)

    request_id = str(uuid4())
    reply_to = f"{prefix}:rpc:reply:{request_id}"
    body = {
        "request_id": request_id,
        "method": "spy",
        "payload": {},
        "reply_to": reply_to,
        "deadline": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
    }
    raw.xadd(stream, {"data": json.dumps(body)})

    def consumed() -> bool:
        info = _group_info(raw, stream)
        return info is not None and info["lag"] == 0 and info["pending"] == 0

    assert wait_until(consumed)
    assert called == []
    assert raw.exists(reply_to) == 0


def test_concurrent_requests_get_their_own_replies(make_bus, handler_loop):
    server = make_bus()
    clients = [make_bus(), make_bus()]

    async def slow_echo(payload: dict) -> dict:
        await asyncio.sleep(0.02)
        return payload

    handle("echo", slow_echo, handler_loop, bus=server)
    server.start(SERVER, "c1")

    futures = [(n, request(SERVER, "echo", {"n": n}, bus=clients[n % 2])) for n in range(20)]

    for n, future in futures:
        assert future.result(10) == {"n": n}


def test_request_from_other_threads(make_bus, handler_loop):
    server, client = make_bus(), make_bus()
    handle("echo", echo, handler_loop, bus=server)
    server.start(SERVER, "c1")
    results: list[dict] = []

    def worker(n: int) -> None:
        results.append(request(SERVER, "echo", {"n": n}, bus=client).result(10))

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(r["echo"]["n"] for r in results) == list(range(5))


def test_cancelled_handler_does_not_stop_consumer(make_bus, handler_loop):
    server, client = make_bus(), make_bus()

    async def cancelled(payload: dict) -> dict:
        raise asyncio.CancelledError

    handle("cancel", cancelled, handler_loop, bus=server)
    handle("echo", echo, handler_loop, bus=server)
    server.start(SERVER, "c1")

    with pytest.raises(RpcHandlerError):
        request(SERVER, "cancel", {}, bus=client).result(10)
    assert request(SERVER, "echo", {"n": 1}, bus=client).result(10) == {"echo": {"n": 1}}


def test_slow_requests_do_not_block_later_ones(make_bus, handler_loop):
    server, client = make_bus(), make_bus()

    async def slow(payload: dict) -> dict:
        await asyncio.sleep(0.5)
        return payload

    handle("slow", slow, handler_loop, bus=server)
    server.start(SERVER, "c1")

    started = time.monotonic()
    futures = [request(SERVER, "slow", {"n": n}, bus=client) for n in range(12)]

    assert [f.result(10) for f in futures] == [{"n": n} for n in range(12)]
    assert time.monotonic() - started < 3


def test_request_on_closed_bus_is_unavailable(make_bus):
    client = make_bus()
    client.close(timeout=2)

    with pytest.raises(RpcUnavailable):
        request(SERVER, "echo", {}, bus=client).result(5)


def test_cancelling_request_future_does_not_log_error(make_bus, caplog):
    client = make_bus()

    with caplog.at_level(logging.ERROR):
        future = request(SERVER, "echo", {}, bus=client)
        future.cancel()
        client.close(timeout=2)  # inner 隨 bus 關閉而結束，relay 此時面對已取消的 outer
        time.sleep(0.3)

    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


def _group_info(raw, stream: str) -> dict | None:
    try:
        groups = raw.xinfo_groups(stream)
    except Exception:
        return None
    return groups[0] if groups else None


# ── 快取失效 ─────────────────────────────────────────────


class KeyRecorder:
    def __init__(self) -> None:
        self.keys: list[str | None] = []

    async def __call__(self, key: str | None) -> None:
        self.keys.append(key)


def subscribers(raw, prefix: str) -> int:
    return dict(raw.pubsub_numsub(f"{prefix}:cache-invalidate")).get(f"{prefix}:cache-invalidate", 0)


def test_key_invalidation_reaches_every_instance_including_sender(make_bus, handler_loop, raw, prefix):
    a, b = make_bus(), make_bus()
    rec_a, rec_b = KeyRecorder(), KeyRecorder()
    on_invalidate("users", rec_a, handler_loop, bus=a)
    on_invalidate("users", rec_b, handler_loop, bus=b)
    assert wait_until(lambda: subscribers(raw, prefix) == 2)

    invalidate("users", "42", bus=a)

    assert wait_until(lambda: rec_a.keys == ["42"] and rec_b.keys == ["42"])


def test_whole_cache_invalidation(make_bus, handler_loop, raw, prefix):
    a, b = make_bus(), make_bus()
    rec_a, rec_b = KeyRecorder(), KeyRecorder()
    on_invalidate("users", rec_a, handler_loop, bus=a)
    on_invalidate("users", rec_b, handler_loop, bus=b)
    assert wait_until(lambda: subscribers(raw, prefix) == 2)

    invalidate("users", bus=a)

    assert wait_until(lambda: rec_a.keys == [None] and rec_b.keys == [None])


def test_other_cache_names_are_not_delivered(make_bus, handler_loop, raw, prefix):
    bus = make_bus()
    users, guilds = KeyRecorder(), KeyRecorder()
    on_invalidate("users", users, handler_loop, bus=bus)
    on_invalidate("guilds", guilds, handler_loop, bus=bus)
    assert wait_until(lambda: subscribers(raw, prefix) == 1)

    invalidate("guilds", "g1", bus=bus)

    assert wait_until(lambda: guilds.keys == ["g1"])
    time.sleep(0.3)
    assert users.keys == []


def test_registering_same_cache_again_replaces_handler(make_bus, handler_loop, raw, prefix):
    bus = make_bus()
    old, new = KeyRecorder(), KeyRecorder()
    on_invalidate("users", old, handler_loop, bus=bus)
    on_invalidate("users", new, handler_loop, bus=bus)
    assert wait_until(lambda: subscribers(raw, prefix) == 1)

    invalidate("users", "1", bus=bus)

    assert wait_until(lambda: new.keys == ["1"])
    time.sleep(0.3)
    assert old.keys == []


def test_handler_runs_on_registered_loop_and_error_does_not_stop_listening(make_bus, handler_loop, raw, prefix):
    bus = make_bus()
    loops: list[asyncio.AbstractEventLoop] = []

    async def flaky(key: str | None) -> None:
        loops.append(asyncio.get_running_loop())
        if key == "bad":
            raise RuntimeError("handler 故意失敗")

    on_invalidate("users", flaky, handler_loop, bus=bus)
    assert wait_until(lambda: subscribers(raw, prefix) == 1)

    invalidate("users", "bad", bus=bus)
    invalidate("users", "good", bus=bus)

    assert wait_until(lambda: len(loops) == 2)
    assert set(loops) == {handler_loop}


def test_malformed_message_is_ignored(make_bus, handler_loop, raw, prefix, caplog):
    bus = make_bus()
    rec = KeyRecorder()
    on_invalidate("users", rec, handler_loop, bus=bus)
    assert wait_until(lambda: subscribers(raw, prefix) == 1)

    with caplog.at_level(logging.WARNING, logger="starlib.messaging"):
        channel = f"{prefix}:cache-invalidate"
        raw.publish(channel, "not json")
        raw.publish(channel, json.dumps({"cache": "users"}))
        raw.publish(channel, json.dumps({"cache": 1, "key": None}))
        raw.publish(channel, json.dumps({"cache": "users", "key": "ok", "extra": 1}))
        assert wait_until(lambda: rec.keys == ["ok"])

    assert sum("格式錯誤" in r.getMessage() for r in caplog.records) == 3


def test_reconnect_invalidates_every_registered_cache(make_bus, handler_loop, raw, prefix, proxy):
    p, url = proxy
    bus = make_bus(url)
    users, guilds = KeyRecorder(), KeyRecorder()
    on_invalidate("users", users, handler_loop, bus=bus)
    on_invalidate("guilds", guilds, handler_loop, bus=bus)
    assert wait_until(lambda: subscribers(raw, prefix) == 1)
    assert users.keys == [] and guilds.keys == []

    p.set_down(True)
    assert wait_until(lambda: not bus.run(_is_up(bus)).result(5), timeout=5)
    p.set_down(False)

    assert wait_until(lambda: users.keys == [None] and guilds.keys == [None], timeout=10)
    assert wait_until(lambda: subscribers(raw, prefix) == 1)


def test_redis_started_after_registration(make_bus, handler_loop, raw, prefix, proxy):
    p, url = proxy
    p.set_down(True)
    bus = make_bus(url)
    rec = KeyRecorder()
    on_invalidate("users", rec, handler_loop, bus=bus)
    time.sleep(0.5)

    p.set_down(False)
    assert wait_until(lambda: subscribers(raw, prefix) == 1, timeout=10)
    raw.publish(f"{prefix}:cache-invalidate", json.dumps({"cache": "users", "key": "k"}))

    assert wait_until(lambda: rec.keys == ["k"])


def test_invalidate_while_redis_down_only_warns(make_bus, proxy, caplog):
    p, url = proxy
    p.set_down(True)
    bus = make_bus(url)

    with caplog.at_level(logging.WARNING, logger="starlib.messaging"):
        invalidate("users", "1", bus=bus)
        assert wait_until(lambda: any("失效通知" in r.getMessage() for r in caplog.records))

    assert all(r.levelno == logging.WARNING for r in caplog.records if "失效通知" in r.getMessage())
