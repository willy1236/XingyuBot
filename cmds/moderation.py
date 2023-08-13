import discord,datetime
from discord.ext import commands
from discord.commands import SlashCommandGroup
from core.classes import Cog_Extension
from starcord import ChoiceList,BotEmbed,Jsondb,sqldb
from starcord.utility import converter

set_option = ChoiceList.set('channel_set_option')

# def update_dict():
#     global voice_lobby_list
#     voice_lobby_list = []
#     dbdata = sqldb.get_notice_channel_by_type("voice_lobby")
#     for data in dbdata:
#         voice_lobby_list.append(data["channel_id"])


# update_dict()

class moderation(Cog_Extension):
    warning = SlashCommandGroup("warning", "警告相關指令")
    channel_notify = SlashCommandGroup("channel", "自動通知相關指令")
    
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
            await ctx.respond(content=f'沒有提供任何訊息，所以沒有清除任何內容',delete_after=5)

    @channel_notify.command(description='設定通知頻道')
    @commands.has_permissions(manage_channels=True)
    @commands.guild_only()
    async def set(self,ctx:discord.ApplicationContext,
                  notice_type:discord.Option(str,name='通知類型',description='要接收的通知類型',required=True,choices=set_option),
                  channel:discord.Option(discord.abc.GuildChannel,name='頻道',description='要接收通知的頻道',default=None),
                  role:discord.Option(discord.Role,required=False,name='身分組',description='發送通知時tag的身分組，若為定時通知則不會tag',default=None)):
        guildid = ctx.guild.id
        
        if channel:
            roleid = role.id if role else None
            sqldb.set_notice_channel(guildid,notice_type,channel.id,roleid)
            await ctx.respond(f'設定完成，已將 {ChoiceList.get_tw(notice_type,"channel_set_option")} 頻道設為 {channel.mention}')
            await ctx.send(embed=BotEmbed.simple('溫馨提醒','若為定時通知，請將機器人的訊息保持在此頻道的最新訊息，以免機器人找不到訊息而重複發送'),delete_after=10)
        else:
            sqldb.remove_notice_channel(guildid,notice_type)
            await ctx.respond(f'設定完成，已移除 {notice_type} 頻道')

    @channel_notify.command(description='查看通知設定的頻道')
    @commands.has_permissions(manage_channels=True)
    @commands.guild_only()
    async def list(self,ctx:discord.ApplicationContext):
        dbdata = sqldb.get_all_notice_channel(str(ctx.guild.id))
        embed = BotEmbed.general("通知頻道",ctx.guild.icon.url if ctx.guild.icon else discord.Embed.Empty)
        for data in dbdata:
            notice_type = data['notice_type']
            channel_id = data['channel_id']
            role_id = data['role_id']
            
            channel = self.bot.get_channel(channel_id)
            if role_id:
                role = ctx.guild.get_role(role_id)
            else:
                role = None

            text = "找不到頻道"
            if channel:
                text = channel.mention
                if role:
                    text += f" {role.mention}"
            embed.add_field(name=ChoiceList.get_tw(notice_type,"channel_set_option"), value=text)
        await ctx.respond(embed=embed)

    #@channel_notify.command(description='設定動態語音頻道')
    
    @warning.command(description='給予用戶警告，此警告將會連動至其他群組')
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def add(self,ctx,
                      user:discord.Option(discord.User,name='用戶',description='要給予警告的用戶',required=True),
                      reason:discord.Option(str,name='原因',description='限100字內')):
        is_owner = await self.bot.is_owner(ctx.author)
        if not user in ctx.guild.members and not is_owner:
            await ctx.respond("只能警告在伺服器內的成員")
            return
        if user.bot:
            await ctx.respond("不能警告機器人")
            return

        time = datetime.datetime.now()
        moderate_user = ctx.author.id
        sqldb.add_warning(user.id,'warning',moderate_user,ctx.guild.id,time,reason,None)
        embed = BotEmbed.general(f'{user.name} 的警告單',user.display_avatar.url,description=f"{user.mention}：{reason}")
        embed.add_field(name="執行人員",value=ctx.author.mention)
        embed.timestamp = time
        await ctx.respond(embed=embed)
    
    @warning.command(description='獲取用戶的所有警告')
    @commands.guild_only()
    async def list(self,ctx,
                      user:discord.Option(discord.User,name='用戶',description='要查詢的用戶',required=True)):
        dbdata = sqldb.get_warnings(user.id)
        embed = BotEmbed.general(f'{user.name} 的警告單列表（共{len(dbdata)}筆）',user.display_avatar.url)
        for i in dbdata:
            moderate_user = self.bot.get_user(i['moderate_user'])
            guild = self.bot.get_guild(i['create_guild'])
            time_str = i['create_time']
            moderate_type = i['moderate_type']
            last_time = i['last_time']
            if last_time:
                moderate_type += f" {last_time}"
            embed.add_field(name=f"編號: {i['warning_id']} ({moderate_type})",value=f"{guild.name}/{moderate_user.mention}\n{i['reason']}\n{time_str}")
        await ctx.respond(embed=embed)

    @warning.command(description='獲取指定警告')
    @commands.guild_only()
    async def get(self,ctx,
                      warning_id:discord.Option(str,name='警告編號',description='要查詢的警告',required=True)):
        dbdata = sqldb.get_warning(int(warning_id))
        if dbdata:
            user = self.bot.get_user(dbdata['user_id'])
            moderate_user = self.bot.get_user(dbdata['moderate_user'])
            guild = self.bot.get_guild(dbdata['create_guild'])
            time_str = dbdata['create_time']
            moderate_type = dbdata['moderate_type']
            last_time = dbdata['last_time']
            if last_time:
                moderate_type += f" {last_time}"
            embed = BotEmbed.general(f'{user.name} 的警告單',user.display_avatar.url,description=f"編號:{warning_id} ({moderate_type})\n被警告用戶：{user.mention}\n管理員：{guild.name}/{moderate_user.mention}\n原因：{dbdata['reason']}\n時間：{time_str}")
            await ctx.respond(embed=embed)
        else:
            await ctx.respond("查無此警告單")

    @warning.command(description='移除用戶警告')
    @commands.has_permissions(kick_members=True)
    @commands.guild_only()
    async def remove(self,ctx,
                     warning_id:discord.Option(str,name='警告編號',description='要移除的警告',required=True)):
        dbdata = sqldb.get_warning(int(warning_id))
        is_owner = await self.bot.is_owner(ctx.author)
        if dbdata:
            guild = self.bot.get_guild(dbdata['create_guild'])
            if not guild == ctx.guild and not is_owner:
                await ctx.respond("不能移除非此伺服器發出的警告")
                return
            sqldb.remove_warning(int(warning_id))
            await ctx.respond(f"已移除編號:{warning_id}的警告")
        else:
            await ctx.respond("查無此警告單")

    @commands.slash_command(description='禁言用戶')
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    @commands.guild_only()
    async def timeout(self,ctx:discord.ApplicationContext,
                      user:discord.Option(discord.Member,name='用戶',description='要禁言的用戶',required=True),
                      time_last:discord.Option(str,name='時長',description='格式為30s、1h20m等，支援天(d)、小時(h)、分鐘(m)、秒(s)',required=True),
                      reason:discord.Option(str,name='原因',description='限100字內',required=False),
                      add_record:discord.Option(bool,name='是否要將此紀錄存入警告系統',description='將紀錄存入警告系統供其他群組檢視',default=False)):
        await ctx.defer()
        time = converter.time_to_datetime(time_last)
        await user.timeout_for(time,reason=reason)
        
        moderate_user = ctx.user.id
        create_time = datetime.datetime.now()
        if add_record and not user.bot:
            sqldb.add_warning(user.id,'timeout',moderate_user,ctx.guild.id,create_time,reason,time_last)
        
        embed = BotEmbed.general(f'{user.name} 已被禁言',user.display_avatar.url,description=f"{user.mention}：{reason}")
        embed.add_field(name="執行人員",value=ctx.author.mention)
        embed.timestamp = create_time
        await ctx.respond(embed=embed)

    @commands.slash_command(description='踢除用戶')
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    @commands.guild_only()
    async def kick(self,ctx:discord.ApplicationContext,
                      user:discord.Option(discord.Member,name='用戶',description='要踢除的用戶',required=True),
                      reason:discord.Option(str,name='原因',description='限100字內',required=False),
                      add_record:discord.Option(bool,name='是否要將此紀錄存入警告系統',description='將紀錄存入警告系統供其他群組檢視',default=False)):
        await ctx.defer()
        await user.kick(reason=reason)
        
        moderate_user = ctx.user.id
        create_time = datetime.datetime.now()
        if add_record and not user.bot:
            sqldb.add_warning(user.id,'kick',moderate_user,ctx.guild.id,create_time,reason,None)
        
        embed = BotEmbed.general(f'{user.name} 已被踢除',user.display_avatar.url,description=f"{user.mention}：{reason}")
        embed.add_field(name="執行人員",value=ctx.author.mention)
        embed.timestamp = create_time
        await ctx.respond(embed=embed)

    @commands.slash_command(description='停權用戶')
    @commands.has_permissions(ban_members=True)
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
        create_time = datetime.datetime.now()
        if add_record and not user.bot:
            sqldb.add_warning(user.id,'ban',moderate_user,ctx.guild.id,create_time,reason,None)
        
        embed = BotEmbed.general(f'{user.name} 已被停權',user.display_avatar.url,description=f"{user.mention}：{reason}")
        embed.add_field(name="執行人員",value=ctx.author.mention)
        embed.timestamp = create_time
        await ctx.respond(embed=embed)

    
def setup(bot):
    bot.add_cog(moderation(bot))