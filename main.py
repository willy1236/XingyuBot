import discord
from discord.ext import commands
import json, random, datetime, asyncio, os
from library import find,BRS

intents = discord.Intents.all()
#intents.typing = False
#intents.presences = False
#intents.members = True
#intents.guilds = True
#intents.messages = True
#intents.voice_states = True

bot_list={"1":"Bot1", "2":"Bep", "3":"Bot2"}
global bot_code
#1:dc小幫手 2:Bep
bot_code = 1
botuser = bot_list[str(bot_code)]

jdata = json.load(open('setting.json',mode='r',encoding='utf8'))
cdata = json.load(open('database/channel_settings.json',mode='r',encoding='utf8'))
picdata = json.load(open('database/picture.json',mode='r',encoding='utf8'))

try:
    tokens = json.load(open('token_settings.json',mode='r',encoding='utf8'))
    token = tokens[botuser]
except:
    token = os.environ[botuser]



if bot_code ==1:
    bot = commands.Bot(command_prefix=commands.when_mentioned_or('!!'),owner_id=419131103836635136,intents=intents,case_insensitive=True, help_command=None)
elif bot_code == 2:
    bot = commands.AutoShardedBot(shard_count=1,command_prefix=commands.when_mentioned_or('b!'),owner_id=419131103836635136,intents=intents,case_insensitive=True, help_command=None)
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
async def anno(ctx,*,msg):
    send_success = 0
    send_msg = await ctx.send('訊息發送中...')

    embed= BRS.all_anno(msg)
    
    for i in cdata['all_anno']:
        channel = bot.get_channel(cdata['all_anno'][i])
        if channel != None:
            try:
                await channel.send(embed=embed)
                send_success += 1
            except:
                pass
    await ctx.message.delete()
    await send_msg.edit(f"已向{send_success}/{len(cdata['all_anno'])}個頻道發送公告",delete_after=5)

#edit
@bot.command()
@commands.is_owner()
async def edit(ctx,msgid:int,*,new_msg):
    message = await ctx.fetch_message(msgid)
    #message = channel.get_partial_message(msgID)
    await message.edit(content=new_msg)
    await ctx.message.add_reaction('✅')

#reaction
@bot.command()
@commands.is_owner()
async def reaction(ctx,msgid:int,mod:str,*,emojiid):
    message = await ctx.fetch_message(msgid)
    channel = message.channel
    #message = channel.get_partial_message(msgID)
    emoji = find.emoji(emojiid)

    if emoji == None:
        await ctx.send(f'反應添加失敗:找不到表情符號',delete_after=5)
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
        with open('database/sign_day.json',mode='w',encoding='utf8') as jfile:
            reset = []
            json.dump(reset,jfile,indent=4)

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

# @bot.command()
# @commands.is_owner()
# async def shutdown(ctx):
#     await ctx.send('機器人關閉中...')
#     await bot.close()

@bot.command()
@commands.is_owner()
async def permission(ctx,guild_id:int):
    guild = bot.get_guild(guild_id)
    member = guild.get_member(ctx.bot.user.id)
    permission = member.guild_permissions

    embed = discord.Embed(title=guild.name, color=0xc4e9ff)
    embed.add_field(name="管理員", value=permission.administrator, inline=True)
    embed.add_field(name="管理頻道", value=permission.manage_channels, inline=True)
    embed.add_field(name="管理公會", value=permission.manage_guild, inline=True)
    embed.add_field(name="管理訊息", value=permission.manage_messages, inline=True)
    embed.add_field(name="管理暱稱", value=permission.manage_nicknames, inline=True)
    embed.add_field(name="管理身分組", value=permission.manage_roles, inline=True)
    embed.add_field(name="管理webhook", value=permission.manage_webhooks, inline=True)
    embed.add_field(name="管理表情符號", value=permission.manage_emojis, inline=True)
    embed.add_field(name="踢出成員", value=permission.kick_members, inline=True)
    embed.add_field(name="封鎖成員", value=permission.ban_members, inline=True)
    embed.add_field(name="觀看審核日誌", value=permission.view_audit_log, inline=True)
    # permission.create_instant_invite
    # permission.add_reactions
    # permission.priority_speaker
    # permission.stream
    # permission.read_messages
    # permission.send_messages
    # permission.send_tts_messages
    # permission.embed_links
    # permission.attach_files
    # permission.read_message_history
    # permission.mention_everyone
    # permission.external_emojis
    # permission.view_guild_insights
    # permission.connect
    # permission.speak
    # permission.mute_members
    # permission.deafen_members
    # permission.move_members
    # permission.use_voice_activation
    # permission.change_nickname
    # permission.use_slash_commands
    # permission.request_to_speak
    await ctx.send(embed=embed)

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

ignore_py = ['music']
for filename in os.listdir('./cmds'):
    if filename.endswith('.py') and filename[:-3] not in ignore_py:
        bot.load_extension(f'cmds.{filename[:-3]}')


if __name__ == "__main__":
    try:
        import keep_alive
        keep_alive.keep_alive()
    except:
        pass

    try:
        bot.run(token)
    except discord.errors.LoginFailure:
        print('發生錯誤:機器人登入失敗')