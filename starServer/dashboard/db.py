"""後台的 DB 存取入口。

sqldb 是 thread-local 的 scoped_session，讀完不 commit 會一直佔住連線，而且 engine 跟 bot 共用同一個連線池
（預設 5+10）。所以後台一律走專屬的小 executor，每次跑完在 finally 釋放 session；
不寫 `def` 端點，也不用 asyncio／anyio 預設 executor 跑 DB。
"""

import asyncio
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import TypedDict

from starlib import sqldb

MAX_WORKERS = 3

_executor = ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="dashboard-db")
_busy = 0
_busy_lock = threading.Lock()


class ExecutorStats(TypedDict):
    workers: int
    busy: int
    queued: int


class PoolStats(TypedDict):
    in_use: int
    limit: int


def _run[T](fn: Callable[[], T]) -> T:
    global _busy
    with _busy_lock:
        _busy += 1
    try:
        return fn()
    finally:
        with _busy_lock:
            _busy -= 1
        sqldb.release_session()


async def run_db[T](fn: Callable[[], T]) -> T:
    """在後台專屬 executor 跑同步的 DB 函式，結束後釋放該 thread 的 session。"""
    return await asyncio.get_running_loop().run_in_executor(_executor, _run, fn)


def executor_stats() -> ExecutorStats:
    """後台 executor 的 worker 數、執行中與排隊中的工作數。不經 executor，executor 塞住時也能回應。"""
    with _busy_lock:
        busy = _busy
    return {"workers": MAX_WORKERS, "busy": busy, "queued": _executor._work_queue.qsize()}


def pool_stats() -> PoolStats:
    """bot 與後台共用的 DB 連線池：使用中的連線數與上限（pool size + max overflow）。不經 executor。"""
    pool = sqldb.engine.pool
    return {"in_use": pool.checkedout(), "limit": pool.size() + pool._max_overflow}  # type: ignore[attr-defined]
