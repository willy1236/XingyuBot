import asyncio
import atexit
import logging
import time

import truststore
from fastapi import FastAPI

from sentry_bootstrap import init_sentry
from v2_starDiscord.bot import DiscordBot
from v2_starlib.base import get_settings
from v2_starlib.database import create_sqldb
from v2_starlib.fileDatabase import JsonDatabase
from v2_starlib.pubsub import StarEventBus
from v2_starWeb import setup_star_server

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

    web_app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    setup_star_server(web_app, bot, sqldb)
    import uvicorn

    config = uvicorn.Config(web_app, host="0.0.0.0", port=14000)
    web_server = uvicorn.Server(config)

    try:
        await asyncio.gather(bot.start(), web_server.serve())
    except Exception as e:
        log.exception("An error occurred while running the bot.")


if __name__ == "__main__":
    asyncio.run(main())
