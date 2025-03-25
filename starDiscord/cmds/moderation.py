from datetime import datetime, timedelta

import discord
from discord.commands import SlashCommandGroup
from discord.ext import commands

from starlib import BotEmbed, ChoiceList, Jsondb, sclient
from starlib.instance import debug_guilds
from starlib.types import NotifyChannelType, WarningType
from starlib.utils import converter
from starlib.models.mysql import ReactionRoleMessage, ReactionRole
from ..uiElement.view import ReactionRoleView

from ..extension import Cog_Extension

set_option = ChoiceList.set('channel_set_option')

class moderation(Cog_Extension):
    warning = SlashCommandGroup("warning", "警告相關指令")
    channel_notify = SlashCommandGroup("channel", "自動通知相關指令")
    react_role = SlashCommandGroup("reactrole", "反應身分組相關指令")
    
    @commands.slash_command(description='清理訊息')
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_guild_permissions(manage_messages=True)
    @commands.guild_only()
    async def clean(self,
                    ctx:discord.ApplicationContext,
                    num:discord.Option(int,name='數量',description='要清理的訊息數，與訊息id擇一提供',required=False),
                    message_id:discord.Option(str,name='訊息id',description='如果提供，將刪除比此訊息更新的所有訊息（該訊息本身不會被刪）',required=False)):
        await ctx.defer()
        if message_id:
            message = await ctx.channel.fetch_message(int(message_id))
            if message:
                time = message.created_at
                await ctx.channel.purge(after=time)
                await ctx.respond(content=f'清除完成',delete_after=5)
            else:
                await ctx.respond(content=f'沒有找到此訊息',ephemeral=True)

        elif num:
            await ctx.channel.purge(limit=num)
            await ctx.respond(content=f'清除完成，清除了{num}則訊息',delete_after=5)
        else:
            await ctx.respond(content=f'沒有提供任何資訊，所以沒有清除任何內容',delete_after=5)

    @channel_notify.command(description='設定通知頻道')
    @commands.has_permissions(manage_channels=True)
    @commands.guild_only()
    async def set(self,ctx:discord.ApplicationContext,
                  notify_type:discord.Option(int,name='通知類型',description='要接收的通知類型',required=True,choices=set_option),
                  channel:discord.Option(discord.abc.GuildChannel,name='頻道',description='要接收通知的頻道',default=None),
                  role:discord.Option(discord.Role,required=False,name='身分組',description='發送通知時tag的身分組，定時通知與部分通知不會tag', default=None),
                  msg:discord.Option(str,default=None,name='通知文字',description='發送通知時的自訂文字')):
        guildid = ctx.guild.id
        notify_type = NotifyChannelType(notify_type)
        
        if channel:
            roleid = role.id if role else None
            sclient.sqldb.add_notify_channel(guildid,notify_type,channel.id,roleid, msg)
            await ctx.respond(f'設定完成，已將 {Jsondb.get_tw(notify_type,"channel_set_option")} 頻道設定在 {channel.mention}')
            await ctx.send(embed=BotEmbed.simple('溫馨提醒','若為定時通知，請將機器人的訊息保持在此頻道的最新訊息，以免機器人找不到訊息而重複發送'),delete_after=10)
            if not channel.can_send():
                await ctx.send(embed=BotEmbed.simple('溫馨提醒',f'我無法在{channel.mention}中發送訊息，請確認我有足夠的權限'))
        else:
            sclient.sqldb.remove_notify_channel(guildid,notify_type)
            await ctx.respond(f'設定完成，已移除 {Jsondb.get_tw(notify_type,"channel_set_option")} 頻道')

    @channel_notify.command(description='設定動態語音頻道')
    @commands.has_permissions(manage_channels=True)
    @commands.guild_only()
    async def voice(self,ctx:discord.ApplicationContext,
                    channel:discord.Option(discord.VoiceChannel,name='頻道',description='動態語音頻道',default=None)):
        if channel:
            sclient.sqldb.add_notify_channel(ctx.guild.id, NotifyChannelType.DynamicVoice, channel.id)
            await ctx.respond(f'設定完成，已將 {channel.mention} 設定為動態語音頻道')
        else:
            sclient.sqldb.remove_notify_channel(ctx.guild.id, NotifyChannelType.DynamicVoice)
            await ctx.respond(f'設定完成，已移除 動態語音 頻道')
    
    @channel_notify.command(description='查看通知設定的頻道')
    @commands.has_permissions(manage_channels=True)
    @commands.guild_only()
    async def list(self,ctx:discord.ApplicationContext):
        dbdata = sclient.sqldb.get_notify_channel_all(ctx.guild.id)
        embed = BotEmbed.general("通知頻道",ctx.guild.icon.url if ctx.guild.icon else None)
        for data in dbdata:
            notify_type = data.notify_type
            channel_id = data.channel_id
            role_id = data.role_id
            
            channel = self.bot.get_channel(channel_id)
            role = ctx.guild.get_role(role_id) if role_id else None

            text = "找不到頻道"
            if channel:
                text = channel.mention
                if role:
                    text += f" {role.mention}"
            embed.add_field(name=Jsondb.get_tw(notify_type,"channel_set_option"), value=text)
        await ctx.respond(embed=embed)
        
    
    @warning.command(description='給予用戶警告，此警告可連動至其他群組')
    @commands.has_guild_permissions(manage_messages=True)
    @commands.guild_only()
    async def add(self,ctx:discord.ApplicationContext,
                      user:discord.Option(discord.User,name='用戶',description='要給予警告的用戶',required=True),
                      reason:discord.Option(str,name='原因',description='限100字內'),
                      add_record:discord.Option(bool,name='是否要將此紀錄存入警告系統',description='將紀錄存入警告系統供其他群組檢視',default=False)):
        is_owner = await self.bot.is_owner(ctx.author)
        if (ctx.author == user or user not in ctx.guild.members) and not is_owner:
            await ctx.respond("只能警告在伺服器內的成員")
            return
        if user.bot:
            await ctx.respond("不能警告機器人")
            return

        time = datetime.now()
        moderate_user = ctx.author.id
        warning_id = sclient.sqldb.add_warning(user.id, WarningType.Warning, moderate_user, ctx.guild.id, time, reason, None, not add_record)
        embed = BotEmbed.general(f'{user.name} 已被警告',user.display_avatar.url,description=f"{user.mention}：{reason}")
        embed.add_field(name="執行人員",value=ctx.author.mention)
        embed.add_field(name="存入跨群警告系統",value=add_record)
        embed.timestamp = time
        embed.set_footer(text=f"編號 {warning_id}")
        await ctx.respond(embed=embed)
    
    @warning.command(description='獲取用戶的所有警告')
    @commands.guild_only()
    async def list(self,ctx:discord.ApplicationContext,
                      user:discord.Option(discord.User,name='用戶',description='要查詢的用戶',required=True),
                      guild_only:discord.Option(bool,name='查詢是否包含伺服器區域警告',description='預設為True',default=True)):
        dbdata = sclient.sqldb.get_warnings(user.id, ctx.guild.id if guild_only else None)
        await ctx.respond(embed=dbdata.display(self.bot))

    @warning.command(description='獲取指定警告')
    @commands.guild_only()
    async def get(self,ctx:discord.ApplicationContext,
                      warning_id:discord.Option(str,name='警告編號',description='要查詢的警告',required=True)):
        sheet = sclient.sqldb.get_warning(int(warning_id))
        if sheet and (ctx.guild.get_member(sheet.discord_id) or ctx.guild.id in debug_guilds):
            await ctx.respond(embed=sheet.embed(self.bot))
        else:
            await ctx.respond("查無此警告單")

    @warning.command(description='移除用戶警告')
    @commands.check_any(commands.has_guild_permissions(kick_members=True), 
                        commands.has_guild_permissions(ban_members=True),
                        commands.has_guild_permissions(manage_messages=True))
    @commands.guild_only()
    async def remove(self,ctx:discord.ApplicationContext,
                     warning_id:discord.Option(str,name='警告編號',description='要移除的警告',required=True)):
        dbdata = sclient.sqldb.get_warning(int(warning_id))
        is_owner = await self.bot.is_owner(ctx.author)
        if dbdata:
            guild = self.bot.get_guild(dbdata.create_guild)
            if guild != ctx.guild and not is_owner:
                await ctx.respond("不能移除非此伺服器發出的警告")
                return
            sclient.sqldb.remove_warning(int(warning_id))
            await ctx.respond(f"已移除編號：{warning_id}的警告")
        else:
            await ctx.respond("查無此警告單")

    @commands.slash_command(description='禁言用戶')
    @commands.has_guild_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    @commands.guild_only()
    async def timeout(self,ctx:discord.ApplicationContext,
                      user:discord.Option(discord.Member,name='用戶',description='要禁言的用戶',required=True),
                      time_last:discord.Option(str,name='時長',description='格式為30s、1h20m等，支援天(d)、小時(h)、分鐘(m)、秒(s)',required=True),
                      reason:discord.Option(str,name='原因',description='限100字內',default="已禁言"),
                      add_record:discord.Option(bool,name='是否要將此紀錄存入警告系統',description='將紀錄存入警告系統供其他群組檢視',default=False)):
        await ctx.defer()
        time = converter.time_to_datetime(time_last)
        if not time or time > timedelta(days=7) :
            await ctx.respond(f"錯誤：時間格式錯誤（不得超過7天）")
            return
        
        await user.timeout_for(time,reason=reason)
        
        moderate_user = ctx.user.id
        create_time = datetime.now()
        if add_record and not user.bot:
            sclient.sqldb.add_warning(user.id, WarningType.Timeout, moderate_user, ctx.guild.id, create_time, reason, time_last, guild_only=False)
        
        timestamp = int((create_time+time).timestamp())
        embed = BotEmbed.general(f'{user.name} 已被禁言',user.display_avatar.url,description=f"{user.mention}：{reason}")
        embed.add_field(name="執行人員",value=ctx.author.mention)
        embed.add_field(name="結束時間",value=f"<t:{timestamp}>（{time_last}）")
        embed.timestamp = create_time
        await ctx.respond(embed=embed)

    @commands.slash_command(description='踢除用戶')
    @commands.has_guild_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    @commands.guild_only()
    async def kick(self,ctx:discord.ApplicationContext,
                      user:discord.Option(discord.Member,name='用戶',description='要踢除的用戶',required=True),
                      reason:discord.Option(str,name='原因',description='限100字內',required=False),
                      add_record:discord.Option(bool,name='是否要將此紀錄存入警告系統',description='將紀錄存入警告系統供其他群組檢視',default=False)):
        await ctx.defer()
        await user.kick(reason=reason)
        
        moderate_user = ctx.user.id
        create_time = datetime.now()
        if add_record and not user.bot:
            sclient.sqldb.add_warning(user.id, WarningType.Kick, moderate_user, ctx.guild.id, create_time, reason, guild_only=False)
        
        embed = BotEmbed.general(f'{user.name} 已被踢除',user.display_avatar.url,description=f"{user.mention}：{reason}")
        embed.add_field(name="執行人員",value=ctx.author.mention)
        embed.timestamp = create_time
        await ctx.respond(embed=embed)

    @commands.slash_command(description='停權用戶')
    @commands.has_guild_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    @commands.guild_only()
    async def ban(self,ctx:discord.ApplicationContext,
                      user:discord.Option(discord.Member,name='用戶',description='要停權的用戶',required=True),
                      reason:discord.Option(str,name='原因',description='限100字內',required=True),
                      add_record:discord.Option(bool,name='是否要將此紀錄存入警告系統',description='將紀錄存入警告系統供其他群組檢視',default=False),
                      #delete_message_seconds:discord.Option(int,name='刪除指定秒數內訊息',description='若提供，將刪除用戶指定秒數內的所有訊息',default=None,min_value=1),
                      delete_message_days:discord.Option(int,name='刪除指定天數內訊息',description='若提供，將刪除用戶指定天數內的所有訊息',default=None,min_value=1,max_value=7)):
        await ctx.defer()
        await user.ban(reason=reason,delete_message_days=delete_message_days)
        
        moderate_user = ctx.user.id
        create_time = datetime.now()
        if add_record and not user.bot:
            sclient.sqldb.add_warning(user.id, WarningType.Ban, moderate_user, ctx.guild.id, create_time, reason, guild_only=False)
        
        embed = BotEmbed.general(f'{user.name} 已被停權',user.display_avatar.url,description=f"{user.mention}：{reason}")
        embed.add_field(name="執行人員",value=ctx.author.mention)
        embed.timestamp = create_time
        await ctx.respond(embed=embed)

    @react_role.command(description='新增反應身分組訊息，需新增反應身分組訊息後才能設定反應身分組')
    @commands.has_permissions(manage_roles=True)
    @commands.guild_only()
    async def addmessage(self, ctx:discord.ApplicationContext,
                         content:discord.Option(str, name='訊息', description='要設定的訊息', required=True)):
        await ctx.defer()
        msg = await ctx.channel.send(content)
        sclient.sqldb.merge(ReactionRoleMessage(ctx.guild.id, ctx.channel.id, msg.id, content))
        await ctx.respond("已新增反應身分組訊息", delete_after=5)

    @react_role.command(description='移除反應身分組訊息')
    @commands.has_permissions(manage_roles=True)
    @commands.guild_only()
    async def removemessage(self, ctx:discord.ApplicationContext,
                            message_id:discord.Option(str, name='訊息id', description='要移除的訊息id', required=True)):
        await ctx.defer()
        message = await ctx.channel.fetch_message(int(message_id))
        if not message:
            await ctx.respond("找不到此訊息，請在該訊息的頻道進行設定", delete_after=5)
            return
        await message.delete()
        sclient.sqldb.delete_reaction_role_message(message.id)
        await ctx.respond("已移除反應身分組訊息", delete_after=5)
        
    @react_role.command(description='設定反應身分組')
    @commands.has_permissions(manage_roles=True)
    @commands.guild_only()
    async def setrole(self, ctx:discord.ApplicationContext,
                      message_id:discord.Option(str, name='訊息id', description='要設定的訊息id', required=True),
                      role:discord.Option(discord.Role,name='身分組',description='要設定的身分組',required=True),
                      title:discord.Option(str,name='表情符號',description='要設定的表情符號',required=True),
                      description:discord.Option(str,name='描述',description='要設定的描述',required=False)):
        await ctx.defer()
        message = await ctx.channel.fetch_message(int(message_id))
        if not message:
            await ctx.respond("找不到此訊息，請在該訊息的頻道進行設定", delete_after=5)
            return
        
        sclient.sqldb.merge(ReactionRole(message.id, role.id, title, description))
        react_roles = sclient.sqldb.get_reaction_roles_by_message(message.id)
        await message.edit(view=ReactionRoleView(message.id, react_roles))        
        
        await ctx.respond(f"已新增 {title} 給 {role.mention}", delete_after=5)

    @react_role.command(description='移除反應身分組')
    @commands.has_permissions(manage_roles=True)
    @commands.guild_only()
    async def removerole(self, ctx:discord.ApplicationContext,
                        message_id:discord.Option(str, name='訊息id', description='要設定的訊息id', required=True),
                        role:discord.Option(discord.Role,name='身分組',description='要設定的身分組',required=True)):
        await ctx.defer()
        message = await ctx.channel.fetch_message(int(message_id))
        if not message:
            await ctx.respond("找不到此訊息，請在該訊息的頻道進行設定", delete_after=5)
            return
        
        sclient.sqldb.delete_reaction_role(message.id, role.id)
        react_roles = sclient.sqldb.get_reaction_roles_by_message(message.id)
        await message.edit(view=ReactionRoleView(message.id, react_roles))
        await ctx.respond(f"已移除 {role.mention}", delete_after=5)
    
def setup(bot):
    bot.add_cog(moderation(bot))