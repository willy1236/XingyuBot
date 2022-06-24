import discord, os
from discord.ext import commands
from BotLib.database import Database

bot_list={"1":"Bot1", "2":"Bep", "3":"Bot2"}
#1:dc小幫手 2:Bep 3:RO
bot_code = 2
botuser = bot_list[str(bot_code)]

jdata = Database().jdata
picdata = Database().picdata
token = Database().tokens[botuser]


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
        help_command=None,
        debug_guild = [566533708371329024]
    )
elif bot_code == 3:
    bot = discord.Bot(
        owner_id=419131103836635136,
        debug_guild = []
    )
else:
    raise ValueError("Invalid bot_code")

#啟動
@bot.event
async def on_ready():
    print(">> Bot is online <<")
    print(">> Bot online as",bot.user.name,"<<")
    print(">> Discord's version:",discord.__version__,"<<")
    await bot.change_presence(activity=discord.Game(name='!!help'),status=discord.Status.online)
    

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

ignore_py = []
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