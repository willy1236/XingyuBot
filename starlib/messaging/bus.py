"""跨 process 事件廣播：Redis Streams，每種事件一條 stream、每個接收服務一個 consumer group。

線路格式與語意見 docs/messaging-contract.md。
"""

import asyncio
import concurrent.futures
import json
import logging
import socket
import threading
import time
from collections import deque
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as aioredis
from pydantic import ValidationError
from redis.exceptions import ResponseError

from sentry_bootstrap import capture_exception_safe
from starlib.settings import get_settings

from .connection import CONNECTION_ERRORS, SENTRY_TAGS, BusUnavailable, RedisConnection
from .events import BusEvent, registry
from .runtime import BusRuntime

log = logging.getLogger(__name__)

DEFAULT_KEY_PREFIX = "xingyubot"
# 修剪過期事件、補建 consumer group、收回其他 consumer 事件的週期
MAINTENANCE_INTERVAL = 30.0
# 同服務其他 consumer 的事件閒置超過這個時間就收回，要大於 handler 正常執行時間
CLAIM_MIN_IDLE_MS = 120_000
CLAIM_BATCH = 100
READ_BLOCK_MS = 5_000
# stream entry 裡放 JSON 的欄位名稱
DATA_FIELD = "data"


@dataclass(frozen=True)
class Delivery:
    redelivered: bool  # 之前被取出但沒 ack，這次是重送


type Handler[E: BusEvent] = Callable[[E, Delivery], Awaitable[None]]


@dataclass(frozen=True)
class _Subscription:
    event_cls: type[BusEvent]
    handler: Handler[Any]
    loop: asyncio.AbstractEventLoop


type _Entry = tuple[str, dict[str, str] | None]


class MessageBus:
    """跨 process 事件 bus。正式程式用 get_bus()；直接建立只給測試，同一 process 可以有多個實例。

    invariant：handler 回傳或拋例外都會 ack；只有 process 在 handler 執行中結束才會重送，
    所以同一事件可能被處理兩次，handler 要能承受。
    """

    def __init__(self, key_prefix: str = DEFAULT_KEY_PREFIX) -> None:
        self._key_prefix = key_prefix
        self._closed = False
        self._lock = threading.Lock()
        self._start_requested = False

        # 以下狀態只在 bus loop 上讀寫
        self._service: str | None = None
        self._consumer: str | None = None
        self._subs: dict[str, _Subscription] = {}
        self._readers: dict[str, asyncio.Task[None]] = {}
        self._claimed: dict[str, deque[_Entry]] = {}
        self._start_callbacks: list[Callable[[str, str], Awaitable[None]]] = []
        self._tasks: set[asyncio.Task[Any]] = set()
        self._publishes: set[asyncio.Task[None]] = set()
        # close() 時讓正在處理的事件跑完、ack 後才取消讀取
        self._stopping = False
        self._handling = 0
        self._idle: asyncio.Event

        self._runtime = BusRuntime(name=f"messaging[{key_prefix}]")
        self._conn: RedisConnection = self._runtime.run(self._init(get_settings().REDIS_URL)).result()

    @property
    def key_prefix(self) -> str:
        return self._key_prefix

    # ── 對外介面：執行緒安全 ──────────────────────────────

    def publish(self, event: BusEvent) -> None:
        """執行緒安全，交給 bus loop 後立即返回，永不拋例外；連不上時事件丟棄並記 warning。"""
        try:
            event_type = type(event).event_type
            data = json.dumps({"event_type": event_type, **event.model_dump(mode="json")}, ensure_ascii=False)
        except Exception as exc:
            log.warning("無法序列化事件 %r，丟棄：%s", event, exc)
            return
        if self._closed or not self._runtime.call_soon(lambda: self._spawn_publish(event_type, data)):
            log.warning("bus 已關閉，丟棄事件 %s", event_type)

    def subscribe[E: BusEvent](self, event_cls: type[E], handler: Handler[E], loop: asyncio.AbstractEventLoop) -> None:
        """handler 在 loop 上執行；start 前後都可呼叫；同一事件類型再次 subscribe 會取代舊的 handler。"""
        event_type = getattr(event_cls, "event_type", None)
        if event_type is None or registry.get(event_type) is not event_cls:
            raise TypeError(f"{event_cls!r} 不是已登錄的 BusEvent")
        sub = _Subscription(event_cls, handler, loop)
        self._runtime.call_soon(lambda: self._add_subscription(sub))

    def start(self, service: str, consumer: str | None = None) -> None:
        """以 service 身分開始消費；呼叫端要在「能實際處理事件」之後才呼叫；重複呼叫無效果。"""
        with self._lock:
            if self._start_requested or self._closed:
                return
            self._start_requested = True
        consumer = consumer or f"{service}@{socket.gethostname()}"
        self._runtime.call_soon(lambda: self._begin(service, consumer))

    def close(self, timeout: float = 5) -> None:
        """先等已排入的發送與正在處理的事件完成（最多 timeout 的一半），再停止讀取、關閉連線。"""
        if self._runtime.in_loop():
            raise RuntimeError("不能在 bus loop 上呼叫 close()")
        with self._lock:
            if self._closed:
                return
            self._closed = True
        started = time.monotonic()
        try:
            self._runtime.run(self._shutdown(timeout)).result(timeout)
        except Exception as exc:
            log.warning("關閉 messaging bus 時發生錯誤：%r", exc)
        self._runtime.stop(max(timeout - (time.monotonic() - started), 0.5))

    # ── 擴充點：callback 都在 bus loop 上執行 ─────────────

    def run[T](self, coro: Coroutine[Any, Any, T]) -> concurrent.futures.Future[T]:
        """執行緒安全，把 coroutine 排到 bus loop。"""
        return self._runtime.run(coro)

    async def get_client(self) -> aioredis.Redis:
        """只能在 bus loop 上呼叫；連不上時 raise BusUnavailable。"""
        if not self._runtime.in_loop():
            raise RuntimeError("get_client() 只能在 bus loop 上呼叫，請用 bus.run() 排進去")
        await self._conn.wait_first_attempt()
        return self._conn.client()

    def on_connected(self, callback: Callable[[bool], Awaitable[None]]) -> None:
        """參數 reconnect：首次連上為 False，之後每次重連為 True；註冊時已連上就立即以 False 呼叫一次。"""
        self._runtime.call_soon(lambda: self._conn.add_callback(callback))

    def on_start(self, callback: Callable[[str, str], Awaitable[None]]) -> None:
        """start(service, consumer) 時呼叫；已經 start 過才註冊的會立即呼叫。"""
        self._runtime.call_soon(lambda: self._add_start_callback(callback))

    # ── bus loop 內部 ────────────────────────────────────

    async def _init(self, url: str | None) -> RedisConnection:
        self._idle = asyncio.Event()
        self._idle.set()
        conn = RedisConnection(url)
        conn.add_callback(self._on_connected)
        self._spawn(self._maintain())
        return conn

    def _stream_key(self, event_type: str) -> str:
        return f"{self._key_prefix}:events:{event_type}"

    def _spawn(self, coro: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
        task = asyncio.get_running_loop().create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    def _spawn_publish(self, event_type: str, data: str) -> None:
        task = self._spawn(self._xadd(event_type, data))
        self._publishes.add(task)
        task.add_done_callback(self._publishes.discard)

    async def _xadd(self, event_type: str, data: str) -> None:
        await self._conn.wait_first_attempt()
        try:
            client = self._conn.client()
        except BusUnavailable:
            if self._conn.configured:
                log.warning("Redis 連不上，丟棄事件 %s", event_type)
            else:
                log.debug("REDIS_URL 未設定，丟棄事件 %s", event_type)
            return
        try:
            await client.xadd(self._stream_key(event_type), {DATA_FIELD: data})
        except CONNECTION_ERRORS as exc:
            self._conn.report_failure(exc)
            log.warning("送出事件 %s 失敗，丟棄：%r", event_type, exc)
        except ResponseError as exc:
            log.warning("送出事件 %s 失敗，丟棄：%s", event_type, exc)

    def _add_subscription(self, sub: _Subscription) -> None:
        self._subs[sub.event_cls.event_type] = sub
        if self._service is not None:
            self._ensure_reader(sub.event_cls.event_type)

    def _begin(self, service: str, consumer: str) -> None:
        self._service = service
        self._consumer = consumer
        log.info("messaging bus 以 %s（consumer %s）開始消費", service, consumer)
        for event_type in self._subs:
            self._ensure_reader(event_type)
        for callback in self._start_callbacks:
            self._spawn(self._run_start_callback(callback))

    def _add_start_callback(self, callback: Callable[[str, str], Awaitable[None]]) -> None:
        self._start_callbacks.append(callback)
        if self._service is not None:
            self._spawn(self._run_start_callback(callback))

    async def _run_start_callback(self, callback: Callable[[str, str], Awaitable[None]]) -> None:
        assert self._service is not None and self._consumer is not None
        try:
            await callback(self._service, self._consumer)
        except Exception as exc:
            capture_exception_safe(exc, tags=SENTRY_TAGS)
            log.error("messaging 的 on_start callback 失敗", exc_info=exc)

    def _ensure_reader(self, event_type: str) -> None:
        task = self._readers.get(event_type)
        if task is None or task.done():
            self._readers[event_type] = self._spawn(self._read_loop(event_type))

    async def _on_connected(self, reconnect: bool) -> None:
        del reconnect
        await self._run_maintenance(claim=False)

    async def _maintain(self) -> None:
        while True:
            await asyncio.sleep(MAINTENANCE_INTERVAL)
            if not self._conn.is_up:
                continue
            try:
                await self._run_maintenance(claim=True)
            except Exception as exc:
                # 沒預期的例外不能讓維護停掉，否則修剪與收回事件都會跟著停
                capture_exception_safe(exc, tags=SENTRY_TAGS)
                log.error("messaging 維護任務發生未預期的錯誤", exc_info=exc)

    async def _run_maintenance(self, *, claim: bool) -> None:
        try:
            client = self._conn.client()
            for event_cls in list(registry.values()):
                for receiver in event_cls.receivers:
                    await self._ensure_group(client, self._stream_key(event_cls.event_type), receiver)
            await self._trim(client)
            if claim and self._service is not None:
                for event_type in list(self._subs):
                    await self._claim_stale(client, event_type)
        except BusUnavailable:
            return
        except CONNECTION_ERRORS as exc:
            self._conn.report_failure(exc)
            log.warning("messaging 維護任務失敗：%r", exc)
        except ResponseError as exc:
            log.warning("messaging 維護任務失敗：%s", exc)

    @staticmethod
    async def _ensure_group(client: aioredis.Redis, stream: str, group: str) -> None:
        try:
            await client.xgroup_create(stream, group, id="0", mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def _trim(self, client: aioredis.Redis) -> None:
        now_ms = int(time.time() * 1000)
        for event_cls in list(registry.values()):
            min_id = now_ms - int(event_cls.ttl.total_seconds() * 1000)
            # 一定要精確修剪：近似修剪（~）在事件量小時不會刪任何東西
            await client.xtrim(self._stream_key(event_cls.event_type), minid=min_id, approximate=False)

    async def _claim_stale(self, client: aioredis.Redis, event_type: str) -> None:
        """收回同服務其他已死 consumer 留下的事件；跳過自己的，避免收回自己正在處理的那筆。"""
        stream = self._stream_key(event_type)
        try:
            pending = await client.xpending_range(stream, self._service, "-", "+", CLAIM_BATCH, idle=CLAIM_MIN_IDLE_MS)
        except ResponseError as exc:
            if _is_missing_group(exc):
                await self._ensure_group(client, stream, self._service)
                return
            raise
        ids = [item["message_id"] for item in pending if item["consumer"] != self._consumer]
        if not ids:
            return
        claimed = await client.xclaim(stream, self._service, self._consumer, CLAIM_MIN_IDLE_MS, ids)
        queue = self._claimed.setdefault(event_type, deque())
        returned: set[str] = set()
        for entry_id, fields in claimed:
            returned.add(entry_id)
            if fields:
                queue.append((entry_id, fields))
            else:
                await client.xack(stream, self._service, entry_id)
        # 內容已被修剪的 entry 不會回傳，直接 ack 掉。Redis 7 以上 XCLAIM 本身就會把它們移出待確認清單，這裡只是保險
        missing = [entry_id for entry_id in ids if entry_id not in returned]
        if missing:
            await client.xack(stream, self._service, *missing)
        if queue:
            log.info("收回 %d 筆 %s 事件重新處理", len(queue), event_type)

    async def _read_loop(self, event_type: str) -> None:
        assert self._service is not None and self._consumer is not None
        stream = self._stream_key(event_type)
        group, consumer = self._service, self._consumer
        # 加入讀取時、以及斷線恢復後，先讀回自己還沒 ack 的事件
        backlog = True
        while not self._stopping:
            await self._conn.wait_up()
            try:
                client = self._conn.client()
                claimed = self._claimed.get(event_type)
                if claimed:
                    entry_id, fields = claimed.popleft()
                    await self._handle_entry(client, event_type, entry_id, fields, redelivered=True)
                    continue
                if backlog:
                    entries = _entries(await client.xreadgroup(group, consumer, {stream: "0"}, count=CLAIM_BATCH))
                    if not entries:
                        backlog = False
                    for entry_id, fields in entries:
                        await self._handle_entry(client, event_type, entry_id, fields, redelivered=True)
                    continue
                response = await client.xreadgroup(group, consumer, {stream: ">"}, count=1, block=READ_BLOCK_MS)
                for entry_id, fields in _entries(response):
                    await self._handle_entry(client, event_type, entry_id, fields, redelivered=False)
            except BusUnavailable:
                continue
            except CONNECTION_ERRORS as exc:
                self._conn.report_failure(exc)
                log.warning("讀取 %s 事件失敗：%r", event_type, exc)
                backlog = True
            except ResponseError as exc:
                backlog = True
                if _is_missing_group(exc):
                    await self._recreate_group(stream, group)
                else:
                    log.warning("讀取 %s 事件失敗：%s", event_type, exc)
                    await asyncio.sleep(1)
            except Exception as exc:
                # 沒預期的例外不能讓這條 stream 停止消費
                capture_exception_safe(exc, tags={**SENTRY_TAGS, "event_type": event_type})
                log.error("讀取 %s 事件發生未預期的錯誤", event_type, exc_info=exc)
                backlog = True
                await asyncio.sleep(1)

    async def _recreate_group(self, stream: str, group: str) -> None:
        log.warning("consumer group %s 不在 %s 上（Redis 資料可能遺失），重新建立", group, stream)
        try:
            await self._ensure_group(self._conn.client(), stream, group)
        except BusUnavailable:
            pass
        except CONNECTION_ERRORS as exc:
            self._conn.report_failure(exc)
        except ResponseError as exc:
            log.warning("重新建立 consumer group 失敗：%s", exc)
            await asyncio.sleep(1)

    async def _handle_entry(
        self,
        client: aioredis.Redis,
        event_type: str,
        entry_id: str,
        fields: dict[str, str] | None,
        *,
        redelivered: bool,
    ) -> None:
        if self._stopping:
            return  # close() 之後取到的事件不處理也不 ack，留在待確認清單，下次啟動時重送
        self._handling += 1
        self._idle.clear()
        try:
            sub = self._subs.get(event_type)
            try:
                event = self._decode(sub, event_type, entry_id, fields) if sub is not None else None
            except Exception as exc:
                # 格式錯誤在 _decode 內已處理；到這裡的是事件 model 的程式錯誤（例如 validator 拋出 pydantic 不會包裝的例外），
                # 回報 Sentry 讓人發現，事件照樣 ack 掉，不卡住這條 stream
                capture_exception_safe(exc, tags={**SENTRY_TAGS, "event_type": event_type})
                log.error("%s 事件 %s 解析時發生未預期的錯誤，略過", event_type, entry_id, exc_info=exc)
                event = None
            if sub is not None and event is not None:
                if not await self._dispatch(sub, event, Delivery(redelivered=redelivered)):
                    return  # handler 沒有機會處理完（loop 已關閉或被取消），不 ack，留在待確認清單，下次啟動時重送
            await client.xack(self._stream_key(event_type), self._service, entry_id)
        finally:
            self._handling -= 1
            if self._handling == 0:
                self._idle.set()

    @staticmethod
    def _decode(sub: _Subscription, event_type: str, entry_id: str, fields: dict[str, str] | None) -> BusEvent | None:
        if not fields:
            return None  # 內容已被修剪
        try:
            payload = json.loads(fields[DATA_FIELD])
            if not isinstance(payload, dict):
                raise ValueError("內容不是 JSON object")
        except (KeyError, ValueError) as exc:
            log.warning("%s 事件 %s 格式錯誤，略過：%r", event_type, entry_id, exc)
            return None
        if payload.get("event_type") != event_type:
            log.warning(
                "%s 事件 %s 的 event_type 是 %r，跟 stream 不符，略過", event_type, entry_id, payload.get("event_type")
            )
            return None
        try:
            event = sub.event_cls.model_validate(payload)
        except ValidationError as exc:
            log.warning("%s 事件 %s 欄位不符，略過：%s", event_type, entry_id, exc)
            return None
        if event.expired(datetime.now(UTC)):
            log.info("%s 事件 %s 已超過時效，略過", event_type, entry_id)
            return None
        return event

    @staticmethod
    async def _dispatch(sub: _Subscription, event: BusEvent, delivery: Delivery) -> bool:
        """交給 handler 執行。回傳 False 表示 handler 沒有機會處理完（它的 loop 已關閉或被取消），事件不該 ack。

        handler 自己拋例外算處理過了：記 log、回報 Sentry，照樣回傳 True。
        """
        try:
            coro = sub.handler(event, delivery)
            try:
                future = asyncio.run_coroutine_threadsafe(coro, sub.loop)
            except RuntimeError as exc:
                coro.close()
                log.warning("%s 的 handler loop 已關閉，事件留待重送：%s", event.event_type, exc)
                return False
            await asyncio.wrap_future(future)
        except asyncio.CancelledError as exc:
            current = asyncio.current_task()
            if current is not None and current.cancelling():
                raise
            # handler 在它自己的 loop 上被取消（例如收到信號，那個 loop 正在關閉）：處理到哪裡不明，留待重送
            log.warning("%s 事件的 handler 被取消，事件留待重送：%r", event.event_type, exc)
            return False
        except Exception as exc:
            capture_exception_safe(exc, tags={**SENTRY_TAGS, "event_type": event.event_type})
            log.error("處理 %s 事件時發生錯誤", event.event_type, exc_info=exc)
        return True

    async def _shutdown(self, timeout: float) -> None:
        current = asyncio.current_task()
        self._stopping = True
        # 先讓已排入的發送、正在處理的事件完成，再取消讀取與維護；handler 卡住時逾時後照樣取消
        waits: list[asyncio.Future[Any]] = [*self._publishes, asyncio.ensure_future(self._idle.wait())]
        await asyncio.wait(waits, timeout=timeout / 2)
        others = [task for task in asyncio.all_tasks() if task is not current]
        for task in others:
            task.cancel()
        await asyncio.gather(*others, return_exceptions=True)
        await self._conn.close()


def _entries(response: Any) -> list[_Entry]:
    """XREADGROUP 的回應 → [(entry_id, fields)]；內容已被修剪的 entry fields 為 None。"""
    if not response:
        return []
    return [(entry_id, fields or None) for _, entries in response for entry_id, fields in entries]


def _is_missing_group(exc: ResponseError) -> bool:
    message = str(exc)
    return message.startswith("NOGROUP") or "no longer exists" in message


_default_bus: MessageBus | None = None
_default_lock = threading.Lock()


def get_bus() -> MessageBus:
    """process 預設實例（預設前綴）；第一次呼叫時建立。"""
    global _default_bus
    with _default_lock:
        if _default_bus is None:
            _default_bus = MessageBus()
        return _default_bus
