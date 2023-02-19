import discord
from core.classes import Cog_Extension
from discord.ext import commands
from discord.commands import SlashCommandGroup
from bothelper.interface.community import Twitch

class system_community(Cog_Extension):
    twitch = SlashCommandGroup("twitch", "Twitch相關指令")
    
    @twitch.command(description='設置twitch開台通知')
    async def set(self,ctx,
                  twitch_user:discord.Option(str,required=True,name='twitch用戶',description='當此用戶開台時會發送通知'),
                  channel:discord.Option(discord.TextChannel,required=True,name='頻道',description='通知發送頻道'),
                  role:discord.Option(discord.Role,required=False,default=None,name='身分組',description='發送通知時tag的身分組')):
        guildid = ctx.guild.id
        channelid = channel.id
        if role:
            roleid = role.id
        else:
            roleid = None
        
        user = Twitch().get_user(twitch_user)
        if user:
            self.sqldb.set_notice_community('twitch',twitch_user,guildid,channelid,roleid)
            if role:
                await ctx.respond(f'設定成功：{user.display_name}({user.login})的開台通知將會發送在{channel.mention}並會通知{role.mention}')
            else:
                await ctx.respond(f'設定成功：{user.display_name}({user.login})的開台通知將會發送在{channel.mention}')
        else:
            await ctx.respond(f'錯誤：找不到用戶{twitch_user}')

    @twitch.command(description='移除twitch開台通知')
    async def remove(self,ctx,twitch_user:discord.Option(str,required=True,name='twitch用戶')):
        guildid = ctx.guild.id
        
        self.sqldb.remove_notice_community('twitch',twitch_user,guildid)
        await ctx.respond(f'已移除 {twitch_user} 的開台通知')
        #await ctx.respond(f'{twitch_user} 還沒有被設定通知')

    @twitch.command(description='確認twitch開台通知')
    async def notice(self,ctx,twitch_user:discord.Option(str,required=True,name='twitch用戶')):
        guildid = ctx.guild.id
        
        record = self.sqldb.get_notice_community_user('twitch',twitch_user,guildid)
        if record:
            channel = self.bot.get_channel(record[0]['channel_id'])
            await ctx.respond(f'TwitchID: {twitch_user} 的開台通知在 {channel.mention}')
        else:
            await ctx.respond(f'TwitchID: {twitch_user} 在此群組沒有設開台通知')

def setup(bot):
    bot.add_cog(system_community(bot))
