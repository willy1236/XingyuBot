import time
import asyncio

import discord

from starDiscord import DiscordBot
from starlib import Jsondb, log, sclient
from starServer.scheduler import run_scheduler_in_thread

config = Jsondb.config
bot_code = config.get('bot_code')
api_website = config.get('api_website')
debug_mode = config.get('debug_mode',True)
twitch_bot = config.get('twitch_bot',False)

def run_discord_bot():
    log.debug('Discord Bot start running...')
    bot = DiscordBot(bot_code)
    sclient.bot = bot
    bot.load_all_extensions()
    
    try:
        bot.run()
    except discord.errors.LoginFailure:
        log.error('>> Bot: Login failed <<')
    except Exception as e:
        log.error(e)

def run_twitch_bot():
    from starServer.tunnel_threads import LoopholeTwitchThread
    twitchtunnel_thread = LoopholeTwitchThread()
    sclient.twitchtunnel_thread = twitchtunnel_thread
    twitchtunnel_thread.start()
    time.sleep(10)

    from starServer.twitch_chatbot import TwitchBotThread
    log.debug('Twitch Bot start running...')
    twitchbot_thread = TwitchBotThread()
    sclient.twitch_bot_thread = twitchbot_thread
    twitchbot_thread.start()
    log.info('>> twitchBot: online <<')
    time.sleep(2)

def run_website():
    from starServer.bot_website import WebsiteThread
    log.debug('website start running...')
    try:
        server = WebsiteThread()
        sclient.website_thread = server
        server.start()
        log.info('>> website: online <<')
    except:
        log.info('>> website: offline <<')
    time.sleep(2)

def main():
    pass

if __name__ == "__main__":
    # if api_website or twitch_bot:
    #     from starServer.tunnel_threads import ServeoThread
    #     serveo_tunnel = ServeoThread()
    #     serveo_tunnel.start()
    #     log.info('>> serveo tunnel: online <<')
    #     time.sleep(2)

    if api_website:
        # from starServer.tunnel_threads import LoopholeThread
        # tunnel_server = LoopholeThread()
        # sclient.tunnel_thread = tunnel_server
        # tunnel_server.start()
        # time.sleep(2)
        run_website()        

    if twitch_bot:
        run_twitch_bot()

    run_scheduler_in_thread()
    
    run_discord_bot()