import discord, os
from discord.ext import commands
from threading import Thread

from BotLib.file_database import JsonDatabase
from BotLib.ui_element.button import *

db = JsonDatabase()
jdata = db.jdata

#Bot1:dc小幫手, Bep:Bep, Bot2:RO
bot_code = 'Bep'
token = db.tokens.get(bot_code)

start_website = jdata.get('start_website')
auto_update = jdata.get('auto_update')
#commands.Bot
#shard_count=1,
#command_prefix=commands.when_mentioned_or('b!'),
#command_prefix='b!',
#case_insensitive=True,
#只有discord.Bot才有debug_guild

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
        debug_guilds = [566533708371329024]
    )
elif bot_code == 'Bot2':
    bot = discord.Bot(
        owner_id=419131103836635136,
        debug_guild = [566533708371329024]
    )
else:
    raise ValueError("Invalid bot_code")

#啟動
@bot.event
async def on_ready():
    #print(">> Bot is online <<")
    print(">> Bot online as",bot.user.name,"<<")
    print(">> Discord's version:",discord.__version__,"<<")
    await bot.change_presence(activity=discord.Game(name=jdata.get("activity","/help")),status=discord.Status.online)
    # cogs = ""
    # for i in bot.cogs:
    #     cogs += f"{i} "
    # print(">> Cogs:",cogs,"<<")
    if len(os.listdir('./cmds'))-len(ignore_py)-1 == len(bot.cogs):
        print(">> Cogs all loaded <<")
    else:
        print(f">> Cogs not all loaded, {len(bot.cogs)}/{len(os.listdir('./cmds'))-len(ignore_py)-1} loaded<<")
    bot.add_view(ReactRole_button())
    

#load
@bot.command()
@commands.is_owner()
async def load(ctx, extension):
    bot.load_extension(f'cmds.{extension}')
    await ctx.send(f'Loaded {extension} done')

#unload
@bot.command()
@commands.is_owner()
async def unload(ctx, extension):
    bot.unload_extension(f'cmds.{extension}')
    await ctx.send(f'Un - Loaded {extension} done')

#reload
@bot.command()
@commands.is_owner()
async def reload(ctx, extension):
    bot.reload_extension(f'cmds.{extension}')
    await ctx.send(f'Re - Loaded {extension} done')

#ping
@bot.command()
async def ping(ctx):
    await ctx.send(f'延遲為:{round(bot.latency*1000)} ms')

if __name__ == "__main__":
    if bot_code == 'Bot1' and auto_update:
        os.system('python update.py')
            
    if start_website:
        try:
            import bot_website
            server = Thread(target=bot_website.run)
            server.start()
            print('>> website: online <<')
        except:
            print('>> website: offline <<')
    else:
        print('>> website: off <<')

    try:
        ignore_py = []
        for filename in os.listdir('./cmds'):
            if filename.endswith('.py') and filename[:-3] not in ignore_py:
                bot.load_extension(f'cmds.{filename[:-3]}')
        
        bot.run(token)
    except discord.errors.LoginFailure:
        print('>> Bot: Login failed <<')