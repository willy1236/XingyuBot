import asyncio
import os
import time
from datetime import datetime, timedelta, timezone
from threading import Thread

import discord

from starlib import Jsondb, log, sclient
from starDiscord import DiscordBot

config = Jsondb.config
bot_code = config.get('bot_code')
api_website = config.get('api_website')
auto_update = config.get('auto_update')
debug_mode = config.get('debug_mode',True)
twitch_bot = config.get('twitch_bot',False)

bot = DiscordBot(bot_code)
sclient.bot = bot
bot.load_all_extensions()

if __name__ == "__main__":
    if api_website:
        from app.bot_website import WebsiteThread, ltThread
        ltserver = ltThread()
        ltserver.start()
        time.sleep(2)

        try:
            server = WebsiteThread()
            server.start()
            log.info('>> website: online <<')
        except:
            log.info('>> website: offline <<')
        time.sleep(2)

    if twitch_bot:
        from app.twitch_chatbot import SakagawaEventsubThread, TwitchBotThread
        twitchbot_thread = TwitchBotThread()
        twitchbot_thread.start()
        time.sleep(5)

        sakagawa_thread = SakagawaEventsubThread()
        sakagawa_thread.start()
        time.sleep(2)
    
    try:
        bot.run()
    except discord.errors.LoginFailure:
        log.error('>> Bot: Login failed <<')
    except Exception as e:
        log.error(e)