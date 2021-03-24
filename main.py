import discord
from discord.ext import commands
import json
import random
import os
import datetime

intents = discord.Intents.default()
intents.typing = False
intents.presences = False
intents.members = True
intents.guilds = True
intents.messages = True
intents.voice_states = True

with open('setting.json',mode='r',encoding='utf8') as jfile:
    jdata = json.load(jfile)

with open('command.json',mode='r',encoding='utf8') as jfile:
    comdata = json.load(jfile)

bot = commands.Bot(command_prefix='!!',owner_id=419131103836635136,intents=intents)

#啟動
@bot.event
async def on_ready():
    print(">> Bot is online <<")
    await bot.change_presence(activity=discord.Game(name='!!help 指令測試中'))

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

#send
@bot.command()
@commands.is_owner()
async def send(ctx,*,msg):
    await ctx.message.delete()
    await ctx.send(msg)

#dmsend
@bot.command()
@commands.is_owner()
async def dmsend(ctx,channel:int,*,msg):
    channel = bot.get_channel(channel)
    await ctx.send(f'公會為 {channel.guild}')
    if channel.guild != '':
        await ctx.send('有工會')
    await ctx.message.delete()
    user = bot.get_user(channel)
    await user.send(msg)
    


#csend
@bot.command()
@commands.is_owner()
async def csend(ctx,channel:int,*,msg):
    await ctx.message.delete()
    channel = bot.get_channel(channel)
    if channel.guild != '':
        await channel.send(msg)
    else:
        user = bot.get_user(channel)
        await user.send(msg)

#all_anno
@bot.command()
@commands.is_owner()
async def all_anno(ctx,*,msg):
    await ctx.message.delete()
    all_anno = jdata['all_anno']

    embed=discord.Embed(description=f'{msg}',color=0x4aa0b5)
    embed.set_footer(text='機器人全群公告')
    
    for b in all_anno:
        channel = bot.get_channel(b)
        await channel.send(embed=embed)

#edit
#@bot.command()
#@commands.is_owner()
#async def edit(ctx,msgID,*,msg):
#    channel = bot.get_channel(686237849301156017)
#    message = discord.utils.get(channel.history.message,id=int(msgID))
#    await message.edit(content=msg)


for filename in os.listdir('./cmds'):
    if filename.endswith('.py'):
        bot.load_extension(f'cmds.{filename[:-3]}')



#if __name__ == "__main__":
bot.run(jdata['TOKEN'])