import discord, os
from discord.ext import commands
from BotLib.database import Database
from cmds.command import Reactbutton1

bot_list={"1":"Bot1", "2":"Bep", "3":"Bot2"}
#1:dc小幫手 2:Bep 3:RO
bot_code = 2

db = Database()
jdata = db.jdata
picdata = db.picdata
token = db.tokens[bot_list[str(bot_code)]]


if bot_code ==1:
    bot = commands.Bot(
        command_prefix=commands.when_mentioned_or('!!'),
        owner_id=419131103836635136,
        intents=discord.Intents.all(),
        case_insensitive=True, 
        help_command=None
    )
elif bot_code == 2:
    bot = commands.AutoShardedBot(
        shard_count=1,
        command_prefix=commands.when_mentioned_or('b!'),
        owner_id=419131103836635136,
        intents=discord.Intents.all(),
        case_insensitive=True, 
        help_command=None
    )
    #只有discord.Bot才有debug_guild
elif bot_code == 3:
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
    await bot.change_presence(activity=discord.Game(name=jdata.get("activity","!!help")),status=discord.Status.online)
    # cogs = ""
    # for i in bot.cogs:
    #     cogs += f"{i} "
    # print(">> Cogs:",cogs,"<<")
    if len(os.listdir('./cmds'))-len(ignore_py)-1 == len(bot.cogs):
        print(">> Cogs all loaded <<")
    else:
        print(f">> Cogs not all loaded, {len(bot.cogs)}/{len(os.listdir('./cmds'))-len(ignore_py)-1} loaded<<")
    bot.add_view(Reactbutton1())
    

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

#reset
@bot.command()
@commands.is_owner()
async def reset(ctx,arg=None):
    if arg == 'sign':
        task_report_channel = bot.get_channel(jdata['task_report'])
        reset = []
        Database().write('jdsign',reset)

        await task_report_channel.send('簽到已重置')
        await ctx.message.add_reaction('✅')
    elif not arg:
        await ctx.message.delete()
        for filename in os.listdir('./cmds'):
            if filename.endswith('.py'):
                bot.reload_extension(f'cmds.{filename[:-3]}')
        await ctx.send('Re - Loaded all done',delete_after=5)

#ping
@bot.command()
async def ping(ctx):
    await ctx.send(f'延遲為:{round(bot.latency*1000)} ms')

@bot.command()
@commands.is_owner()
async def jset(ctx,option,value):
    db = Database()
    jdata = db.jdata
    jdata[option] = value
    db.write('jdata',jdata)
    await ctx.send(f'已將{option} 設為 {value}')

ignore_py = []
if bot_code == 3:
    for filename in os.listdir('./slash_cmds'):
        if filename.endswith('.py') and filename[:-3] not in ignore_py:
            bot.load_extension(f'cmds.{filename[:-3]}')
else:
    for filename in os.listdir('./cmds'):
        if filename.endswith('.py') and filename[:-3] not in ignore_py:
            bot.load_extension(f'cmds.{filename[:-3]}')

if __name__ == "__main__":
    try:
        import keep_alive
        keep_alive.keep_alive()
    except:
        print('>> keep_alive not activated <<')

    try:
        bot.run(token)
    except discord.errors.LoginFailure:
        print('發生錯誤:機器人登入失敗')