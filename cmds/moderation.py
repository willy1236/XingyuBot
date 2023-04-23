import discord
from discord.ext import commands
from core.classes import Cog_Extension
from bothelper import Jsondb

jdict = Jsondb.jdict
option = []
for name,value in jdict['channel_set_option'].items():
    option.append(discord.OptionChoice(name=name,value=value))

class moderation(Cog_Extension):
    @commands.slash_command(description='清理訊息')
    @commands.has_permissions(manage_messages=True)
    async def clean(self,
                    ctx:discord.ApplicationContext,
                    num:discord.Option(int,name='數量',description='要清理的訊息數，與訊息id擇一提供',required=False),
                    message_id:discord.Option(str,name='訊息id',description='如果提供，將刪除比此訊息更新的所有訊息',required=False)):
        if message_id:
            message = await ctx.channel.fetch_message(int(message_id))
            if message:
                time = message.created_at
                await ctx.channel.purge(after=time)
                await ctx.respond(content=f'清除完成',delete_after=5)
            return

        if num:
            await ctx.channel.purge(limit=num)
            await ctx.respond(content=f'清除完成，清除了{num}則訊息',delete_after=5)
        else:
            await ctx.respond(content=f'沒有提供任何訊息，所以沒有清除任何內容',delete_after=5)

    @commands.slash_command(description='設定通知頻道')
    @commands.has_permissions(manage_channels=True)
    async def set(self,ctx:discord.ApplicationContext,
                  set_type:discord.Option(str,name='通知類型',description='要接收的通知類型',required=True,choices=option),
                  channel:discord.Option(discord.abc.GuildChannel,name='頻道',description='要接收通知的頻道',default=None),
                  role:discord.Option(discord.Role,required=False,name='身分組',description='發送通知時tag的身分組',default=None)):
        guildid = ctx.guild.id
        
        if channel:
            if role:
                roleid = role.id
            else:
                roleid = None
            self.sqldb.set_notice_channel(guildid,set_type,channel.id,roleid)
            await ctx.respond(f'設定完成，已將{set_type}頻道設為{channel.mention}')
        else:
            self.sqldb.remove_notice_channel(guildid,set_type)
            await ctx.respond(f'設定完成，已移除{set_type}頻道')
            #await ctx.respond('此伺服器還沒有設定頻道喔')

def setup(bot):
    bot.add_cog(moderation(bot))