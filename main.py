import discord
from discord.ext import commands
import json, random, datetime, asyncio, os

from library import is_number
#import keep_alive


intents = discord.Intents.all()
#intents.typing = False
#intents.presences = False
#intents.members = True
#intents.guilds = True
#intents.messages = True
#intents.voice_states = True

jdata = json.load(open('setting.json',mode='r',encoding='utf8'))

bot = commands.Bot(command_prefix=commands.when_mentioned_or('!!'),owner_id=419131103836635136,intents=intents,case_insensitive=True)

#啟動
@bot.event
async def on_ready():
    print(">> Bot is online <<")
    print(">> Bot online as",bot.user.name,"<<")
    print(">> Discord's version:",discord.__version__,"<<")
    await bot.change_presence(activity=discord.Game(name='!!help'))

bot.remove_command('help')



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
async def send(ctx,id:int,*,msg):
    await ctx.message.delete()
    channel = bot.get_channel(id)
    if id == 0:
        await ctx.send(msg)
    elif channel == None:
        user = bot.get_user(id)
        await user.send(msg)
        await ctx.send(f'訊息發送成功',delete_after=5)
    else:
        await channel.send(msg)
        await ctx.send(f'訊息發送成功',delete_after=5)

#all_anno
@bot.command()
@commands.is_owner()
async def all_anno(ctx,*,msg):
    await ctx.message.delete()
    all_anno = jdata['all_anno']
    send_success = 0

    embed=discord.Embed(description=f'{msg}',color=0x4aa0b5)
    embed.set_footer(text='廣播電台 | 機器人全群公告')
    
    for anno_channel in all_anno:
        channel = bot.get_channel(anno_channel)
        if channel != None:
            await channel.send(embed=embed)
            send_success = send_success+1
    await ctx.send(f'已向{send_success}個頻道發送公告',delete_after=5)

#edit
@bot.command()
@commands.is_owner()
async def edit(ctx,msgID:int,*,new_msg):
    message = await ctx.fetch_message(msgID)
    channel = message.channel
    #message = channel.get_partial_message(msgID)
    await message.edit(content=new_msg)
    await ctx.send(f'訊息編輯完成,{channel.mention}',delete_after=10)

#reaction
@bot.command()
@commands.is_owner()
async def reaction(ctx,msgID:int,mod:str,*,emojiID):
    message = await ctx.fetch_message(msgID)
    channel = message.channel
    #message = channel.get_partial_message(msgID)
    #print(is_number(emojiID),is_number(emojiID) == True)
    if is_number(emojiID) == True:
        emoji = bot.get_emoji(int(emojiID))
    else:
        emoji = emojiID

    if emoji == None:
        await ctx.send(f'反應添加失敗:找不到表情符號',delete_after=5)
        return
    elif mod == 'add':
        await message.add_reaction(emoji)
        await ctx.send(f'反應添加完成,{channel.mention}',delete_after=10)
    elif mod == 'remove':
        await message.remove_reaction(emoji,member=bot.user)
        await ctx.send(f'反應移除完成,{channel.mention}',delete_after=10)
    else:
        ctx.send('參數錯誤:請輸入正確模式(add/remove)',delete_after=5)

#reset
@bot.command()
@commands.is_owner()
async def reset(ctx,arg=None):
    if arg == 'sign':
        task_report_channel = bot.get_channel(jdata['task_report'])
        with open('sign_day.json',mode='w',encoding='utf8') as jfile:
            reset = {"sign":[]}
            json.dump(reset,jfile,indent=4)

        await task_report_channel.send('簽到已重置')
    elif not arg:
        for filename in os.listdir('./cmds'):
            if filename.endswith('.py'):
                bot.reload_extension(f'cmds.{filename[:-3]}')
        await ctx.send('Re - Loaded all done',delete_after=5)

#ping
@bot.command()
async def ping(ctx):
    await ctx.send(f'延遲為:{round(bot.latency*1000)} ms')

@bot.command()
async def user(ctx,id):
    user = await bot.fetch_user(id)
    await ctx.send(user)


# @bot.event
# async def on_message(message):
#     if message.content.startswith('$thumb'):
#         channel = message.channel
#         await channel.send('Send me that 👍 reaction, mate')

#         def check(reaction, user):
#             return user == message.author and str(reaction.emoji) == '👍'

#         try:
#             reaction, user = await bot.wait_for('reaction_add', timeout=60.0, check=check)
#         except asyncio.TimeoutError:
#             await channel.send('👎')
#         else:
#             await channel.send('👍')


for filename in os.listdir('./cmds'):
    if filename.endswith('.py'):
        bot.load_extension(f'cmds.{filename[:-3]}')


#keep_alive.keep_alive()
if __name__ == "__main__":
    bot.run(jdata['Bep_TOKEN'])