import asyncio
import inspect
import logging
import warnings

asyncio.iscoroutinefunction = inspect.iscoroutinefunction  # 修正 asyncio.iscoroutinefunction 在 Python 3.11 之後的行為，避免第三方套件出現警告

# 壓制所有第三方套件（虛擬環境 .venv 中）的棄用警告
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=UserWarning, module=".*")
logging.captureWarnings(False)
logging.getLogger("py.warnings").setLevel(logging.ERROR)

# ruff: disable[E402]
import atexit
import sys
import time

import discord
import structlog
import truststore

from sentry_bootstrap import init_sentry

truststore.inject_into_ssl()

init_sentry(service="main")

from starlib.settings import get_settings

settings = get_settings()
bot_code = settings.BOT_CODE
api_website = settings.API_WEBSITE
twitch_bot = settings.TWITCH_BOT
log_level = settings.LOG_LEVEL


def setup_logging():
    shared_processors = [
        structlog.contextvars.merge_contextvars,  # 合併上下文變數
        structlog.processors.add_log_level,  # 加入日誌等級 (info, warn 等)
        structlog.stdlib.add_logger_name,  # 加入 logger 名稱
        structlog.stdlib.ExtraAdder(),  # 加入額外的上下文資訊（如函式名稱、行號等）
        structlog.processors.TimeStamper(fmt="%Y-%m-%dT%H:%M:%S.%f%z", utc=False),  # 加入 ISO 時間戳記
        structlog.processors.format_exc_info,  # 格式化異常資訊
    ]
    # formatter = logging.Formatter(fmt="%(asctime)s [%(levelname)s][%(name)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processor=structlog.dev.ConsoleRenderer(colors=True),
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    logging.basicConfig(handlers=[handler], level=logging.ERROR)


setup_logging()
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)
logging.getLogger("starDiscord").setLevel(log_level)
logging.getLogger("starlib").setLevel(log_level)
logging.getLogger("starServer.twitch_chatbot").setLevel(log_level)
logging.getLogger("starServer.bot_website").setLevel(log_level)
logging.getLogger("py.warnings").setLevel(logging.ERROR)

from starDiscord import DiscordBot
from starlib import sclient
from starlib.pubsub.model import TwitchStreamEvent

# ruff: enable[E402]


def run_discord_bot():
    sclient.sqldb.init_cache()
    log.debug("Discord Bot start running...")
    bot = DiscordBot(bot_code)
    sclient.bot = bot
    bot.load_all_extensions()

    sclient.subscribe(TwitchStreamEvent, bot.on_twitch_stream_event, loop=bot.loop)

    try:
        bot.run()
    except discord.errors.LoginFailure:
        log.error(">> Bot: Login failed <<")
    except Exception as e:
        log.exception(">> Bot: Unexpected error <<", exc_info=e)

def run_twitch_bot():
    from starServer.tunnel_threads import NgrokTwitchThread

    log.debug("Twitch tunnel start running...")
    twitchtunnel_thread = NgrokTwitchThread()
    sclient.twitchtunnel_thread = twitchtunnel_thread
    twitchtunnel_thread.start()
    time.sleep(5)

    from starServer.twitch_chatbot import TwitchBotThread

    log.debug("Twitch Bot start running...")
    twitchbot_thread = TwitchBotThread()
    sclient.twitch_bot_thread = twitchbot_thread
    twitchbot_thread.start()
    log.info(">> twitchBot: online <<")
    time.sleep(1)

def run_website():
    from starServer.bot_website import WebsiteThread

    log.debug("website start running...")
    try:
        server = WebsiteThread()
        sclient.website_thread = server
        server.start()
        log.info(">> website: online <<")
    except Exception:
        log.exception(">> website: offline <<")
    time.sleep(1)


def cleanup_on_exit() -> None:
    """在程式結束時釋放全域資源。"""
    db = getattr(sclient, "sqldb", None)
    if db is None:
        return

    try:
        db.shutdown()
    except Exception:
        log.exception(">> shutdown cleanup failed <<")


def main():
    if api_website:
        run_website()

    if twitch_bot:
        run_twitch_bot()

    run_discord_bot()


if __name__ == "__main__":
    atexit.register(cleanup_on_exit)
    main()
