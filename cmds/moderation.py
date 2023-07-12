import discord,datetime
from discord.ext import commands
from discord.commands import SlashCommandGroup
from core.classes import Cog_Extension
from starcord import ChoiceList,BotEmbed

set_option = ChoiceList.set('channel_set_option')

class moderation(Cog_Extension):
    warning = SlashCommandGroup("warning", "警告相關指令")
    
    @commands.slash_command(description='清理訊息')
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_guild_permissions(manage_messages=True)
    @commands.guild_only()
    async def clean(self,
                    ctx:discord.ApplicationContext,
                    num:discord.Option(int,name='數量',description='要清理的訊息數，與訊息id擇一提供',required=False),
                    message_id:discord.Option(str,name='訊息id',description='如果提供，將刪除比此訊息更新的所有訊息（該訊息不會被刪）',required=False)):
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

    @commands.slash_command(description='設定通知頻道')
    @commands.has_permissions(manage_channels=True)
    @commands.guild_only()
    async def set(self,ctx:discord.ApplicationContext,
                  set_type:discord.Option(str,name='通知類型',description='要接收的通知類型',required=True,choices=set_option),
                  channel:discord.Option(discord.abc.GuildChannel,name='頻道',description='要接收通知的頻道',default=None),
                  role:discord.Option(discord.Role,required=False,name='身分組',description='發送通知時tag的身分組，若為定時通知則不會tag',default=None)):
        guildid = ctx.guild.id
        
        if channel:
            if role:
                roleid = role.id
            else:
                roleid = None
            self.sqldb.set_notice_channel(guildid,set_type,channel.id,roleid)
            await ctx.respond(f'設定完成，已將 {set_type} 頻道設為 {channel.mention}')
            await ctx.send(embed=BotEmbed.simple('溫馨提醒','若為定時通知，請將機器人的訊息保持在此頻道的最新訊息，以免機器人找不到訊息而重複發送'),delete_after=10)
        else:
            self.sqldb.remove_notice_channel(guildid,set_type)
            await ctx.respond(f'設定完成，已移除 {set_type} 頻道')

    @warning.command(description='給予用戶警告，此警告將會連動至其他群組')
    @commands.has_permissions(kick_members=True)
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
        moderate_user = str(ctx.author.id)
        self.sqldb.add_warning(str(user.id),'warning',moderate_user,str(ctx.guild.id),time,reason)
        embed = BotEmbed.general(f'{user.name} 的警告單',user.display_avatar.url,description=f"{user.mention}：{reason}")
        embed.add_field(name="執行人員",value=ctx.author.mention)
        embed.timestamp = time
        await ctx.respond(embed=embed)
    
    @warning.command(description='獲取用戶的所有警告')
    @commands.guild_only()
    async def list(self,ctx,
                      user:discord.Option(discord.User,name='用戶',description='要查詢的用戶',required=True)):
        dbdata = self.sqldb.get_warnings(str(user.id))
        embed = BotEmbed.general(f'{user.name} 的警告單列表（共{len(dbdata)}筆）',user.display_avatar.url)
        for i in dbdata:
            moderate_user = self.bot.get_user(int(i['moderate_user']))
            guild = self.bot.get_guild(int(i['create_guild']))
            time_str = i['create_time']
            embed.add_field(name=f"編號: {i['warning_id']}",value=f"{guild.name}/{moderate_user.mention}\n{i['reason']}\n{time_str}")
        await ctx.respond(embed=embed)

    @warning.command(description='獲取指定警告')
    @commands.guild_only()
    async def get(self,ctx,
                      warning_id:discord.Option(str,name='警告編號',description='要查詢的警告',required=True)):
        dbdata = self.sqldb.get_warning(int(warning_id))
        if dbdata:
            user = self.bot.get_user(int(dbdata['user_id']))
            moderate_user = self.bot.get_user(int(dbdata['moderate_user']))
            guild = self.bot.get_guild(int(dbdata['create_guild']))
            time_str = dbdata['create_time']
            embed = BotEmbed.general(f'警告單',user.display_avatar.url,description=f"編號:{warning_id}\n被警告用戶：{user.mention}\n管理員：{guild.name}/{moderate_user.mention}\n原因：{dbdata['reason']}\n時間：{time_str}")
            await ctx.respond(embed=embed)
        else:
            await ctx.respond("查無此警告單")

    @warning.command(description='移除用戶警告')
    @commands.has_permissions(kick_members=True)
    @commands.guild_only()
    async def remove(self,ctx,
                     warning_id:discord.Option(str,name='警告編號',description='要移除的警告',required=True)):
        dbdata = self.sqldb.get_warning(int(warning_id))
        is_owner = await self.bot.is_owner(ctx.author)
        if dbdata:
            guild = self.bot.get_guild(int(dbdata['create_guild']))
            if not guild == ctx.guild and not is_owner:
                await ctx.respond("不能移除非此伺服器發出的警告")
                return
            self.sqldb.remove_warning(int(warning_id))
            await ctx.respond(f"已移除編號:{warning_id}的警告")
        else:
            await ctx.respond("查無此警告單")

def setup(bot):
    bot.add_cog(moderation(bot))