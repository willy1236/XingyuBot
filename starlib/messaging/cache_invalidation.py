"""快取失效通知：Redis Pub/Sub，每個實例（含發送端自己）都收，不保存。

線路格式見 docs/messaging-contract.md〈快取失效〉。只用 MessageBus 的擴充點，不改 bus。
"""

import asyncio
import json
import logging
import threading
from collections.abc import Awaitable, Callable
from typing import Any

import redis.asyncio as aioredis

from sentry_bootstrap import capture_exception_safe

from .bus import MessageBus, get_bus
from .connection import CONNECTION_ERRORS, SENTRY_TAGS, BusUnavailable

log = logging.getLogger(__name__)

type InvalidateHandler = Callable[[str | None], Awaitable[None]]

# 沒收到訊息時多久醒來一次；也決定取消與重連的反應速度
POLL_TIMEOUT = 1.0
# 訂閱中斷後重新訂閱的退避：從 1 秒倍增，上限 30 秒
RESUBSCRIBE_INITIAL_DELAY = 1.0
RESUBSCRIBE_MAX_DELAY = 30.0


class _Listener:
    """一個 bus 實例的訂閱與已註冊的處理函式。"""

    def __init__(self, bus: MessageBus) -> None:
        self._bus = bus
        self._channel = f"{bus.key_prefix}:cache-invalidate"
        self._handlers: dict[str, tuple[InvalidateHandler, asyncio.AbstractEventLoop]] = {}
        self._lock = threading.Lock()
        self._task: asyncio.Task[None] | None = None

    def register(self, cache: str, handler: InvalidateHandler, loop: asyncio.AbstractEventLoop) -> None:
        with self._lock:
            self._handlers[cache] = (handler, loop)

    # ── 以下只在 bus loop 上執行 ──────────────────────────

    async def on_connected(self, reconnect: bool) -> None:
        """連上（含重連）時重新訂閱；重連表示斷線期間可能漏收，所有已註冊的快取都丟掉一次。"""
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        self._task = asyncio.get_running_loop().create_task(self._listen(invalidate_all=reconnect))

    async def _listen(self, *, invalidate_all: bool) -> None:
        delay = RESUBSCRIBE_INITIAL_DELAY
        reported = False  # 同一段持續失敗只回報 Sentry 一次，訂閱成功後才重置
        while True:
            try:
                client = await self._bus.get_client()
                pubsub = client.pubsub()
                try:
                    await pubsub.subscribe(self._channel)
                    if invalidate_all:
                        self._dispatch_all()
                    # 之後在這條訂閱自己中斷後重新訂閱，也要丟掉一次
                    invalidate_all = True
                    delay = RESUBSCRIBE_INITIAL_DELAY
                    reported = False
                    await self._pump(pubsub)
                finally:
                    await _close_quietly(pubsub)
            except asyncio.CancelledError:
                raise
            except BusUnavailable:
                # 連線中斷，等 bus 重連後 on_connected 會重新開始
                return
            except CONNECTION_ERRORS as exc:
                log.warning("快取失效的訂閱中斷，%.0f 秒後重新訂閱：%r", delay, exc)
            except Exception as exc:
                if not reported:
                    reported = True
                    capture_exception_safe(exc, tags=SENTRY_TAGS)
                log.warning("快取失效的訂閱發生未預期的錯誤，%.0f 秒後重新訂閱：%r", delay, exc)
            await asyncio.sleep(delay)
            delay = min(delay * 2, RESUBSCRIBE_MAX_DELAY)

    async def _pump(self, pubsub: aioredis.client.PubSub) -> None:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=POLL_TIMEOUT)
            if message is not None:
                self._handle_message(message.get("data"))

    def _handle_message(self, data: Any) -> None:
        try:
            payload = json.loads(data)
            cache, key = payload["cache"], payload["key"]
            if not isinstance(cache, str) or not (key is None or isinstance(key, str)):
                raise ValueError("cache 或 key 型別不符")
        except (TypeError, ValueError, KeyError) as exc:
            log.warning("快取失效訊息格式錯誤，略過：%r（%r）", data, exc)
            return
        self._dispatch(cache, key)

    def _dispatch_all(self) -> None:
        with self._lock:
            caches = list(self._handlers)
        for cache in caches:
            self._dispatch(cache, None)

    def _dispatch(self, cache: str, key: str | None) -> None:
        with self._lock:
            entry = self._handlers.get(cache)
        if entry is None:
            return
        handler, loop = entry
        coro = handler(key)
        try:
            future = asyncio.run_coroutine_threadsafe(coro, loop)
        except RuntimeError as exc:
            coro.close()
            log.warning("快取 %s 的 handler loop 已關閉，略過失效通知：%s", cache, exc)
            return
        future.add_done_callback(lambda done: _report(cache, done))


def _report(cache: str, future: asyncio.Future[None] | Any) -> None:
    if future.cancelled():
        return
    exc = future.exception()
    if exc is not None:
        capture_exception_safe(exc, tags={**SENTRY_TAGS, "cache": cache})
        log.error("快取 %s 的失效 handler 發生錯誤", cache, exc_info=exc)


async def _close_quietly(pubsub: aioredis.client.PubSub) -> None:
    try:
        await pubsub.aclose()
    except Exception as exc:
        log.debug("關閉 Pub/Sub 連線失敗：%r", exc)


_listeners: dict[MessageBus, _Listener] = {}
_listeners_lock = threading.Lock()


def on_invalidate(
    cache: str,
    handler: InvalidateHandler,
    loop: asyncio.AbstractEventLoop,
    *,
    bus: MessageBus | None = None,
) -> None:
    """註冊快取失效 handler，在 loop 上執行；參數是失效的 key，None 表示整個快取。
    同一個 cache 再註冊會取代；bus=None 表示 get_bus()。

    收到失效通知前不保證已訂閱：Redis 連不上時之後連上才開始收，斷線重連時所有已註冊的快取都會收到一次整個失效。
    """
    bus = bus or get_bus()
    with _listeners_lock:
        listener = _listeners.get(bus)
        created = listener is None
        if listener is None:
            listener = _listeners[bus] = _Listener(bus)
    listener.register(cache, handler, loop)
    if created:
        bus.on_connected(listener.on_connected)


def invalidate(cache: str, key: str | None = None, *, bus: MessageBus | None = None) -> None:
    """通知所有實例（含自己）丟掉快取。執行緒安全；key=None 表示整個快取；Redis 連不上時記 warning 後返回。"""
    bus = bus or get_bus()
    data = json.dumps({"cache": cache, "key": key}, ensure_ascii=False)
    bus.run(_publish(bus, cache, data)).add_done_callback(_log_if_failed)


async def _publish(bus: MessageBus, cache: str, data: str) -> None:
    try:
        client = await bus.get_client()
        await client.publish(f"{bus.key_prefix}:cache-invalidate", data)
    except BusUnavailable:
        log.warning("Redis 連不上，快取 %s 的失效通知未送出", cache)
    except Exception as exc:
        log.warning("送出快取 %s 的失效通知失敗：%r", cache, exc)


def _log_if_failed(future: Any) -> None:
    if not future.cancelled() and future.exception() is not None:
        log.warning("快取失效通知未送出（bus 已關閉）：%r", future.exception())
