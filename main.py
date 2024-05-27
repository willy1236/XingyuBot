import asyncio
import os
import time
from datetime import datetime, timedelta, timezone
from threading import Thread

import discord
from discord.ext import commands

from starcord import Jsondb,log,sclient,DiscordBot
from starcord.ui_element.view import PollView, WelcomeView, ReactionRole1

jdata = Jsondb.jdata
bot_code = jdata.get('bot_code')
api_website = jdata.get('api_website')
auto_update = jdata.get('auto_update')
debug_mode = jdata.get('debug_mode',True)
twitch_bot = jdata.get('twitch_bot',False)

bot = DiscordBot(bot_code)
sclient.bot = bot
#啟動
@bot.event
async def on_ready():
    log.info(f">> Bot online as {bot.user.name} <<")
    log.info(f">> Discord's version: {discord.__version__} <<")
    if bot.debug_mode:
        await bot.change_presence(activity=discord.Game(name="開發模式啟用中"),status=discord.Status.dnd)
        log.info(f">> Development mode: On <<")
    else:
        await bot.change_presence(activity=discord.Game(name=jdata.get("activity","/help")),status=discord.Status.online)

    if len(os.listdir('./cmds'))-1 == len(bot.cogs):
        log.info(">> Cogs all loaded <<")
    else:
        log.warning(f">> Cogs not all loaded, {len(bot.cogs)}/{len(os.listdir('./cmds'))} loaded<<")
    
    if bot.bot_code == 'Bot1' and not bot.debug_mode:
        #將超過28天的投票自動關閉
        dbdata = sclient.sqldb.get_all_active_polls()
        now = datetime.now()
        for poll in dbdata:
            if now - poll['created_at'] > timedelta(days=28):
                sclient.sqldb.update_poll(poll['poll_id'],"is_on",0)
            else:   
                bot.add_view(PollView(poll['poll_id'],sqldb=sclient.sqldb,bot=bot))

        invites = await bot.get_guild(613747262291443742).invites()
        now = datetime.now(timezone.utc)
        days_5 = timedelta(days=5)
        for invite in invites:
            if not invite.expires_at and not invite.scheduled_event and invite.uses == 0 and now - invite.created_at > days_5 and invite.url != "https://discord.gg/ye5yrZhYGF":
                await invite.delete()
                await asyncio.sleep(1)

        bot.add_view(WelcomeView())
        bot.add_view(ReactionRole1())
    

#load
@bot.command()
@commands.is_owner()
async def load(ctx, extension):
    bot.load_extension(f'cmds.{extension}')
    await ctx.respond(f'Loaded {extension} done')

#unload
@bot.command()
@commands.is_owner()
async def unload(ctx, extension):
    bot.unload_extension(f'cmds.{extension}')
    await ctx.respond(f'Un - Loaded {extension} done')

#reload
@bot.command()
@commands.is_owner()
async def reload(ctx, extension):
    bot.reload_extension(f'cmds.{extension}')
    await ctx.respond(f'Re - Loaded {extension} done')

#ping
@bot.command()
async def ping(ctx):
    await ctx.respond(f'延遲為:{round(bot.latency*1000)} ms')

for filename in os.listdir('./cmds'):
    if filename.endswith('.py'):
        bot.load_extension(f'cmds.{filename[:-3]}')

if __name__ == "__main__":
    if api_website:
        from app.bot_website import ltThread,WebsiteThread
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
        from app.twitch_chatbot import TwitchBotThread, SakagawaEventsubThread
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