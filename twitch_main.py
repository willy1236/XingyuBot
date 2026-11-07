"""Twitch bot 的獨立入口：python -m twitch_main。與 Discord bot（main）各自一個 process，經 Redis 通訊。

結束碼：收到 SIGTERM／SIGINT 乾淨收尾後為 0；放棄重連、啟動失敗、未捕捉例外為 1（交給 systemd 重啟）。
"""

# ruff: disable[E402]
import asyncio
import logging
import os
import signal
import sys
import threading

from bootstrap import setup_runtime

setup_runtime("twitch")

from sentry_bootstrap import capture_exception_safe, flush_safe
from starlib import sclient
from starlib.messaging import get_bus

# ruff: enable[E402]

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

# 收到停止信號後，等 Twitch bot 自己收尾的上限
SHUTDOWN_GRACE = 15
# 異常結束時，清理（eventsub、api、chat、bus）的時間上限
ABNORMAL_CLEANUP_TIMEOUT = 10

_shutdown = threading.Event()
_thread = None


def _hard_exit(code: int) -> None:
    os._exit(code)


def _on_signal(signum, frame) -> None:
    _shutdown.set()
    if _thread is not None:
        _thread.stop()


def _install_signal_handlers() -> None:
    # Windows 只支援 SIGINT；其他信號註冊失敗就略過
    for name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, _on_signal)
        except (ValueError, OSError):
            pass


def _run() -> bool:
    """啟動並等到 Twitch bot 結束，回傳是否異常結束。"""
    global _thread
    from starServer.twitch_chatbot import TwitchBotThread

    # Twitch 自訂指令的快取（DBCacheType.TwitchCmd）在這裡載入
    sclient.sqldb.init_cache()
    if _shutdown.is_set():
        return False

    log.debug("Twitch Bot start running...")
    thread = _thread = TwitchBotThread()
    thread.start()

    # 每秒醒來一次，Windows 上的 Ctrl+C 才處理得到
    while not thread.ready.wait(1):
        if not thread.is_alive():
            return True  # 啟動失敗：ready 永遠不會 set
        if _shutdown.is_set():
            break
    if _shutdown.is_set():
        thread.stop()  # 信號可能搶在 _thread 賦值之前到達
    if thread.ready.is_set():
        # 初始化完成才開始消費，避免事件進來時 handler 還沒就緒
        get_bus().start("twitch")
        log.info(">> twitchBot: online <<")

    while thread.is_alive() and not _shutdown.is_set():
        thread.join(1)
    if thread.is_alive():
        # 收到停止信號：給 Twitch bot 時間自己收尾，逾時視為異常
        thread.join(SHUTDOWN_GRACE)
    return thread.is_alive() or thread.abnormal


def _abnormal_exit(thread) -> None:
    """限時清理後以非 0 結束；清理卡住時也在時限內結束。"""

    def cleanup() -> None:
        try:
            if thread is not None:
                asyncio.run(thread.cleanup())
            get_bus().close()
        except Exception as exc:
            log.warning("異常結束的清理失敗: %s", exc)

    cleaner = threading.Thread(target=cleanup, name="TwitchAbnormalCleanup", daemon=True)
    cleaner.start()
    cleaner.join(ABNORMAL_CLEANUP_TIMEOUT)
    flush_safe(2)
    _hard_exit(1)


def main() -> None:
    _install_signal_handlers()
    try:
        abnormal = _run()
    except Exception as exc:
        capture_exception_safe(exc, tags={"service": "twitch", "source": "main"})
        log.error("Twitch bot 啟動流程失敗", exc_info=exc)
        abnormal = True

    if abnormal:
        _abnormal_exit(_thread)
        return
    get_bus().close()
    sys.exit(0)


if __name__ == "__main__":
    main()
