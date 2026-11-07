"""服務之間的請求／回應：請求走 Redis Stream（同服務多實例只有一個處理），回應走每個請求專屬的 List。

線路格式見 docs/messaging-contract.md〈請求／回應〉。只用 MessageBus 的擴充點，不改 bus。
"""

import asyncio
import concurrent.futures
import json
import logging
import threading
import time
from collections.abc import Awaitable, Callable, Coroutine
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import redis.asyncio as aioredis
from redis.exceptions import ResponseError

from sentry_bootstrap import capture_exception_safe

from .bus import DATA_FIELD, MessageBus, get_bus
from .connection import CONNECTION_ERRORS, SENTRY_TAGS, BusUnavailable

log = logging.getLogger(__name__)

type RpcHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]

# 請求從發出到必須拿到回應的時間；處理端收到超過這個時間的請求就丟棄
REQUEST_TIMEOUT = 5.0
# 回應 key 的存活時間，發送端已放棄等待時回應不會留著
REPLY_TTL = 30
MAINTENANCE_INTERVAL = 30.0
READ_BLOCK_MS = 1_000
# 連不上或出錯後重試的間隔
RETRY_DELAY = 1.0
DRAIN_BATCH = 100


class RpcUnavailable(Exception):
    """對方無法處理：沒在跑、逾時、Redis 連不上。"""


class RpcHandlerError(Exception):
    """處理端拋出例外或沒有這個方法，message 帶錯誤摘要。"""


# ── 處理端 ───────────────────────────────────────────────


class _Server:
    """一個 bus 實例的請求處理端：已註冊的 method，以及 start 之後的消費與維護。"""

    def __init__(self, bus: MessageBus) -> None:
        self._bus = bus
        self._handlers: dict[str, tuple[RpcHandler, asyncio.AbstractEventLoop]] = {}
        self._service = ""
        self._consumer = ""
        self._tasks: set[asyncio.Task[None]] = set()
        self._lock = threading.Lock()

    def register(self, method: str, handler: RpcHandler, loop: asyncio.AbstractEventLoop) -> None:
        with self._lock:
            self._handlers[method] = (handler, loop)

    def _stream(self) -> str:
        return f"{self._bus.key_prefix}:rpc:{self._service}"

    # ── 以下只在 bus loop 上執行 ──────────────────────────

    async def on_start(self, service: str, consumer: str) -> None:
        self._service, self._consumer = service, consumer
        self._spawn(self._consume())
        self._spawn(self._maintain())

    def _spawn(self, coro: Coroutine[Any, Any, None]) -> None:
        task = asyncio.get_running_loop().create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _consume(self) -> None:
        group = self._service
        while True:
            try:
                client = await self._bus.get_client()
            except BusUnavailable:
                await asyncio.sleep(RETRY_DELAY)
                continue
            try:
                await self._ensure_group(client)
                await self._drain(client)
                while True:
                    response = await client.xreadgroup(
                        group, self._consumer, {self._stream(): ">"}, count=1, block=READ_BLOCK_MS
                    )
                    for _, entries in response or []:
                        for entry_id, fields in entries:
                            # 每筆請求各自一個 task，慢的 handler 不會讓後面的請求在佇列裡過期
                            self._spawn(self._process(client, entry_id, fields))
            except asyncio.CancelledError:
                raise
            except CONNECTION_ERRORS as exc:
                log.warning("讀取 %s 的請求失敗：%r", self._stream(), exc)
            except ResponseError as exc:
                # NOGROUP（Redis 資料遺失）時回到迴圈開頭會重建 group
                log.warning("讀取 %s 的請求失敗：%s", self._stream(), exc)
            except Exception as exc:
                capture_exception_safe(exc, tags=SENTRY_TAGS)
                log.error("讀取 %s 的請求發生未預期的錯誤", self._stream(), exc_info=exc)
            await asyncio.sleep(RETRY_DELAY)

    async def _ensure_group(self, client: aioredis.Redis) -> None:
        try:
            await client.xgroup_create(self._stream(), self._service, id="0", mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def _drain(self, client: aioredis.Redis) -> None:
        """上次當機或 ack 失敗時留在自己待確認清單的請求：不補做，一律直接 ack。"""
        while True:
            response = await client.xreadgroup(self._service, self._consumer, {self._stream(): "0"}, count=DRAIN_BATCH)
            entry_ids = [entry_id for _, batch in response or [] for entry_id, _ in batch]
            if not entry_ids:
                return
            await client.xack(self._stream(), self._service, *entry_ids)

    async def _maintain(self) -> None:
        """定期清掉過期請求；不做補送。"""
        while True:
            await asyncio.sleep(MAINTENANCE_INTERVAL)
            try:
                client = await self._bus.get_client()
                await client.xtrim(self._stream(), minid=_trim_floor(), approximate=False)
            except BusUnavailable:
                continue
            except Exception as exc:
                log.warning("修剪 %s 失敗：%r", self._stream(), exc)

    async def _process(self, client: aioredis.Redis, entry_id: str, fields: dict[str, str] | None) -> None:
        try:
            await self._handle(client, fields)
        except asyncio.CancelledError:
            raise
        except CONNECTION_ERRORS as exc:
            log.warning("處理請求 %s 時 Redis 連不上：%r", entry_id, exc)
            return  # 沒 ack，下次啟動時由 _drain 清掉
        except Exception as exc:
            capture_exception_safe(exc, tags=SENTRY_TAGS)
            log.error("處理請求 %s 時發生未預期的錯誤", entry_id, exc_info=exc)
        try:
            await client.xack(self._stream(), self._service, entry_id)
        except (*CONNECTION_ERRORS, ResponseError) as exc:
            log.warning("確認請求 %s 失敗：%r", entry_id, exc)

    async def _handle(self, client: aioredis.Redis, fields: dict[str, str] | None) -> None:
        request = self._parse(fields)
        if request is None:
            return
        method, payload, reply_to, deadline = request
        remaining = (deadline - datetime.now(UTC)).total_seconds()
        if remaining <= 0:
            log.info("請求 %s 已過期，丟棄", method)
            return
        reply = await self._run(method, payload, remaining)
        if reply is not None:
            pipe = client.pipeline(transaction=True)
            pipe.rpush(reply_to, reply)
            pipe.expire(reply_to, REPLY_TTL)
            await pipe.execute()

    def _parse(self, fields: dict[str, str] | None) -> tuple[str, dict[str, Any], str, datetime] | None:
        try:
            body = json.loads((fields or {})[DATA_FIELD])
            method, payload, reply_to = body["method"], body["payload"], body["reply_to"]
            deadline = datetime.fromisoformat(body["deadline"])
            if not (isinstance(method, str) and isinstance(payload, dict) and isinstance(reply_to, str)):
                raise ValueError("欄位型別不符")
            if deadline.tzinfo is None:
                raise ValueError("deadline 沒有時區")
            # 回應只能寫到回應專用的 key，不讓請求指定任意 key
            if not reply_to.startswith(f"{self._bus.key_prefix}:rpc:reply:"):
                raise ValueError("reply_to 不在回應 key 範圍內")
        except (KeyError, TypeError, ValueError) as exc:
            log.warning("請求格式錯誤，略過：%r", exc)
            return None
        return method, payload, reply_to, deadline

    async def _run(self, method: str, payload: dict[str, Any], remaining: float) -> str | None:
        """執行 handler，回傳要寫回的 JSON；超過期限（發送端已放棄）回傳 None。"""
        with self._lock:
            entry = self._handlers.get(method)
        if entry is None:
            return _error_reply(f"沒有這個方法：{method}")
        handler, loop = entry
        coro = handler(payload)
        try:
            future = asyncio.run_coroutine_threadsafe(coro, loop)
        except RuntimeError as exc:
            coro.close()
            return _error_reply(f"{method} 的 handler loop 已關閉：{exc}")
        try:
            result = await asyncio.wait_for(asyncio.wrap_future(future), remaining)
        except TimeoutError:
            log.warning("請求 %s 執行超過期限，放棄回應", method)
            return None
        except asyncio.CancelledError:
            current = asyncio.current_task()
            if current is not None and current.cancelling():
                raise  # bus 自己被取消（關閉中）
            # handler 在它自己的 loop 上被取消（例如那個 loop 正在關閉）：回錯誤，不讓消費者停掉
            log.warning("請求 %s 的 handler 被取消", method)
            return _error_reply(f"{method} 的 handler 被取消")
        except Exception as exc:
            capture_exception_safe(exc, tags={**SENTRY_TAGS, "rpc_method": method})
            log.error("處理請求 %s 時 handler 拋出例外", method, exc_info=exc)
            return _error_reply(f"{type(exc).__name__}: {exc}")
        try:
            if not isinstance(result, dict):
                raise TypeError(f"handler 應回傳 dict，實際是 {type(result).__name__}")
            return json.dumps({"ok": True, "result": result}, ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            return _error_reply(f"回應無法序列化：{exc}")


def _error_reply(message: str) -> str:
    return json.dumps({"ok": False, "error": message}, ensure_ascii=False)


def _trim_floor() -> int:
    return int((time.time() - REQUEST_TIMEOUT) * 1000)


_servers: dict[MessageBus, _Server] = {}
_servers_lock = threading.Lock()


def handle(
    method: str,
    handler: RpcHandler,
    loop: asyncio.AbstractEventLoop,
    *,
    bus: MessageBus | None = None,
) -> None:
    """註冊請求處理函式，在 loop 上執行並回傳可 JSON 序列化的 dict；start 前後都可註冊，同名再註冊會取代。

    bus=None 表示 get_bus()。沒有註冊任何 handle 的服務不消費請求，發給它的請求逾時得到 RpcUnavailable。
    """
    bus = bus or get_bus()
    with _servers_lock:
        server = _servers.get(bus)
        created = server is None
        if server is None:
            server = _servers[bus] = _Server(bus)
    server.register(method, handler, loop)
    if created:
        bus.on_start(server.on_start)


# ── 發送端 ───────────────────────────────────────────────


def request(
    service: str, method: str, payload: dict[str, Any], *, bus: MessageBus | None = None
) -> concurrent.futures.Future[dict[str, Any]]:
    """向 service 發請求。執行緒安全；逾時固定 REQUEST_TIMEOUT 秒，呼叫端在自己的 loop 用 asyncio.wrap_future 等待。

    future 的結果是處理端的回傳值；對方無法處理時是 RpcUnavailable，處理端出錯時是 RpcHandlerError。
    """
    bus = bus or get_bus()
    inner = bus.run(_request(bus, service, method, payload))
    outer: concurrent.futures.Future[dict[str, Any]] = concurrent.futures.Future()

    def relay(done: concurrent.futures.Future[dict[str, Any]]) -> None:
        # bus 已關閉或關閉時被取消，對呼叫端來說也是「無法處理」
        if done.cancelled():
            outer.set_exception(RpcUnavailable("bus 已關閉"))
        elif isinstance(exc := done.exception(), RuntimeError):
            outer.set_exception(RpcUnavailable(f"bus 已關閉：{exc}"))
        elif exc is not None:
            outer.set_exception(exc)
        else:
            outer.set_result(done.result())

    inner.add_done_callback(relay)
    return outer


async def _request(bus: MessageBus, service: str, method: str, payload: dict[str, Any]) -> dict[str, Any]:
    request_id = str(uuid4())
    deadline = datetime.now(UTC) + timedelta(seconds=REQUEST_TIMEOUT)
    reply_to = f"{bus.key_prefix}:rpc:reply:{request_id}"
    body = json.dumps(
        {
            "request_id": request_id,
            "method": method,
            "payload": payload,
            "reply_to": reply_to,
            "deadline": deadline.isoformat(),
        },
        ensure_ascii=False,
    )
    try:
        client = await bus.get_client()
    except BusUnavailable as exc:
        raise RpcUnavailable("Redis 連不上") from exc
    try:
        # 順手修剪沒人處理的過期請求，對方沒在跑時 stream 也不會一直長大
        await client.xadd(
            f"{bus.key_prefix}:rpc:{service}",
            {DATA_FIELD: body},
            minid=_trim_floor(),
            approximate=False,
        )
        remaining = (deadline - datetime.now(UTC)).total_seconds()
        if remaining <= 0:
            raise RpcUnavailable("逾時")
        # 不用 wait_for 包 BLPOP：取消進行中的指令會弄壞共用連線，逾時交給 Redis 自己處理
        popped = await client.blpop([reply_to], timeout=remaining)
    except (*CONNECTION_ERRORS, ResponseError) as exc:
        raise RpcUnavailable(f"Redis 操作失敗：{exc!r}") from exc
    if popped is None:
        raise RpcUnavailable(f"{service} 在 {REQUEST_TIMEOUT:g} 秒內沒有回應")
    try:
        reply = json.loads(popped[1])
        if reply["ok"] is True:
            return reply["result"]
        error = str(reply["error"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RpcHandlerError(f"回應格式錯誤：{exc!r}") from exc
    raise RpcHandlerError(error)
