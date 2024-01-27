import discord, os,time,asyncio
from discord.ext import commands
from threading import Thread

from starcord import Jsondb,log,sclient
from starcord.ui_element.button import *
from starcord.ui_element.view import *

#Bot1:dc小幫手, Bep:Bep, Bot2:RO
jdata = Jsondb.jdata
bot_code = jdata.get('bot_code')
token = Jsondb.get_token(bot_code)
api_website = jdata.get('api_website')
auto_update = jdata.get('auto_update')
debug_guild = jdata.get('debug_guild')
debug_mode = jdata.get('debug_mode',True)
#commands.Bot
#shard_count=1,
#command_prefix=commands.when_mentioned_or('b!'),
#command_prefix='b!',
#case_insensitive=True,

if bot_code == 'Bot1':
    bot = discord.Bot(
        owner_id=419131103836635136,
        intents=discord.Intents.all(),
        help_command=None
    )
elif bot_code == 'Bep':
    bot = discord.Bot(
        owner_id=419131103836635136,
        intents=discord.Intents.all(),
        help_command=None,
        debug_guilds = debug_guild
    )
elif bot_code == 'Bot2':
    bot = discord.Bot(
        owner_id=419131103836635136,
        debug_guilds = debug_guild
    )
else:
    raise ValueError("Invalid bot_code")

#啟動
@bot.event
async def on_ready():
    log.info(f">> Bot online as {bot.user.name} <<")
    log.info(f">> Discord's version: {discord.__version__} <<")
    if debug_mode:
        await bot.change_presence(activity=discord.Game(name="開發模式啟用中"),status=discord.Status.dnd)
        log.info(f">> Development mode: On <<")
    else:
        await bot.change_presence(activity=discord.Game(name=jdata.get("activity","/help")),status=discord.Status.online)

    if len(os.listdir('./cmds'))-1 == len(bot.cogs):
        log.info(">> Cogs all loaded <<")
    else:
        log.warning(f">> Cogs not all loaded, {len(bot.cogs)}/{len(os.listdir('./cmds'))} loaded<<")
    
    if bot_code == 'Bot1' and not debug_mode:
        #將超過14天的投票自動關閉
        dbdata = sclient.get_all_active_polls()
        now = datetime.datetime.now()
        for poll in dbdata:
            if now - poll['created_at'] > datetime.timedelta(days=14):
                #sqldb.remove_poll(poll['poll_id'])
                sclient.update_poll(poll['poll_id'],"is_on",0)
            else:
                bot.add_view(PollView(poll['poll_id'],sqldb=sclient))

        invites = await bot.get_guild(613747262291443742).invites()
        now = datetime.datetime.now(datetime.timezone.utc)
        days_1 = datetime.timedelta(days=1)
        invite:discord.Invite
        for invite in invites:
            if not invite.expires_at and not invite.scheduled_event and invite.uses == 0 and now - invite.created_at > days_1 and invite.url != "https://discord.gg/ye5yrZhYGF":
                await invite.delete()
                await asyncio.sleep(1)
    

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

class SatrPlatform():
    pass

if __name__ == "__main__":
    # if not debug_mode and auto_update:
    #     os.system('python ./app/update.py')
            
    if api_website:
        from .app.bot_website import ltThread,WebsiteThread
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
    
    try:
        bot.run(token)
    except discord.errors.LoginFailure:
        log.error('>> Bot: Login failed <<')
    except Exception as e:
        log.error(e)