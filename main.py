import discord
from discord.ext import commands
import json, random, datetime, asyncio, os
from library import find

intents = discord.Intents.all()
#intents.typing = False
#intents.presences = False
#intents.members = True
#intents.guilds = True
#intents.messages = True
#intents.voice_states = True

#1:dc小幫手 2:Bep
bot_code = 2

jdata = json.load(open('setting.json',mode='r',encoding='utf8'))
cdata = json.load(open('database/channel_settings.json',mode='r',encoding='utf8'))
picdata = json.load(open('database/picture.json',mode='r',encoding='utf8'))

if bot_code ==1:
    bot = commands.Bot(command_prefix=commands.when_mentioned_or('!!'),owner_id=419131103836635136,intents=intents,case_insensitive=True, help_command=None)
elif bot_code == 2:
    bot = commands.Bot(command_prefix=commands.when_mentioned_or('b!'),owner_id=419131103836635136,intents=intents,case_insensitive=True, help_command=None)
else:
    raise ValueError("Invalid bot_code")

#啟動
@bot.event
async def on_ready():
    print(">> Bot is online <<")
    print(">> Bot online as",bot.user.name,"<<")
    print(">> Discord's version:",discord.__version__,"<<")
    await bot.change_presence(activity=discord.Game(name='!!help'))
    

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

    embed=discord.Embed(description=f'{msg}',color=0xc4e9ff)
    embed.set_author(name="Bot Radio Station",icon_url=picdata['radio_001'])
    embed.set_footer(text='廣播電台 | 機器人全群公告')
    
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
async def edit(ctx,msgID:int,*,new_msg):
    message = await ctx.fetch_message(msgID)
    #message = channel.get_partial_message(msgID)
    await message.edit(content=new_msg)
    await ctx.message.add_reaction('✅')

#reaction
@bot.command()
@commands.is_owner()
async def reaction(ctx,msgID:int,mod:str,*,emojiID):
    message = await ctx.fetch_message(msgID)
    channel = message.channel
    #message = channel.get_partial_message(msgID)
    emoji = find.emoji(emojiID)

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


@bot.slash_command()
async def hello(ctx, name: str = None):
    name = name or ctx.author.name
    await ctx.respond(f"Hello {name}!")


for filename in os.listdir('./cmds'):
    if filename.endswith('.py') and filename not in ['task']:
        bot.load_extension(f'cmds.{filename[:-3]}')


if __name__ == "__main__":
    if bot_code == 1:
        try:
            import keep_alive
            keep_alive.keep_alive()
        except:
            pass
        bot.run(jdata['TOKEN'])
    elif bot_code == 2:
        bot.run(jdata['Bep_TOKEN'])