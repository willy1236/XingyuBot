import asyncio
import atexit
import logging
import time

import truststore

from sentry_bootstrap import init_sentry
from v2_starDiscord.bot import DiscordBot
from v2_starlib.base import get_settings
from v2_starlib.database import create_sqldb
from v2_starlib.fileDatabase import JsonDatabase
from v2_starlib.pubsub import StarEventBus

truststore.inject_into_ssl()

init_sentry(service="main")
log = logging.getLogger(__name__)


async def main():
    settings = get_settings()
    sqldb = create_sqldb()
    Jsondb = JsonDatabase()
    sclient = StarEventBus()

    sqldb.init_cache()
    log.debug("Discord Bot start running...")
    bot = DiscordBot(settings, sqldb, Jsondb, sclient)
    bot.load_all_extensions()

    # sclient.subscribe(TwitchStreamEvent, bot.on_twitch_stream_event, loop=bot.loop)

    try:
        await asyncio.gather(bot.start())
    except Exception as e:
        log.exception("An error occurred while running the bot.")


if __name__ == "__main__":
    asyncio.run(main())
