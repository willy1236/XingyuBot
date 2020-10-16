import discord
from discord.ext import commands
import json
import random
import os


with open('setting.json',mode='r',encoding='utf8') as jfile:
    jdata = json.load(jfile)

with open('command.json',mode='r',encoding='utf8') as jfile:
    comdata = json.load(jfile)

bot = commands.Bot(command_prefix='!!')

#啟動
@bot.event
async def on_ready():
    print(">> Bot is online <<")
    await bot.change_presence(activity=discord.Game(name='!!help'))

#load
@bot.command()
async def load(ctx, extension):
    bot.load_extension(f'cmds.{extension}')
    await ctx.sand(f'Loaded {extension} done')

#unload
@bot.command()
async def unload(ctx, extension):
    bot.unload_extension(f'cmds.{extension}')
    await ctx.sand(f'Un - Loaded {extension} done')

#reload
@bot.command()
async def reload(ctx, extension):
    bot.reload_extension(f'cmds.{extension}')
    await ctx.sand(f'Re - Loaded {extension} done')

#sand
@bot.command()
async def sand(ctx, arg):
    await ctx.send(arg)


for filename in os.listdir('./cmds'):
    if filename.endswith('.py'):
        bot.load_extension(f'cmds.{filename[:-3]}')



#if __name__ == "__main__":
bot.run(jdata['TOKEN'])