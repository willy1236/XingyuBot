"""starlib.messaging 事件廣播：用真的 Redis，同一個 process 內建立多個 MessageBus 模擬多個 process。

每個測試用不重複的 key 前綴，結束時刪掉；時間相關的常數（維護週期、收回門檻、重連退避）縮短後測行為。
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
import redis

from starlib.messaging import BusEvent, BusUnavailable, Delivery, MessageBus
from starlib.messaging import bus as bus_module
from starlib.messaging import connection as connection_module
from starlib.settings import get_settings

pytestmark = pytest.mark.integration

SERVICE = "svc"
OTHER_SERVICE = "other"


class Ping(BusEvent):
    event_type = "test.messaging.ping"
    ttl = timedelta(minutes=10)
    receivers = (SERVICE, OTHER_SERVICE)

    n: int
    text: str = ""


class ShortLived(BusEvent):
    event_type = "test.messaging.short"
    ttl = timedelta(seconds=1)
    receivers = (SERVICE,)

    n: int


def now() -> datetime:
    return datetime.now(UTC)


def wait_until(predicate: Callable[[], bool], timeout: float = 10, interval: float = 0.05) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


@pytest.fixture(scope="module")
def redis_url() -> str:
    url = get_settings().REDIS_URL
    if not url:
        pytest.skip("REDIS_URL 未設定")
    try:
        redis.Redis.from_url(url, socket_connect_timeout=2).ping()
    except redis.RedisError as exc:
        pytest.skip(f"Redis 連不上：{exc}")
    return url


@pytest.fixture
def raw(redis_url: str) -> Iterator[redis.Redis]:
    client = redis.Redis.from_url(redis_url, decode_responses=True)
    yield client
    client.close()


@pytest.fixture
def prefix(raw: redis.Redis) -> Iterator[str]:
    value = f"test-{uuid4().hex[:12]}"
    yield value
    keys = list(raw.scan_iter(f"{value}:*"))
    if keys:
        raw.delete(*keys)


@pytest.fixture(autouse=True)
def fast_timings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bus_module, "MAINTENANCE_INTERVAL", 0.3)
    monkeypatch.setattr(bus_module, "READ_BLOCK_MS", 300)
    monkeypatch.setattr(connection_module, "RECONNECT_MAX_DELAY", 0.5)
    monkeypatch.setattr(connection_module, "RECONNECT_INITIAL_DELAY", 0.1)
    monkeypatch.setattr(connection_module, "HEALTH_CHECK_INTERVAL", 0.3)


@pytest.fixture
def sentry(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[Any]]:
    calls: dict[str, list[Any]] = {"exception": [], "message": [], "handler": []}
    monkeypatch.setattr(connection_module, "capture_exception_safe", lambda exc, **kw: calls["exception"].append(exc))
    monkeypatch.setattr(connection_module, "capture_message_safe", lambda msg, **kw: calls["message"].append(msg))
    monkeypatch.setattr(bus_module, "capture_exception_safe", lambda exc, **kw: calls["handler"].append(exc))
    return calls


class LoopThread:
    """模擬 Discord bot 之類有自己 event loop 的 thread。"""

    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(5)


@pytest.fixture
def handler_loop() -> Iterator[asyncio.AbstractEventLoop]:
    lt = LoopThread()
    yield lt.loop
    lt.stop()


@pytest.fixture
def make_bus(prefix: str, redis_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., MessageBus]]:
    buses: list[MessageBus] = []

    def factory(url: str | None = redis_url) -> MessageBus:
        monkeypatch.setattr(get_settings(), "REDIS_URL", url)
        bus = MessageBus(key_prefix=prefix)
        buses.append(bus)
        return bus

    yield factory
    for bus in buses:
        bus.close(timeout=2)


class Recorder:
    """收事件的 handler，記下事件、Delivery 與執行的 loop。"""

    def __init__(self, block: threading.Event | None = None, fail: bool = False) -> None:
        self.received: list[tuple[BusEvent, Delivery, asyncio.AbstractEventLoop]] = []
        self.block = block
        self.fail = fail
        self.started = threading.Event()

    async def __call__(self, event: BusEvent, delivery: Delivery) -> None:
        self.received.append((event, delivery, asyncio.get_running_loop()))
        self.started.set()
        if self.block is not None:
            while not self.block.is_set():
                await asyncio.sleep(0.02)
        if self.fail:
            raise RuntimeError("handler 故意失敗")

    @property
    def ns(self) -> list[int]:
        return [event.n for event, _, _ in self.received]  # type: ignore[attr-defined]


def stream(prefix: str, event_cls: type[BusEvent]) -> str:
    return f"{prefix}:events:{event_cls.event_type}"


def pending_count(raw: redis.Redis, prefix: str, event_cls: type[BusEvent], group: str = SERVICE) -> int:
    try:
        return raw.xpending(stream(prefix, event_cls), group)["pending"]
    except redis.ResponseError:
        return 0


# ── 基本收發 ─────────────────────────────────────────────


def test_handler_receives_same_event_on_registered_loop(make_bus, handler_loop):
    sender, receiver = make_bus(), make_bus()
    rec = Recorder()
    receiver.subscribe(Ping, rec, handler_loop)
    receiver.start(SERVICE, "c1")

    event = Ping(occurred_at=now(), n=1, text="中文 ok")
    sender.publish(event)

    assert wait_until(lambda: rec.received)
    got, delivery, loop = rec.received[0]
    assert got == event
    assert delivery == Delivery(redelivered=False)
    assert loop is handler_loop


def test_publish_from_other_threads_and_loops_does_not_block(make_bus, handler_loop):
    sender, receiver = make_bus(), make_bus()
    rec = Recorder()
    receiver.subscribe(Ping, rec, handler_loop)
    receiver.start(SERVICE, "c1")

    durations: list[float] = []

    def timed_publish(n: int) -> None:
        started = time.monotonic()
        sender.publish(Ping(occurred_at=now(), n=n))
        durations.append(time.monotonic() - started)

    threads = [threading.Thread(target=timed_publish, args=(n,)) for n in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    async def from_loop() -> None:
        timed_publish(3)

    asyncio.run_coroutine_threadsafe(from_loop(), handler_loop).result(5)
    asyncio.run(from_loop())
    timed_publish(5)

    assert wait_until(lambda: len(rec.received) == 6)
    assert sorted(rec.ns) == [0, 1, 2, 3, 3, 5]
    assert max(durations) < 1


def test_same_service_once_each_service_once(make_bus, handler_loop):
    sender = make_bus()
    a1, a2, b = make_bus(), make_bus(), make_bus()
    rec_a1, rec_a2, rec_b = Recorder(), Recorder(), Recorder()
    a1.subscribe(Ping, rec_a1, handler_loop)
    a2.subscribe(Ping, rec_a2, handler_loop)
    b.subscribe(Ping, rec_b, handler_loop)
    a1.start(SERVICE, "a1")
    a2.start(SERVICE, "a2")
    b.start(OTHER_SERVICE, "b1")

    for n in range(10):
        sender.publish(Ping(occurred_at=now(), n=n))

    assert wait_until(lambda: len(rec_a1.received) + len(rec_a2.received) == 10 and len(rec_b.received) == 10)
    time.sleep(0.5)
    assert sorted(rec_a1.ns + rec_a2.ns) == list(range(10))
    assert sorted(rec_b.ns) == list(range(10))


# ── 補送與時效 ───────────────────────────────────────────


def test_backlog_after_restart_respects_ttl(make_bus, handler_loop):
    sender = make_bus()
    first = make_bus()
    first.subscribe(Ping, Recorder(), handler_loop)
    first.start(SERVICE, "c1")
    time.sleep(0.3)
    first.close()

    sender.publish(Ping(occurred_at=now(), n=1))
    sender.publish(Ping(occurred_at=now() - timedelta(minutes=11), n=2))
    time.sleep(0.3)

    restarted = make_bus()
    rec = Recorder()
    restarted.subscribe(Ping, rec, handler_loop)
    restarted.start(SERVICE, "c1")

    assert wait_until(lambda: rec.received)
    time.sleep(0.5)
    assert rec.ns == [1]


def test_backlog_for_service_never_started(make_bus, handler_loop):
    sender = make_bus()
    sender.publish(Ping(occurred_at=now(), n=7))
    time.sleep(0.3)

    receiver = make_bus()
    rec = Recorder()
    receiver.subscribe(Ping, rec, handler_loop)
    receiver.start(SERVICE, "c1")

    assert wait_until(lambda: rec.ns == [7])


def test_subscribe_after_start_gets_backlog_and_new_events(make_bus, handler_loop):
    sender, receiver = make_bus(), make_bus()
    receiver.start(SERVICE, "c1")
    sender.publish(Ping(occurred_at=now(), n=1))
    time.sleep(0.3)

    rec = Recorder()
    receiver.subscribe(Ping, rec, handler_loop)
    assert wait_until(lambda: rec.ns == [1])

    sender.publish(Ping(occurred_at=now(), n=2))
    assert wait_until(lambda: rec.ns == [1, 2])


def test_killed_during_handler_is_redelivered(make_bus, handler_loop, raw, prefix):
    sender = make_bus()
    first = make_bus()
    stuck = Recorder(block=threading.Event())
    first.subscribe(Ping, stuck, handler_loop)
    first.start(SERVICE, "c1")
    sender.publish(Ping(occurred_at=now(), n=1))
    assert stuck.started.wait(5)

    first.close()
    assert pending_count(raw, prefix, Ping) == 1

    restarted = make_bus()
    rec = Recorder()
    restarted.subscribe(Ping, rec, handler_loop)
    restarted.start(SERVICE, "c1")

    assert wait_until(lambda: rec.received)
    assert rec.received[0][1] == Delivery(redelivered=True)
    assert wait_until(lambda: pending_count(raw, prefix, Ping) == 0)


def test_handler_exception_is_reported_and_acked(make_bus, handler_loop, raw, prefix, sentry):
    sender, receiver = make_bus(), make_bus()
    rec = Recorder(fail=True)
    receiver.subscribe(Ping, rec, handler_loop)
    receiver.start(SERVICE, "c1")

    sender.publish(Ping(occurred_at=now(), n=1))
    assert wait_until(lambda: sentry["handler"])
    assert isinstance(sentry["handler"][0], RuntimeError)
    assert wait_until(lambda: pending_count(raw, prefix, Ping) == 0)

    receiver.close()
    restarted = make_bus()
    rec2 = Recorder()
    restarted.subscribe(Ping, rec2, handler_loop)
    restarted.start(SERVICE, "c1")
    sender.publish(Ping(occurred_at=now(), n=2))
    assert wait_until(lambda: rec2.received)
    time.sleep(0.3)
    assert rec2.ns == [2]


def test_malformed_messages_are_acked_and_skipped(make_bus, handler_loop, raw, prefix, caplog):
    sender, receiver = make_bus(), make_bus()
    rec = Recorder()
    receiver.subscribe(Ping, rec, handler_loop)
    receiver.start(SERVICE, "c1")
    time.sleep(0.3)

    key = stream(prefix, Ping)
    occurred = now().isoformat()
    with caplog.at_level(logging.WARNING, logger="starlib.messaging.bus"):
        raw.xadd(key, {"other": "x"})  # 沒有 data 欄位
        raw.xadd(key, {"data": "不是 json"})
        raw.xadd(key, {"data": json.dumps({"event_type": "test.messaging.short", "occurred_at": occurred, "n": 1})})
        raw.xadd(key, {"data": json.dumps({"event_type": Ping.event_type, "occurred_at": occurred})})  # 缺 n
        raw.xadd(
            key,
            {"data": json.dumps({"event_type": Ping.event_type, "occurred_at": occurred, "n": 5, "extra": [1, 2]})},
        )
        sender.publish(Ping(occurred_at=now(), n=6))

        assert wait_until(lambda: rec.ns == [5, 6])
        assert wait_until(lambda: pending_count(raw, prefix, Ping) == 0)
    assert sum("略過" in r.getMessage() for r in caplog.records) == 4


def test_resubscribe_replaces_handler(make_bus, handler_loop):
    sender, receiver = make_bus(), make_bus()
    old, new = Recorder(), Recorder()
    receiver.subscribe(Ping, old, handler_loop)
    receiver.start(SERVICE, "c1")
    receiver.subscribe(Ping, new, handler_loop)
    time.sleep(0.2)

    sender.publish(Ping(occurred_at=now(), n=1))
    assert wait_until(lambda: new.received)
    time.sleep(0.3)
    assert old.received == []


# ── 過期清除與收回 ───────────────────────────────────────


def test_expired_events_trimmed_without_consumer(make_bus, raw, prefix):
    sender = make_bus()
    sender.publish(ShortLived(occurred_at=now(), n=1))
    key = stream(prefix, ShortLived)
    assert wait_until(lambda: raw.xlen(key) == 1, timeout=3)
    assert wait_until(lambda: raw.xlen(key) == 0, timeout=5)


def test_trimmed_pending_event_is_acked(make_bus, handler_loop, raw, prefix):
    sender = make_bus()
    first = make_bus()
    stuck = Recorder(block=threading.Event())
    first.subscribe(ShortLived, stuck, handler_loop)
    first.start(SERVICE, "c1")
    sender.publish(ShortLived(occurred_at=now(), n=1))
    assert stuck.started.wait(5)
    first.close()

    key = stream(prefix, ShortLived)
    assert wait_until(lambda: raw.xlen(key) == 0, timeout=5)
    assert pending_count(raw, prefix, ShortLived) == 1

    restarted = make_bus()
    rec = Recorder()
    restarted.subscribe(ShortLived, rec, handler_loop)
    restarted.start(SERVICE, "c1")
    assert wait_until(lambda: pending_count(raw, prefix, ShortLived) == 0)
    assert rec.received == []


def test_long_handler_not_reclaimed_but_dead_consumer_is(make_bus, handler_loop, raw, prefix, monkeypatch):
    monkeypatch.setattr(bus_module, "CLAIM_MIN_IDLE_MS", 500)
    sender = make_bus()

    dead = make_bus()
    dead.subscribe(Ping, Recorder(block=threading.Event()), handler_loop)
    dead.start(SERVICE, "dead")
    sender.publish(Ping(occurred_at=now(), n=1))
    assert wait_until(lambda: pending_count(raw, prefix, Ping) == 1)
    dead.close()

    release = threading.Event()
    rec = Recorder(block=release)
    alive = make_bus()
    alive.subscribe(Ping, rec, handler_loop)
    alive.start(SERVICE, "alive")
    sender.publish(Ping(occurred_at=now(), n=2))

    # 自己正在處理的 n=2 執行超過收回門檻好幾倍，也不會被自己收回
    assert wait_until(lambda: rec.received)
    time.sleep(2)
    release.set()

    assert wait_until(lambda: sorted(rec.ns) == [1, 2])
    time.sleep(1)
    assert sorted(rec.ns) == [1, 2]
    deliveries = {event.n: delivery for event, delivery, _ in rec.received}  # type: ignore[attr-defined]
    assert deliveries[1] == Delivery(redelivered=True)
    assert deliveries[2] == Delivery(redelivered=False)
    assert wait_until(lambda: pending_count(raw, prefix, Ping) == 0)


def test_group_recreated_after_data_loss(make_bus, handler_loop, raw, prefix):
    sender, receiver = make_bus(), make_bus()
    rec = Recorder()
    receiver.subscribe(Ping, rec, handler_loop)
    receiver.start(SERVICE, "c1")
    sender.publish(Ping(occurred_at=now(), n=1))
    assert wait_until(lambda: rec.ns == [1])

    # 模擬 FLUSHALL：只刪這個測試的 key，不動本機其他資料
    raw.delete(*raw.scan_iter(f"{prefix}:*"))
    time.sleep(0.5)
    sender.publish(Ping(occurred_at=now(), n=2))
    assert wait_until(lambda: rec.ns == [1, 2], timeout=10)


# ── 連不上 Redis ─────────────────────────────────────────


class FlakyProxy:
    """TCP proxy，down 時切斷所有連線並拒絕新連線，用來模擬 Redis 停掉又恢復。"""

    def __init__(self, target_host: str, target_port: int) -> None:
        self.target = (target_host, target_port)
        self.down = False
        self._writers: set[asyncio.StreamWriter] = set()
        self._runner = LoopThread()
        self.port = asyncio.run_coroutine_threadsafe(self._serve(), self._runner.loop).result(5)

    async def _serve(self) -> int:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        return self._server.sockets[0].getsockname()[1]

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        if self.down:
            writer.close()
            return
        up_reader, up_writer = await asyncio.open_connection(*self.target)
        self._writers.update({writer, up_writer})

        async def pipe(src: asyncio.StreamReader, dst: asyncio.StreamWriter) -> None:
            try:
                while data := await src.read(65536):
                    dst.write(data)
                    await dst.drain()
            except OSError:
                pass
            finally:
                dst.close()

        await asyncio.gather(pipe(reader, up_writer), pipe(up_reader, writer))

    def set_down(self, down: bool) -> None:
        async def apply() -> None:
            self.down = down
            if down:
                for w in list(self._writers):
                    w.close()
                self._writers.clear()

        asyncio.run_coroutine_threadsafe(apply(), self._runner.loop).result(5)

    def stop(self) -> None:
        self.set_down(True)

        async def shutdown() -> None:
            self._server.close()
            tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        asyncio.run_coroutine_threadsafe(shutdown(), self._runner.loop).result(5)
        self._runner.stop()


@pytest.fixture
def proxy(redis_url: str) -> Iterator[tuple[FlakyProxy, str]]:
    parsed = redis.connection.parse_url(redis_url)
    p = FlakyProxy(parsed.get("host", "127.0.0.1"), parsed.get("port", 6379))
    url = redis_url.replace(f"{parsed.get('host')}:{parsed.get('port', 6379)}", f"127.0.0.1:{p.port}")
    if url == redis_url:
        pytest.skip("無法改寫 REDIS_URL 指向 proxy")
    yield p, url
    p.stop()


def test_redis_url_unset(make_bus, caplog):
    with caplog.at_level(logging.WARNING, logger="starlib.messaging"):
        bus = make_bus(url=None)
        bus.publish(Ping(occurred_at=now(), n=1))
        bus.start(SERVICE, "c1")
        with pytest.raises(BusUnavailable):
            bus.run(bus.get_client()).result(5)
        time.sleep(0.3)
    assert sum("REDIS_URL" in r.getMessage() for r in caplog.records) == 1


def test_redis_down_then_recovers(make_bus, handler_loop, proxy, sentry):
    p, url = proxy
    p.set_down(True)
    sender, receiver = make_bus(url), make_bus(url)
    rec = Recorder()
    receiver.subscribe(Ping, rec, handler_loop)

    started = time.monotonic()
    sender.publish(Ping(occurred_at=now(), n=1))
    receiver.start(SERVICE, "c1")
    assert time.monotonic() - started < 1
    with pytest.raises(BusUnavailable):
        sender.run(sender.get_client()).result(5)

    p.set_down(False)
    assert wait_until(lambda: sender.run(_is_up(sender)).result(5), timeout=5)
    assert wait_until(lambda: receiver.run(_is_up(receiver)).result(5), timeout=5)
    time.sleep(0.5)
    sender.publish(Ping(occurred_at=now(), n=2))
    assert wait_until(lambda: rec.ns == [2])


def test_sentry_reports_only_state_changes(make_bus, handler_loop, proxy, sentry, caplog):
    p, url = proxy
    sender, receiver = make_bus(url), make_bus(url)
    rec = Recorder()
    receiver.subscribe(Ping, rec, handler_loop)
    receiver.start(SERVICE, "c1")
    sender.publish(Ping(occurred_at=now(), n=1))
    assert wait_until(lambda: rec.ns == [1])

    p.set_down(True)
    assert wait_until(lambda: not sender.run(_is_up(sender)).result(5), timeout=5)
    with caplog.at_level(logging.WARNING, logger="starlib.messaging"):
        for n in range(5):
            sender.publish(Ping(occurred_at=now(), n=10 + n))
        time.sleep(1.5)
    assert any("丟棄" in r.getMessage() for r in caplog.records)
    assert all(r.exc_info is None for r in caplog.records)

    p.set_down(False)
    assert wait_until(lambda: sender.run(_is_up(sender)).result(5), timeout=5)
    assert wait_until(lambda: receiver.run(_is_up(receiver)).result(5), timeout=5)
    time.sleep(0.5)
    sender.publish(Ping(occurred_at=now(), n=2))
    assert wait_until(lambda: 2 in rec.ns)

    # 兩個 bus 各自追蹤連線：每個 bus 一次斷線、一次恢復
    assert len(sentry["exception"]) == 2
    assert sentry["message"] == ["Redis 連線恢復", "Redis 連線恢復"]


async def _is_up(bus: MessageBus) -> bool:
    try:
        await bus.get_client()
    except BusUnavailable:
        return False
    return True


def test_on_connected_late_registration_and_reconnect(make_bus, proxy):
    p, url = proxy
    bus = make_bus(url)
    assert wait_until(lambda: bus.run(_is_up(bus)).result(5))

    calls: list[bool] = []

    async def callback(reconnect: bool) -> None:
        calls.append(reconnect)

    bus.on_connected(callback)
    assert wait_until(lambda: calls == [False])

    p.set_down(True)
    assert wait_until(lambda: not bus.run(_is_up(bus)).result(5), timeout=5)
    p.set_down(False)
    assert wait_until(lambda: calls == [False, True], timeout=5)


def test_on_start_called_after_start(make_bus):
    bus = make_bus()
    calls: list[tuple[str, str]] = []

    async def before(service: str, consumer: str) -> None:
        calls.append(("before", service, consumer))  # type: ignore[arg-type]

    async def after(service: str, consumer: str) -> None:
        calls.append(("after", service, consumer))  # type: ignore[arg-type]

    bus.on_start(before)
    time.sleep(0.1)
    assert calls == []
    bus.start(SERVICE, "c1")
    bus.start(SERVICE, "ignored")
    bus.on_start(after)
    assert wait_until(lambda: len(calls) == 2)
    assert calls == [("before", SERVICE, "c1"), ("after", SERVICE, "c1")]
