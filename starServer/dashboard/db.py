"""後台的 DB 存取入口。

sqldb 是 thread-local 的 scoped_session，讀完不 commit 會一直佔住連線，而且 engine 跟 bot 共用同一個連線池
（預設 5+10）。所以後台一律走專屬的小 executor，每次跑完在 finally 釋放 session；
不寫 `def` 端點，也不用 asyncio／anyio 預設 executor 跑 DB。
"""

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from starlib import sqldb

_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="dashboard-db")


def _run[T](fn: Callable[[], T]) -> T:
    try:
        return fn()
    finally:
        sqldb.release_session()


async def run_db[T](fn: Callable[[], T]) -> T:
    """在後台專屬 executor 跑同步的 DB 函式，結束後釋放該 thread 的 session。"""
    return await asyncio.get_running_loop().run_in_executor(_executor, _run, fn)
