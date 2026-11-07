"""Twitch bot 的獨立入口：python -m twitch_main。與 Discord bot（main）各自一個 process，經 Redis 通訊。"""

# ruff: disable[E402]
import logging

from bootstrap import setup_runtime

setup_runtime("twitch")

from starlib import sclient
from starlib.messaging import get_bus

# ruff: enable[E402]

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)


def main() -> None:
    from starServer.twitch_chatbot import TwitchBotThread

    # Twitch 自訂指令的快取（DBCacheType.TwitchCmd）在這裡載入
    sclient.sqldb.init_cache()

    log.debug("Twitch Bot start running...")
    thread = TwitchBotThread()
    thread.start()
    # 初始化完成才開始消費，避免事件進來時 handler 還沒就緒
    thread.ready.wait()
    get_bus().start("twitch")
    log.info(">> twitchBot: online <<")

    try:
        thread.join()
    finally:
        # Ctrl+C 打斷 join 時，要讓 Twitch bot 自己清理（eventsub、api、chat），再關 bus
        thread.stop()
        thread.join(10)
        get_bus().close()


if __name__ == "__main__":
    main()
