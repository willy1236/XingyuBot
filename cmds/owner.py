import discord,os,mcrcon,datetime
from discord.ext import commands
from discord.commands import SlashCommandGroup

from core.classes import Cog_Extension
from starcord import BotEmbed,BRS,Jsondb,sqldb,twitch_bot

from starcord.ui_element.button import ReactRole_button

class SendMessageModal(discord.ui.Modal):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_item(discord.ui.InputText(label="要傳送的訊息", style=discord.InputTextStyle.long))

class AnnoModal(discord.ui.Modal):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_item(discord.ui.InputText(label="要傳送的公告", style=discord.InputTextStyle.long))

    async def callback(self, interaction: discord.Interaction):
        picdata = Jsondb.picdata
        embed = discord.Embed(description=self.children[0].value,color=0xc4e9ff,timestamp=datetime.datetime.now())
        embed.set_author(name="機器人全群公告",icon_url=picdata['radio_001'])
        embed.set_footer(text='Bot Radio System')
        send_success = 0
        channels = sqldb.get_notice_channel('all_anno')

        for i in channels:
            channel = interaction.client.get_channel(i['channel_id'])
            if channel:
                try:
                    await channel.send(embed=embed)
                    send_success += 1
                except:
                    pass

        await interaction.response.send_message(f"已向{send_success}/{len(channels)}個頻道發送公告")

class BotUpdateModal(discord.ui.Modal):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_item(discord.ui.InputText(label="要傳送的更新訊息", style=discord.InputTextStyle.long))

    async def callback(self, interaction: discord.Interaction):
        picdata = Jsondb.picdata
        embed = discord.Embed(description=self.children[0].value,color=0xc4e9ff,timestamp=datetime.datetime.now())
        embed.set_author(name="機器人更新通知",icon_url=picdata['radio_001'])
        embed.set_footer(text='Bot Radio System')
        send_success = 0
        channels = sqldb.get_notice_channel('all_anno')

        for i in channels:
            channel = interaction.client.get_channel(i['channel_id'])
            if channel:
                try:
                    await channel.send(embed=embed)
                    send_success += 1
                except:
                    pass

        await interaction.response.send_message(f"已向{send_success}/{len(channels)}個頻道發送公告")

class BotPanel(discord.ui.View):
    def __init__(self,bot):
        super().__init__()
        self.bot = bot
    
    @discord.ui.button(label="伺服器列表",row=1,style=discord.ButtonStyle.primary)
    async def button_callback1(self, button: discord.ui.Button, interaction: discord.Interaction):
        name_list = []
        for i in self.bot.guilds:
            name_list.append(i.name)
        embed = BotEmbed.simple('伺服器列表',','.join(name_list))
        await interaction.response.send_message(content="",ephemeral=False,embed=embed)

debug_guild = Jsondb.jdata.get('debug_guild')

class owner(Cog_Extension):
    
    twitch_chatbot = SlashCommandGroup("twitch_chatbot", "twitch機器人相關指令",guild_ids=debug_guild)
    
    #change_presence
    @commands.slash_command(description='更換bot狀態',guild_ids=debug_guild)
    @commands.is_owner()
    async def statue(self,ctx,statue):
        jdata = Jsondb.jdata
        jdata['activity'] = statue
        await self.bot.change_presence(activity=discord.Game(name=jdata.get("activity","/help")),status=discord.Status.online)
        Jsondb.write('jdata',jdata)
        await ctx.respond(f'狀態更改完成',delete_after=5)

    #send
    @commands.slash_command(description='發送訊息',guild_ids=debug_guild)
    @commands.is_owner()
    async def send(self,ctx,
                   id:discord.Option(str,required=True,name='頻道id',description=''),
                   msg:discord.Option(str,required=True,name='訊息',description='')):      
        #modal = SendMessageModal(title="發送訊息")
        #await ctx.send_modal(modal)
        #msg = modal.children[0].value
        await ctx.defer()
        id = int(id)
        channel = self.bot.get_channel(id)
        if channel:
            await channel.send(msg)
        else:
            user = self.bot.get_user(id)
            message = await user.send(msg)
            await BRS.dm(self,message)
        await ctx.respond(f'訊息發送成功',delete_after=5,ephemeral=True)

    #all_anno
    @commands.slash_command(description='全群公告',guild_ids=debug_guild)
    @commands.is_owner()
    async def anno(self,ctx:discord.ApplicationContext):
        modal = AnnoModal(title="全群公告")
        await ctx.send_modal(modal)
        await modal.wait()

    #bot_update
    @commands.slash_command(description='機器人更新通知',guild_ids=debug_guild)
    @commands.is_owner()
    async def botupdate(self,ctx:discord.ApplicationContext):
        modal = BotUpdateModal(title="機器人更新")
        await ctx.send_modal(modal)
        await modal.wait()

    #edit
    @commands.slash_command(description='編輯訊息',guild_ids=debug_guild)
    @commands.is_owner()
    async def edit(self,ctx,msgid:str,new_msg):
        await ctx.defer()
        message = await ctx.fetch_message(int(msgid))
        await message.edit(content=new_msg)
        await ctx.respond(f'訊息修改成功',delete_after=5,ephemeral=True)
    #     await ctx.message.add_reaction('✅')

    # #reaction
    # @commands.slash_command(description='反應訊息',guild_ids=main_guild)
    # @commands.is_owner()
    # async def reaction(self,ctx,msgid:int,mod:str,*,emojiid):
    #     message = await ctx.fetch_message(msgid)
    #     channel = message.channel
    #     emoji = find.emoji(emojiid)

    #     if emoji == None:
    #         await ctx.send(f'反應添加失敗:找不到表情符號',delete_after=5)
    #     elif mod == 'add':
    #         await message.add_reaction(emoji)
    #         await ctx.send(f'反應添加完成,{channel.mention}',delete_after=10)
    #     elif mod == 'remove':
    #         await message.remove_reaction(emoji,member=self.bot.user)
    #         await ctx.send(f'反應移除完成,{channel.mention}',delete_after=10)
    #     else:
    #         ctx.send('參數錯誤:請輸入正確模式(add/remove)',delete_after=5)

    @commands.slash_command(description='權限檢查',guild_ids=debug_guild)
    @commands.is_owner()
    async def permission(self,ctx,guild_id):
        guild_id = int(guild_id)
        guild = self.bot.get_guild(guild_id)
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
        embed.add_field(name="管理討論串", value=permission.manage_threads, inline=True)
        embed.add_field(name="管理活動", value=permission.manage_events, inline=True)
        embed.add_field(name="踢出成員", value=permission.kick_members, inline=True)
        embed.add_field(name="封鎖成員", value=permission.ban_members, inline=True)
        embed.add_field(name="禁言成員", value=permission.moderate_members, inline=True)
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
        await ctx.respond(embed=embed)

    @commands.slash_command(guild_ids=debug_guild)
    @commands.is_owner()
    async def reaction_role(self,ctx,chaid,msgid):
        channel = await self.bot.fetch_channel(chaid)
        message = await channel.fetch_message(msgid)
        await message.edit('請點擊按鈕獲得權限',view=ReactRole_button())
        await ctx.respond('訊息已發送')

    #reset
    @commands.slash_command(description='資料重置',guild_ids=debug_guild)
    @commands.is_owner()
    async def reset(self,ctx,arg=None):
        await ctx.defer()
        if arg == 'sign':
            task_report_channel = self.bot.get_channel(Jsondb.jdata['task_report'])
            self.sqldb.truncate_table('user_sign')

            await task_report_channel.send('簽到已重置')
            await ctx.respond('簽到已重置',delete_after=5)
        elif not arg:
            for filename in os.listdir('./cmds'):
                if filename.endswith('.py'):
                    self.bot.reload_extension(f'cmds.{filename[:-3]}')
            await ctx.respond('Re - Loaded all done',delete_after=5)

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

    @commands.slash_command(description='使用mc伺服器指令',guild_ids=debug_guild)
    @commands.is_owner()
    async def mccommand(self,ctx,command):
        settings = Jsondb.jdata.get('mc_server')
        host = settings.get('host')
        port = settings.get('port')
        password = settings.get('password')
        with mcrcon.MCRcon(host, password, port) as rcon:
            response = rcon.command(command)
            await ctx.respond(response)

    @twitch_chatbot.command(description='加入Twitch頻道',guild_ids=debug_guild)
    @commands.is_owner()
    async def join(self,ctx,twitch_user):
        channel = twitch_bot.get_channel(twitch_user)
        if channel:
            await ctx.respond(f'加入 {twitch_user}')
        else:
            await ctx.respond(f'找不到 {twitch_user} 但仍加入')

            cache = Jsondb.cache
            cache.get('twitch_initial_channels').append(twitch_user)
            Jsondb.write('cache',cache)

            await twitch_bot.join_channels((twitch_user,))
            
    
    @twitch_chatbot.command(description='離開Twitch頻道',guild_ids=debug_guild)
    @commands.is_owner()
    async def leave(self,ctx,twitch_user):
        cache = Jsondb.cache
        if twitch_user in cache.get('twitch_initial_channels'):
            cache.get('twitch_initial_channels').remove(twitch_user)
            Jsondb.write('cache',cache)
            await twitch_bot.part_channels((twitch_user,))
            await ctx.respond(f'離開 {twitch_user}')
        else:
            await ctx.respond(f'錯誤：未加入 {twitch_user}')

    @twitch_chatbot.command(description='發送消息到指定Twitch頻道',guild_ids=debug_guild)
    @commands.is_owner()
    async def send(self,ctx,twitch_user,context):
        await twitch_bot.get_channel(twitch_user).send(context)
        await ctx.respond(f'已發送到 {twitch_user}: {context}')
    
    @commands.slash_command(description='機器人面板',guild_ids=debug_guild)
    @commands.is_owner()
    async def panel(self,ctx,guild:discord.Option(bool,name='是否列出伺服器')):
        embed_list = []
        embed = BotEmbed.basic(self,description=f'伺服器總數：{len(self.bot.guilds)}\n成員：{len(self.bot.users)}')
        embed_list.append(embed)
        
        if guild:
            name_list = []
            for i in self.bot.guilds:
                name_list.append(i.name)
            embed = BotEmbed.simple('伺服器列表',','.join(name_list))
            embed_list.append(embed)

        await ctx.respond(f'',embeds=embed_list,view=BotPanel(self.bot))

    @commands.slash_command(description='獲取指令',guild_ids=debug_guild)
    @commands.is_owner()
    async def getcommand(self,ctx,name:discord.Option(str,name='指令名稱')):
        data = self.bot.get_application_command(name)
        if data:
            await ctx.respond(embed=BotEmbed.simple(data.name,data.id))
        else:
            await ctx.respond(embed=BotEmbed.simple('指令未找到'))


def setup(bot):
    bot.add_cog(owner(bot))