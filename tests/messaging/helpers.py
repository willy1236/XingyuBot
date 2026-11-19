"""訊息匯流排測試共用：Redis 連線、可斷線的 proxy 與 `make_bus` 等 fixture（需要本機 Redis）。"""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Callable, Iterator
from uuid import uuid4

import pytest
import redis

from starlib.messaging import BusUnavailable, MessageBus
from starlib.messaging import bus as bus_module
from starlib.messaging import connection as connection_module
from starlib.settings import get_settings


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


async def _is_up(bus: MessageBus) -> bool:
    try:
        await bus.get_client()
    except BusUnavailable:
        return False
    return True
