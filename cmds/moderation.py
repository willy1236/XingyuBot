import discord
from discord.ext import commands
from core.classes import Cog_Extension
from BotLib.funtions import find
from BotLib.database import Database

jdict = Database().jdict
option = []
for i in jdict['channel_set_option']:
    option.append(discord.OptionChoice(name=i,value=jdict['channel_set_option'][i]))

class moderation(Cog_Extension):
    cdata = Database().cdata
    
    @commands.slash_command(description='清理訊息',guild_ids=[566533708371329024])
    @commands.has_permissions(manage_messages=True)
    async def clean(self,ctx,num:discord.Option(int,name='數量',description='要清理的訊息數',required=True)):
        await ctx.channel.purge(limit=num+1)
        await ctx.respond(content=f'清除完成，清除了{num}則訊息',delete_after=5)

    @commands.slash_command(description='設定通知頻道',guild_ids=[566533708371329024])
    @commands.has_permissions(manage_channels=True)
    async def set(  self,
                    ctx,
                    set_type:discord.Option(str,name='通知類型',description='要接收的通知類型',required=True,choices=option),
                    channel:discord.Option(discord.abc.GuildChannel,name='頻道',description='要接收通知的頻道',default=None)
                ):
        guild = str(ctx.guild.id)
        if set_type not in self.cdata:
            self.cdata[set_type]={}
        
        if channel:
            self.cdata[set_type][guild] = channel.id
            Database().write('cdata',self.cdata)
            await ctx.respond(f'設定完成，已將{set_type}頻道設為{channel.mention}')
        else:
            if guild in self.cdata[set_type]:
                del self.cdata[set_type][guild]
                Database().write('cdata',self.cdata)
                await ctx.respond(f'設定完成，已移除{set_type}頻道')
            else:
                await ctx.respond('此伺服器還沒有設定頻道喔')

def setup(bot):
    bot.add_cog(moderation(bot))