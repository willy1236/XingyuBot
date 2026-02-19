import asyncio
import time

import discord
import truststore

truststore.inject_into_ssl()

# ruff: disable[E402]
from starDiscord import DiscordBot
from starlib import Jsondb, log, sclient
from starlib.core.model import TwitchStreamEvent
from starServer.scheduler import run_scheduler_in_thread

# ruff: enable[E402]

config = Jsondb.config
bot_code = config.get("bot_code")
api_website = config.get("api_website")
twitch_bot = config.get("twitch_bot", False)


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
        log.error(e)

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
        log.info(">> website: offline <<")
    time.sleep(1)

def main():
    if api_website:
        run_website()

    if twitch_bot:
        run_twitch_bot()

    run_scheduler_in_thread()

    run_discord_bot()


if __name__ == "__main__":
    main()
