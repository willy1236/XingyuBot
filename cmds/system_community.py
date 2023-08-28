import discord,datetime
from core.classes import Cog_Extension
from discord.commands import SlashCommandGroup
from starcord.clients import TwitchAPI,YoutubeAPI
from starcord import sqldb,BotEmbed

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
        roleid = role.id if role else None

        user = TwitchAPI().get_user(twitch_user)
        if user:
            sqldb.set_notice_community('twitch',twitch_user,guildid,channelid,roleid)
            if role:
                await ctx.respond(f'設定成功：{user.display_name}({user.login})的開台通知將會發送在{channel.mention}並會通知{role.mention}')
            else:
                await ctx.respond(f'設定成功：{user.display_name}({user.login})的開台通知將會發送在{channel.mention}')
                
            from .task import scheduler,update_channel_dict_list
            time = datetime.datetime.now() + datetime.timedelta(seconds=1)
            scheduler.add_job(update_channel_dict_list,"date",run_date=time,args=["twitch"])
        else:
            await ctx.respond(f'錯誤：找不到用戶{twitch_user}')

    @twitch.command(description='移除twitch開台通知')
    async def remove(self,ctx,twitch_user:discord.Option(str,required=True,name='twitch用戶')):
        guildid = ctx.guild.id
        sqldb.remove_notice_community('twitch',twitch_user,guildid)
        await ctx.respond(f'已移除 {twitch_user} 的開台通知')
        
        from .task import scheduler,update_channel_dict_list
        time = datetime.datetime.now() + datetime.timedelta(seconds=1)
        scheduler.add_job(update_channel_dict_list,"date",run_date=time,args=["twitch"])

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
    
    @twitch.command(description='確認群組內所有的twitch開台通知')
    async def list(self,ctx):
        guildid = ctx.guild.id
        embed = BotEmbed.general("twitch開台通知",ctx.guild.icon.url if ctx.guild.icon else discord.Embed.Empty)
        dbdata = sqldb.get_notice_community_list('twitch',guildid)
        for data in dbdata:
            notice_name = data['notice_name']
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
            embed.add_field(name=notice_name, value=text)
        await ctx.respond(embed=embed)

    @twitch.command(description='取得twitch頻道的相關資訊')
    async def user(self,ctx,twitch_username:discord.Option(str,required=True,name='twitch用戶')):
        user = TwitchAPI().get_user(twitch_username)
        if user:
            await ctx.respond(embed=user.desplay())
        else:
            await ctx.respond(f"查詢不到用戶：{twitch_username}",ephemeral=True)

    @youtube.command(description='取得youtube頻道的相關資訊')
    async def channel(self,ctx,youtube_id:discord.Option(str,required=True,name='youtube頻道id')):
        ytapi = YoutubeAPI()
        channel = ytapi.get_channel_content(youtube_id)
        if channel:
            await ctx.respond("查詢成功",embed=channel.desplay())
        else:
            await ctx.respond("查詢失敗",ephemeral=True)

def setup(bot):
    bot.add_cog(system_community(bot))
