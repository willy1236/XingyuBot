"""Redis 連線管理：追蹤連線狀態、斷線後以指數退避重連，只在狀態改變時回報 Sentry。

所有方法都只能在 bus loop 上呼叫。
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from enum import Enum, auto

import redis.asyncio as aioredis
from redis.asyncio.retry import Retry
from redis.backoff import NoBackoff
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from sentry_bootstrap import capture_exception_safe, capture_message_safe

log = logging.getLogger(__name__)

# 重連退避：從 1 秒開始倍增，上限 30 秒
RECONNECT_INITIAL_DELAY = 1.0
RECONNECT_MAX_DELAY = 30.0
# 連上之後多久 ping 一次確認連線還在
HEALTH_CHECK_INTERVAL = 5.0
CONNECT_TIMEOUT = 5.0
# 要大於消費端 XREADGROUP 的 BLOCK 時間
SOCKET_TIMEOUT = 15.0

SENTRY_TAGS = {"component": "messaging"}

# 這些例外代表連不上 Redis，其他例外（例如指令錯誤）不影響連線狀態
CONNECTION_ERRORS: tuple[type[BaseException], ...] = (RedisConnectionError, RedisTimeoutError, OSError)


class BusUnavailable(Exception):
    """Redis 沒設定、連不上，或 bus 已關閉。"""


class _State(Enum):
    CONNECTING = auto()  # 還沒嘗試完第一次連線
    UP = auto()
    DOWN = auto()


ConnectedCallback = Callable[[bool], Awaitable[None]]


class RedisConnection:
    def __init__(self, url: str | None) -> None:
        self._client: aioredis.Redis | None = None
        self._state = _State.CONNECTING
        self._closed = False
        self._first_attempt_done = asyncio.Event()
        self._up = asyncio.Event()
        self._failed = asyncio.Event()
        self._supervisor: asyncio.Task[None] | None = None
        # callback -> 是否已經被呼叫過；第一次呼叫的 reconnect 為 False
        self._callbacks: dict[ConnectedCallback, bool] = {}

        if url is None:
            log.warning("REDIS_URL 未設定，跨 process 訊息停用：事件不會送出也收不到")
            self._state = _State.DOWN
            self._first_attempt_done.set()
            return
        try:
            self._client = aioredis.Redis.from_url(
                url,
                socket_connect_timeout=CONNECT_TIMEOUT,
                socket_timeout=SOCKET_TIMEOUT,
                decode_responses=True,
                # 不讓 redis-py 自己重試：連不上要立即回報，重連由 supervisor 退避處理
                retry=Retry(NoBackoff(), 0),
            )
        except ValueError as exc:
            log.warning("REDIS_URL 格式不正確，跨 process 訊息停用：%s", exc)
            self._state = _State.DOWN
            self._first_attempt_done.set()
            return
        self._supervisor = asyncio.get_running_loop().create_task(self._supervise(), name="messaging-connection")

    @property
    def configured(self) -> bool:
        return self._client is not None

    @property
    def is_up(self) -> bool:
        return self._state is _State.UP and not self._closed

    def client(self) -> aioredis.Redis:
        if self._client is None or not self.is_up:
            raise BusUnavailable("Redis 連不上")
        return self._client

    async def wait_first_attempt(self) -> None:
        await self._first_attempt_done.wait()

    async def wait_up(self) -> None:
        await self._up.wait()

    def report_failure(self, exc: BaseException) -> None:
        """操作時發現連不上：標成斷線，交給 supervisor 退避重連。"""
        if self._closed or self._state is not _State.UP:
            return
        self._mark_down(exc)
        self._failed.set()

    def add_callback(self, callback: ConnectedCallback) -> None:
        self._callbacks[callback] = self._callbacks.get(callback, False)
        if self.is_up:
            self._fire(callback)

    async def close(self) -> None:
        self._closed = True
        self._up.clear()
        if self._supervisor is not None:
            self._supervisor.cancel()
            await asyncio.gather(self._supervisor, return_exceptions=True)
        if self._client is not None:
            await self._client.aclose()

    async def _supervise(self) -> None:
        assert self._client is not None
        delay = RECONNECT_INITIAL_DELAY
        while not self._closed:
            if self._state is not _State.UP:
                try:
                    await self._client.ping()
                except CONNECTION_ERRORS as exc:
                    self._mark_down(exc)
                    self._first_attempt_done.set()
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, RECONNECT_MAX_DELAY)
                    continue
                delay = RECONNECT_INITIAL_DELAY
                self._mark_up()
                continue

            try:
                await asyncio.wait_for(self._failed.wait(), HEALTH_CHECK_INTERVAL)
            except TimeoutError:
                pass
            self._failed.clear()
            if self._state is not _State.UP:
                continue
            try:
                await self._client.ping()
            except CONNECTION_ERRORS as exc:
                self._mark_down(exc)

    def _mark_down(self, exc: BaseException) -> None:
        previous = self._state
        self._state = _State.DOWN
        self._up.clear()
        if previous is _State.DOWN:
            log.warning("Redis 仍然連不上：%s", exc)
            return
        log.warning("Redis 連線中斷，事件會丟棄直到恢復：%s", exc)
        if isinstance(exc, Exception):
            capture_exception_safe(exc, tags=SENTRY_TAGS)

    def _mark_up(self) -> None:
        # 之前回報過斷線（包含啟動時就連不上），恢復時才回報，Sentry 上斷線與恢復成對
        recovered = self._state is _State.DOWN
        self._state = _State.UP
        self._first_attempt_done.set()
        self._up.set()
        if recovered:
            log.info("Redis 連線恢復")
            capture_message_safe("Redis 連線恢復", level="info", tags=SENTRY_TAGS)
        else:
            log.info("Redis 已連線")
        for callback in self._callbacks:
            self._fire(callback)

    def _fire(self, callback: ConnectedCallback) -> None:
        reconnect = self._callbacks[callback]
        self._callbacks[callback] = True
        asyncio.get_running_loop().create_task(self._run_callback(callback, reconnect))

    @staticmethod
    async def _run_callback(callback: ConnectedCallback, reconnect: bool) -> None:
        try:
            await callback(reconnect)
        except Exception as exc:
            capture_exception_safe(exc, tags=SENTRY_TAGS)
            log.error("messaging 的 on_connected callback 失敗", exc_info=exc)
