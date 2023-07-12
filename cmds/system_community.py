import discord
from core.classes import Cog_Extension
from discord.commands import SlashCommandGroup
from starcord.clients import TwitchAPI,YoutubeAPI
from starcord import sqldb

class system_community(Cog_Extension):
    twitch = SlashCommandGroup("twitch", "Twitch相關指令")
    youtube = SlashCommandGroup("youtube", "youtube相關指令")
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
        
        user = TwitchAPI().get_user(twitch_user)
        if user:
            sqldb.set_notice_community('twitch',twitch_user,guildid,channelid,roleid)
            if role:
                await ctx.respond(f'設定成功：{user.display_name}({user.login})的開台通知將會發送在{channel.mention}並會通知{role.mention}')
            else:
                await ctx.respond(f'設定成功：{user.display_name}({user.login})的開台通知將會發送在{channel.mention}')
        else:
            await ctx.respond(f'錯誤：找不到用戶{twitch_user}')

    @twitch.command(description='移除twitch開台通知')
    async def remove(self,ctx,twitch_user:discord.Option(str,required=True,name='twitch用戶')):
        sqldb.remove_notice_community('twitch',twitch_user,ctx.guild.id)
        await ctx.respond(f'已移除 {twitch_user} 的開台通知')

    @twitch.command(description='確認twitch開台通知')
    async def notice(self,ctx,twitch_user:discord.Option(str,required=True,name='twitch用戶')):
        guildid = ctx.guild.id
        record = sqldb.get_notice_community_user('twitch',twitch_user,guildid)
        if record:
            channel = self.bot.get_channel(record[0]['channel_id'])
            role = channel.guild.get_role(record[0]['role_id'])
            if role:
                await ctx.respond(f'TwitchID: {twitch_user} 的開台通知在 {channel.mention} 並通知 {role.mention}')
            else:
                await ctx.respond(f'TwitchID: {twitch_user} 的開台通知在 {channel.mention}')
        else:
            await ctx.respond(f'TwitchID: {twitch_user} 在此群組沒有設開台通知')
    
    @twitch.command(description='取得twitch頻道的相關資訊')
    async def user(self,ctx,twitch_username:discord.Option(str,required=True,name='twitch用戶')):
        user = TwitchAPI().get_user(twitch_username)
        if user:
            await ctx.respond(embed=user.desplay())
        else:
            await ctx.respond("查詢失敗",ephemeral=True)

    @youtube.command(description='取得youtube頻道的相關資訊（未完成）')
    async def channel(self,ctx,youtube_username:discord.Option(str,required=True,name='youtube頻道')):
        ytapi = YoutubeAPI()
        channelid = ytapi.get_channel_id(youtube_username)
        if channelid:
            channel = ytapi.get_channel_content(channelid)
        else:
            channel = None
        
        if channel:
            await ctx.respond("查詢成功")
        else:
            await ctx.respond("查詢失敗",ephemeral=True)

def setup(bot):
    bot.add_cog(system_community(bot))
