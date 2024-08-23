from datetime import datetime, timedelta

import discord
import mcrcon
from discord.ext import commands
from discord.commands import SlashCommandGroup

from starlib import BotEmbed,Jsondb,sclient
from starlib.utilities.utility import converter
from starlib.types import NotifyChannelType
from ..extension import Cog_Extension
from ..bot import DiscordBot

class SendMessageModal(discord.ui.Modal):
    def __init__(self, channel, bot, is_dm, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_item(discord.ui.InputText(label="要傳送的訊息", style=discord.InputTextStyle.long))
        self.channel = channel
        self.is_dm = is_dm
        self.bot:DiscordBot = bot
    
    async def callback(self, interaction: discord.Interaction):
        message = await self.channel.send(self.children[0].value)
        await interaction.response.send_message(f'訊息發送成功',delete_after=5,ephemeral=True)
        if self.is_dm:
            await self.bot.dm(interaction.client,message)


class AnnoModal(discord.ui.Modal):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_item(discord.ui.InputText(label="要傳送的公告", style=discord.InputTextStyle.long))

    async def callback(self, interaction: discord.Interaction):
        msg = await interaction.response.send_message(f"訊息發送中..")
        picdata = Jsondb.picdata
        embed = discord.Embed(description=self.children[0].value,color=0xc4e9ff,timestamp=datetime.now())
        embed.set_author(name="機器人全群公告",icon_url=picdata['radio_001'])
        embed.set_footer(text='Bot Radio System')
        send_success = 0
        channels = sclient.sqldb.get_notify_channel_by_type(NotifyChannelType.AllAnnouncements)

        for i in channels:
            channel = interaction.client.get_channel(i.channel_id)
            if channel:
                try:
                    if i.role_id:
                        role = channel.guild.get_role(i.role_id)
                        await channel.send(role.mention,embed=embed)
                    else:
                        await channel.send(embed=embed)
                    send_success += 1
                except:
                    pass
            else:
                    print(f"anno: {i.guild_id}/{i.channel_id}")

        await msg.edit_original_response(content=f"已向{send_success}/{len(channels)}個頻道發送公告")

class BotUpdateModal(discord.ui.Modal):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_item(discord.ui.InputText(label="要傳送的更新訊息", style=discord.InputTextStyle.long))

    async def callback(self, interaction: discord.Interaction):
        msg = await interaction.response.send_message(f"訊息發送中..")
        picdata = Jsondb.picdata
        embed = discord.Embed(description=self.children[0].value,color=0xc4e9ff,timestamp=datetime.now())
        embed.set_author(name="機器人更新通知",icon_url=picdata['radio_001'])
        embed.set_footer(text='Bot Radio System')
        send_success = 0
        channels = sclient.sqldb.get_notify_channel_by_type(NotifyChannelType.BotUpdates)

        for i in channels:
            channel = interaction.client.get_channel(i.channel_id)
            if channel:
                try:
                    if i.role_id:
                        role = channel.guild.get_role(i.role_id)
                        await channel.send(role.mention,embed=embed)
                    else:
                        await channel.send(embed=embed)
                    send_success += 1
                except:
                    pass
            else:
                print(f"botupdate: {i.guild_id}/{i.channel_id}")
        
        await msg.edit_original_response(content=f"已向{send_success}/{len(channels)}個頻道發送公告")

class BotPanel(discord.ui.View):
    def __init__(self,bot):
        super().__init__()
        self.bot = bot
    
    @discord.ui.button(label="伺服器列表",row=1,style=discord.ButtonStyle.primary)
    async def button_callback1(self, button: discord.ui.Button, interaction: discord.Interaction):
        name_list = []
        for i in self.bot.guilds:
            name_list.append(f'{i.name}（{i.id}）')
        embed = BotEmbed.simple('伺服器列表','\n'.join(name_list))
        await interaction.response.send_message(content="",ephemeral=False,embed=embed)

debug_guilds = Jsondb.config.get('debug_guilds')

class owner(Cog_Extension):
    twitch_chatbot = SlashCommandGroup("twitch_chatbot", "twitch機器人相關指令",guild_ids=debug_guilds)

    #load
    #@bot.command()
    @commands.slash_command(description='載入extension',guild_ids=debug_guilds)
    @commands.is_owner()
    async def load(self, ctx, extension):
        self.bot.load_extension(f'starDiscord.cmds.{extension}')
        await ctx.respond(f'Loaded {extension} done')

    #unload
    @commands.slash_command(description='關閉extension',guild_ids=debug_guilds)
    @commands.is_owner()
    async def unload(self, ctx, extension):
        self.bot.unload_extension(f'starDiscord.cmds.{extension}')
        await ctx.respond(f'Un - Loaded {extension} done')

    #reload
    @commands.slash_command(description='重載extension',guild_ids=debug_guilds)
    @commands.is_owner()
    async def reload(self, ctx, extension):
        self.bot.reload_extension(f'starDiscord.cmds.{extension}')
        await ctx.respond(f'Re - Loaded {extension} done')

    #ping
    @commands.slash_command(description='查詢延遲')
    async def ping(self, ctx):
        await ctx.respond(f'延遲為：{round(self.bot.latency*1000)} ms')
    
    #change_presence
    @commands.slash_command(description='更換bot狀態',guild_ids=debug_guilds)
    @commands.is_owner()
    async def statue(self,ctx,statue):
        config = Jsondb.config
        config.write('activity', statue)
        await self.bot.change_presence(activity=discord.Game(name=config.get("activity")),status=discord.Status.online)
        await ctx.respond(f'狀態更改完成',delete_after=5)

    #send
    @commands.slash_command(description='發送訊息',guild_ids=debug_guilds)
    @commands.is_owner()
    async def sendmesssage(self,ctx,
                   id:discord.Option(str,required=True,name='頻道id',description='')):      
        #modal = SendMessageModal(title="發送訊息")
        #await ctx.send_modal(modal)
        #msg = modal.children[0].value
        #await ctx.defer()
        id = int(id)
        channel = self.bot.get_channel(id)
        if channel:
            modal = SendMessageModal(title="發送訊息(頻道)", channel=channel, bot=self.bot, is_dm=False)
        else:
            user = self.bot.get_user(id)
            if user:
                modal = SendMessageModal(title="發送訊息(私訊)", channel=channel, bot=self.bot, is_dm=True)
            else:
                await ctx.respond(f'找不到此ID',ephemeral=True)
                return

        await ctx.send_modal(modal)
        await modal.wait()

    #all_anno
    @commands.slash_command(description='全群公告',guild_ids=debug_guilds)
    @commands.is_owner()
    async def anno(self,ctx:discord.ApplicationContext):
        modal = AnnoModal(title="全群公告")
        await ctx.send_modal(modal)
        await modal.wait()

    #bot_update
    @commands.slash_command(description='機器人更新通知',guild_ids=debug_guilds)
    @commands.is_owner()
    async def botupdate(self,ctx:discord.ApplicationContext):
        modal = BotUpdateModal(title="機器人更新")
        await ctx.send_modal(modal)
        await modal.wait()

    #edit
    @commands.slash_command(description='編輯訊息',guild_ids=debug_guilds)
    @commands.is_owner()
    async def editmessage(self,ctx:discord.ApplicationContext,msgid:str,new_msg):
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

    @commands.slash_command(description='權限檢查',guild_ids=debug_guilds)
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

    # @commands.slash_command(guild_ids=debug_guilds)
    # @commands.is_owner()
    # async def reaction_role(self,ctx,chaid,msgid):
    #     channel = await self.bot.fetch_channel(chaid)
    #     message = await channel.fetch_message(msgid)
    #     await message.edit('請點擊按鈕獲得權限',view=ReactRole_button())
    #     await ctx.respond('訊息已發送')

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

    @commands.slash_command(description='使用mc伺服器指令',guild_ids=debug_guilds)
    @commands.is_owner()
    async def mccommand(self,ctx,command):
        settings = Jsondb.config.get('mc_server')
        host = settings.get('host')
        port = settings.get('port')
        password = settings.get('password')
        with mcrcon.MCRcon(host, password, port) as rcon:
            response = rcon.command(command)
            await ctx.respond(response)

    # @twitch_chatbot.command(description='加入Twitch頻道',guild_ids=debug_guilds)
    # @commands.is_owner()
    # async def join(self,ctx,twitch_user):
    #     channel = twitch_bot.get_channel(twitch_user)
    #     if channel:
    #         await ctx.respond(f'加入 {twitch_user}')
    #     else:
    #         await ctx.respond(f'找不到 {twitch_user} 但仍加入')

    #         cache = Jsondb.cache
    #         cache.get('twitch_initial_channels').append(twitch_user)
    #         Jsondb.write('cache',cache)

    #         await twitch_bot.join_channels((twitch_user,))
            
    
    # @twitch_chatbot.command(description='離開Twitch頻道',guild_ids=debug_guilds)
    # @commands.is_owner()
    # async def leave(self,ctx,twitch_user):
    #     cache = Jsondb.cache
    #     if twitch_user in cache.get('twitch_initial_channels'):
    #         cache.get('twitch_initial_channels').remove(twitch_user)
    #         Jsondb.write('cache',cache)
    #         await twitch_bot.part_channels((twitch_user,))
    #         await ctx.respond(f'離開 {twitch_user}')
    #     else:
    #         await ctx.respond(f'錯誤：未加入 {twitch_user}')

    # @twitch_chatbot.command(description='發送消息到指定Twitch頻道',guild_ids=debug_guilds)
    # @commands.is_owner()
    # async def send(self,ctx,twitch_user,context):
    #     await twitch_bot.get_channel(twitch_user).send(context)
    #     await ctx.respond(f'已發送到 {twitch_user}: {context}')
    
    @commands.slash_command(description='機器人面板',guild_ids=debug_guilds)
    @commands.is_owner()
    async def panel(self,ctx):
        embed_list = []
        embed = BotEmbed.bot(self.bot,description=f'伺服器總數：{len(self.bot.guilds)}\n成員：{len(self.bot.users)}')
        embed_list.append(embed)

        await ctx.respond(f'',embeds=embed_list,view=BotPanel(self.bot))

    @commands.slash_command(description='獲取指令',guild_ids=debug_guilds)
    @commands.is_owner()
    async def getcommand(self,ctx,name:discord.Option(str,name='指令名稱')):
        data = self.bot.get_application_command(name)
        if data:
            await ctx.respond(embed=BotEmbed.simple(data.name,data.id))
        else:
            await ctx.respond(embed=BotEmbed.simple('指令未找到'))

    @commands.slash_command(description='獲取指定伺服器與主伺服器的共通成員',guild_ids=debug_guilds)
    @commands.is_owner()
    async def findmember(self,ctx,guildid:discord.Option(str,name='伺服器id')):
        guild = self.bot.get_guild(int(guildid))
        guild_main = self.bot.get_guild(613747262291443742)
        if not guild:
            await ctx.respond("伺服器未找到")
            return
        if guild == guild_main:
            await ctx.respond("伺服器重複")
            return

        member = guild.members
        member_main = guild_main.members
        common_member = [element for element in member if element in member_main]
        common_member_display = []
        for member in common_member:
            common_member_display.append(f"{member.mention} ({member.id})")
        
        embed = BotEmbed.simple(f"{guild.name} 的共通成員","\n".join(common_member_display))
        await ctx.respond(embed=embed)

    @commands.slash_command(description='尋找id對象',guild_ids=debug_guilds)
    @commands.cooldown(rate=1,per=3)
    async def find(self,ctx:discord.ApplicationContext,id:discord.Option(str,name='id'),guildid:discord.Option(str,name='guildid',required=False)):
        success = 0
        id = int(id)
        user = await self.bot.get_or_fetch_user(id)
        if user and user in ctx.guild.members:
            user = ctx.guild.get_member(user.id)
            embed = BotEmbed.simple(title=f'{user.name}#{user.discriminator}', description="ID:用戶(伺服器成員)")
            embed.add_field(name="暱稱", value=user.nick, inline=False)
            embed.add_field(name="最高身分組", value=user.top_role.mention, inline=True)
            embed.add_field(name="目前狀態", value=user.raw_status, inline=True)
            if user.activity:
                embed.add_field(name="目前活動", value=user.activity.name, inline=True)
            embed.add_field(name="是否為機器人", value=user.bot, inline=False)
            embed.add_field(name="是否為Discord官方", value=user.system, inline=True)
            embed.add_field(name="是否被禁言", value=user.timed_out, inline=True)
            embed.add_field(name="加入群組日期", value=user.joined_at, inline=False)
            embed.add_field(name="帳號創建日期", value=user.created_at, inline=False)
            embed.set_thumbnail(url=user.display_avatar.url)
            embed.set_footer(text=f"id:{user.id}")
            success += 1
        elif user:
            embed = BotEmbed.simple(title=f'{user.name}#{user.discriminator}', description="ID:用戶")
            embed.add_field(name="是否為機器人", value=user.bot, inline=False)
            embed.add_field(name="是否為Discord官方", value=user.system, inline=False)
            embed.add_field(name="帳號創建日期", value=user.created_at, inline=False)
            embed.set_thumbnail(url=user.display_avatar.url)
            success += 1

        channel = self.bot.get_channel(id)
        if channel:
            embed = BotEmbed.simple(title=channel.name, description="ID:頻道")
            embed.add_field(name="所屬類別", value=channel.category, inline=False)
            embed.add_field(name="所屬公會", value=channel.guild, inline=False)
            embed.add_field(name="創建時間", value=channel.created_at, inline=False)
            success += 1
        
        guild = self.bot.get_guild(id)
        if guild:
            embed = BotEmbed.simple(title=guild.name, description="ID:伺服器")
            embed.add_field(name="伺服器擁有者", value=guild.owner, inline=False)
            embed.add_field(name="創建時間", value=guild.created_at, inline=False)
            embed.add_field(name="驗證等級", value=guild.verification_level, inline=False)
            embed.add_field(name="成員數", value=len(guild.members), inline=False)
            embed.add_field(name="文字頻道數", value=len(guild.text_channels), inline=False)
            embed.add_field(name="語音頻道數", value=len(guild.voice_channels), inline=False)
            embed.set_footer(text='頻道數可能因權限不足而有少算，敬請特別注意')
            embed.set_thumbnail(url=guild.icon.url)
            success += 1

        if guildid:
            guildid = int(guildid)
            guild = self.bot.get_guild(guildid)
            role = guild.get_role(id)
            if role:
                embed = BotEmbed.simple(title=role.name, description="ID:身分組")
                embed.add_field(name="所屬伺服器", value=role.guild, inline=False)
                embed.add_field(name="創建時間", value=role.created_at, inline=False)
                embed.add_field(name="所屬層級位置", value=role.position, inline=False)
                embed.add_field(name="顏色", value=role.color, inline=False)
                if role.icon:
                    embed.set_thumbnail(url=role.icon.url)
                success += 1
            
        if success == 1:
            await ctx.respond(embed=embed)
        elif success > 1:
            await ctx.respond(f'find:id重複(出現{success}次)')
        else:
            await ctx.respond('無法辨認此ID')

    @commands.slash_command(description='以機器人禁言用戶',guild_ids=debug_guilds)
    @commands.bot_has_permissions(moderate_members=True)
    @commands.is_owner()
    async def timeout_bot(self,ctx:discord.ApplicationContext,
                      channelid:discord.Option(str,name='頻道',description='要發送警告單的頻道',required=True),
                      userid:discord.Option(str,name='用戶',description='要禁言的用戶',required=True),
                      time_last:discord.Option(str,name='時長',description='格式為30s、1h20m等，支援天(d)、小時(h)、分鐘(m)、秒(s)',required=True),
                      reason:discord.Option(str,name='原因',description='限100字內',required=False)):
        await ctx.defer()
        time = converter.time_to_datetime(time_last)
        channel = self.bot.get_channel(int(channelid))
        if not time or time > timedelta(days=7) :
            await ctx.respond(f"錯誤：時間格式錯誤（不得超過7天）")
            return
        
        user = channel.guild.get_member(int(userid))
        await user.timeout_for(time,reason=reason)
        
        moderate_user = self.bot.user
        create_time = datetime.now()
        
        timestamp = int((create_time+time).timestamp())
        embed = BotEmbed.general(f'{user.name} 已被禁言',user.display_avatar.url,description=f"{user.mention}：{reason}")
        embed.add_field(name="執行人員",value=moderate_user.mention)
        embed.add_field(name="結束時間",value=f"<t:{timestamp}>（{time_last}）")
        embed.timestamp = create_time
        msg = await channel.send(embed=embed)
        await ctx.respond(msg.jump_url)

def setup(bot):
    bot.add_cog(owner(bot))