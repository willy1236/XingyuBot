import discord
from discord.ext import commands
import json
import random

with open('setting.json',mode='r',encoding='utf8') as jfile:
    jdata = json.load(jfile)

bot = commands.Bot(command_prefix='!!')

#啟動
@bot.event
async def on_ready():
    print(">> Bot is online <<")

#回復相同訊息
@bot.command()
async def test(ctx, arg):
    await ctx.send(arg)


#@bot.command()
#async def test2(ctx):
#    channel = bot.get_channel(int(jdata['test_channel']))
#    await channel.sand(f'hi')

#在指定頻道發送指定訊息
@bot.command()
async def test3(ctx):
    channel = bot.get_channel(int(jdata['test2_channel']))
    await channel.send('Hello')

#在指定頻道發送相同訊息
@bot.command()
async def test4(ctx, arg):
    channel = bot.get_channel(int(jdata['test2_channel']))
    await channel.send(arg)


bot.run(jdata['TOKEN'])