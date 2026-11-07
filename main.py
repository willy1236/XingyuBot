# ruff: disable[E402]
import atexit
import logging
import time

from bootstrap import setup_runtime

setup_runtime("main")

import discord

from starlib.settings import get_settings

settings = get_settings()
bot_code = settings.BOT_CODE
api_website = settings.API_WEBSITE

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

from starDiscord import DiscordBot
from starlib import sclient
from starlib.messaging import get_bus

# ruff: enable[E402]


def run_discord_bot():
    sclient.sqldb.init_cache()
    log.debug("Discord Bot start running...")
    bot = DiscordBot(bot_code)
    sclient.bot = bot
    bot.load_all_extensions()

    try:
        bot.run()
    except discord.errors.LoginFailure:
        log.error(">> Bot: Login failed <<")
    except Exception as e:
        log.exception(">> Bot: Unexpected error <<", exc_info=e)
    finally:
        # bot.run() 收到 SIGINT/SIGTERM 只會關閉 Discord，背景 thread 要另外停止，否則程式會卡在 join
        log.info(">> stopping background threads <<")
        sclient.stop_threads()
        get_bus().close()

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

    run_discord_bot()


if __name__ == "__main__":
    atexit.register(cleanup_on_exit)
    main()
