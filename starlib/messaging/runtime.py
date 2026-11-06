"""每個 bus 實例專屬的 daemon thread 與 event loop。"""

import asyncio
import concurrent.futures
import logging
import threading
from collections.abc import Callable, Coroutine
from typing import Any

log = logging.getLogger(__name__)


class BusRuntime:
    """一條 daemon thread 跑一個 event loop；bus 的 Redis 操作都排到這個 loop 上執行。"""

    def __init__(self, name: str) -> None:
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, name=name, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_forever()
        finally:
            self.loop.close()

    @property
    def running(self) -> bool:
        return self._thread.is_alive() and not self.loop.is_closed()

    def in_loop(self) -> bool:
        return threading.get_ident() == self._thread.ident

    def run[T](self, coro: Coroutine[Any, Any, T]) -> concurrent.futures.Future[T]:
        """執行緒安全，把 coroutine 排到 loop 上。loop 已停止時回傳帶 RuntimeError 的 future。"""
        try:
            return asyncio.run_coroutine_threadsafe(coro, self.loop)
        except RuntimeError as exc:
            coro.close()
            future: concurrent.futures.Future[T] = concurrent.futures.Future()
            future.set_exception(exc)
            return future

    def call_soon(self, callback: Callable[[], Any]) -> bool:
        """執行緒安全，不等待；loop 已停止時回傳 False。"""
        try:
            self.loop.call_soon_threadsafe(callback)
        except RuntimeError:
            return False
        return True

    def stop(self, timeout: float) -> None:
        self.call_soon(self.loop.stop)
        if not self.in_loop():
            self._thread.join(timeout)
            if self._thread.is_alive():
                log.warning("messaging 的 bus thread %s 在 %.1f 秒內沒有結束", self._thread.name, timeout)
