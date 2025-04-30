from datetime import datetime

import discord
from discord.commands import SlashCommandGroup
from tweepy.errors import TooManyRequests

from starlib import BotEmbed, ChoiceList, Jsondb, sclient, tz
from starlib.dataExtractor import TwitchAPI, YoutubeAPI, YoutubeRSS
from starlib.models.mysql import Community
from starlib.types import CommunityType, JsonCacheType, NotifyCommunityType
from starlib.instance import twitter_api

from ..extension import Cog_Extension

twitch_notify_option = ChoiceList.set("twitch_notify_option")

class system_community(Cog_Extension):
    twitch = SlashCommandGroup("twitch", "Twitch相關指令")
    youtube = SlashCommandGroup("youtube", "youtube相關指令")
    twitter = SlashCommandGroup("twitter", "twitter相關指令")
    
    @twitch.command(description='設置twitch開台通知')
    async def set(self,ctx,
                  notify_type:discord.Option(int, required=True, name='通知種類',description='通知種類',choices=twitch_notify_option),
                  twitch_user:discord.Option(str, required=True, name='twitch用戶', description='使用者名稱，當此用戶開台時會發送通知'),
                  channel:discord.Option(discord.TextChannel, required=True, name='頻道', description='通知將會發送到此頻道'),
                  role:discord.Option(discord.Role, default=None, name='身分組', description='發送通知時tag的身分組，若無則不會tag'),
                  msg:discord.Option(str,default=None,name='通知文字',description='發送通知時的自訂文字')):
        await ctx.defer()
        guildid = ctx.guild.id
        channelid = channel.id
        roleid = role.id if role else None
        type = NotifyCommunityType(notify_type)
        api = TwitchAPI()

        user = api.get_user(twitch_user)
        type_tw = Jsondb.get_tw(type.value, "twitch_notify_option")
        if user:
            sclient.sqldb.add_notify_community(type, user.id, CommunityType.Twitch, guildid, channelid, roleid, msg)
            sclient.sqldb.merge(Community(id=user.id, type=CommunityType.Twitch, name=user.display_name, login=user.login))
            match type:
                case NotifyCommunityType.TwitchLive:
                    pass
            
                case NotifyCommunityType.TwitchVideo:
                    Jsondb.set_cache(JsonCacheType.TwitchVideo, user.id, datetime.now(tz=tz).isoformat(timespec="seconds"))
                
                case NotifyCommunityType.TwitchClip:
                    Jsondb.set_cache(JsonCacheType.TwitchClip, user.id, datetime.now(tz=tz).isoformat(timespec="seconds"))

            if role:
                await ctx.respond(f'設定成功：{user.display_name}({user.login})的{type_tw}將會發送在{channel.mention}並會通知{role.mention}')
            else:
                await ctx.respond(f'設定成功：{user.display_name}({user.login})的{type_tw}將會發送在{channel.mention}')
            
            if not channel.can_send():
                await ctx.send(embed=BotEmbed.simple('溫馨提醒',f'我無法在{channel.mention}中發送訊息，請確認我有足夠的權限'))

        else:
            await ctx.respond(f'錯誤：找不到用戶 {twitch_user}')
    
    @twitch.command(description='移除twitch開台通知')
    async def remove(self,ctx,
                     twitch_user_login:discord.Option(str, required=True, name='twitch用戶', description='使用者名稱'),
                     notify_type:discord.Option(int, required=False, name='通知種類', description='要移除的通知種類，留空為移除全部',choices=twitch_notify_option,default=None)):
        guildid = ctx.guild.id
        twitch_user = TwitchAPI().get_user(twitch_user_login)
        if not notify_type or notify_type == NotifyCommunityType.TwitchLive:
            sclient.sqldb.remove_notify_community(NotifyCommunityType.TwitchLive, twitch_user.id, guildid)
            if not sclient.sqldb.get_notify_community_count(NotifyCommunityType.TwitchLive, twitch_user.id):
                Jsondb.remove_cache(JsonCacheType.TwitchLive, twitch_user.id)
        
        if not notify_type or notify_type == NotifyCommunityType.TwitchVideo:
            sclient.sqldb.remove_notify_community(NotifyCommunityType.TwitchVideo, twitch_user.id, guildid)
            if not sclient.sqldb.get_notify_community_count(NotifyCommunityType.TwitchVideo, twitch_user.id):
                Jsondb.remove_cache(JsonCacheType.TwitchVideo, twitch_user.id)

        if not notify_type or notify_type == NotifyCommunityType.TwitchClip:
            sclient.sqldb.remove_notify_community(NotifyCommunityType.TwitchClip, twitch_user.id, guildid)
            if not sclient.sqldb.get_notify_community_count(NotifyCommunityType.TwitchClip, twitch_user.id):
                Jsondb.remove_cache(JsonCacheType.TwitchClip, twitch_user.id)
        
        if notify_type:
            await ctx.respond(f'已移除 {twitch_user.display_name}({twitch_user.login}) 的通知')
        else:
            await ctx.respond(f'已移除 {twitch_user.display_name}({twitch_user.login}) 的所有通知')
        
        sclient.sqldb.update_notify_community()

    @twitch.command(description='確認twitch開台通知')
    async def notify(self,ctx,twitch_user_login:discord.Option(str, required=True, name='twitch用戶', description='使用者名稱')):
        guildid = ctx.guild.id
        record = sclient.sqldb.get_notify_community_user_bylogin(NotifyCommunityType.TwitchLive, twitch_user_login, guildid)
        if record:
            channel = self.bot.get_channel(record.channel_id)
            role = channel.guild.get_role(record.role_id)
            if role:
                await ctx.respond(f'Twitch名稱: {twitch_user_login} 的開台通知在 {channel.mention} 並通知 {role.mention}')
            else:
                await ctx.respond(f'Twitch名稱: {twitch_user_login} 的開台通知在 {channel.mention}')
        else:
            await ctx.respond(f'Twitch名稱: {twitch_user_login} 在此群組沒有設開台通知')
    
    @twitch.command(description='確認群組內所有的twitch通知')
    async def list(self,ctx:discord.ApplicationContext):
        guildid = ctx.guild.id
        embed = BotEmbed.general("twitch開台通知", ctx.guild.icon.url if ctx.guild.icon else None)
        dbdata = sclient.sqldb.get_notify_community_list(NotifyCommunityType.TwitchLive,guildid) + sclient.sqldb.get_notify_community_list(NotifyCommunityType.TwitchVideo,guildid) + sclient.sqldb.get_notify_community_list(NotifyCommunityType.TwitchClip,guildid)
        for notify_data, community_data in dbdata:
            display_name = f"{community_data.name}（{community_data.login}）"
            channel_id = notify_data.channel_id
            role_id = notify_data.role_id
            notify_type = notify_data.notify_type
            
            if notify_type == NotifyCommunityType.TwitchVideo:
                display_name += "（影片）"

            if notify_type == NotifyCommunityType.TwitchClip:
                display_name += "（剪輯）"

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
            embed.add_field(name=display_name, value=text)
        await ctx.respond(embed=embed)

    @twitch.command(description='取得twitch頻道的相關資訊')
    async def user(self,ctx,twitch_username:discord.Option(str, required=True, name='twitch用戶', description='使用者名稱')):
        user = TwitchAPI().get_user(twitch_username)
        if user:
            await ctx.respond(embed=user.desplay())
        else:
            await ctx.respond(f"查詢不到用戶：{twitch_username}",ephemeral=True)

    @youtube.command(description='取得youtube頻道的相關資訊')
    async def channel(self,ctx,youtube_handle:discord.Option(str,required=True,name='youtube帳號代碼',description="youtube頻道中以@開頭的代號")):
        ytapi = YoutubeAPI()
        channel = ytapi.get_channel(handle=youtube_handle)
        if channel:
            await ctx.respond("查詢成功",embed=channel.embed())
        else:
            await ctx.respond("查詢失敗",ephemeral=True)

    @youtube.command(description='設置youtube開台通知')
    async def set(self,ctx,
                  ythandle:discord.Option(str,required=True,name='youtube帳號代碼',description="youtube頻道中以@開頭的代號"),
                  channel:discord.Option(discord.TextChannel,required=True,name='頻道',description='通知將會發送到此頻道'),
                  role:discord.Option(discord.Role,required=False,default=None,name='身分組',description='發送通知時tag的身分組'),
                  msg:discord.Option(str,default=None,name='通知文字',description='發送通知時的自訂文字')):
        guildid = ctx.guild.id
        channelid = channel.id
        roleid = role.id if role else None

        ytchannel = YoutubeAPI().get_channel(handle=ythandle)
        if ytchannel:
            sclient.sqldb.add_notify_community(NotifyCommunityType.Youtube, ytchannel.id, CommunityType.Youtube, guildid, channelid, roleid, msg)
            sclient.sqldb.merge(Community(id=ytchannel.id, type=CommunityType.Youtube, name=ytchannel.snippet.title))
            if role:
                await ctx.respond(f'設定成功：{ytchannel.snippet.title}的通知將會發送在{channel.mention}並會通知{role.mention}')
            else:
                await ctx.respond(f'設定成功：{ytchannel.snippet.title}的通知將會發送在{channel.mention}')

            feed = YoutubeRSS().get_videos(ytchannel.id)
            updated_at = feed[0].updated_at.isoformat() if feed else datetime.now(tz=tz).isoformat(timespec="seconds")
            Jsondb.set_cache(JsonCacheType.YoutubeVideo, ytchannel.id, updated_at)
            
            if not channel.can_send():
                await ctx.send(embed=BotEmbed.simple('溫馨提醒',f'我無法在{channel.mention}中發送訊息，請確認我有足夠的權限'))
        else:
            await ctx.respond(f'錯誤：找不到帳號代碼 {ythandle} 的頻道')

    @youtube.command(description='移除youtube通知')
    async def remove(self,ctx,ythandle:discord.Option(str,required=True,name='youtube帳號代碼',description="youtube頻道中以@開頭的代號")):
        guildid = ctx.guild.id

        ytchannel = YoutubeAPI().get_channel(handle=ythandle)
        if not ytchannel:
            await ctx.respond(f'錯誤：找不到帳號代碼 {ythandle} 的頻道')
            return

        sclient.sqldb.remove_notify_community(NotifyCommunityType.Youtube, ytchannel.id, guildid)
        await ctx.respond(f'已移除頻道 {ytchannel.snippet.title} 的通知')
        
        sclient.sqldb.update_notify_community(NotifyCommunityType.Youtube)

        if not sclient.sqldb.get_notify_community_count(NotifyCommunityType.Youtube, ytchannel.id):
            Jsondb.remove_cache(JsonCacheType.YoutubeVideo, ytchannel.id)

    @youtube.command(description='確認youtube通知')
    async def notify(self,ctx,ythandle:discord.Option(str,required=True,name='youtube帳號代碼',description="youtube頻道中以@開頭的代號")):
        guildid = ctx.guild.id
        
        ytchannel = YoutubeAPI().get_channel(handle=ythandle)
        if not ytchannel:
            await ctx.respond(f'錯誤：找不到帳號代碼 {ythandle} 的頻道')
            return
        
        record = sclient.sqldb.get_notify_community_user_byid(NotifyCommunityType.Youtube,ytchannel.id,guildid)
        if record:
            channel = self.bot.get_channel(record.channel_id)
            role = channel.guild.get_role(record.role_id)
            if role:
                await ctx.respond(f'Youtube頻道: {ytchannel.snippet.title} 的通知在 {channel.mention} 並通知 {role.mention}')
            else:
                await ctx.respond(f'Youtube頻道: {ytchannel.snippet.title} 的通知在 {channel.mention}')
        else:
            await ctx.respond(f'Youtube頻道: {ytchannel.snippet.title} 在此群組沒有設通知')
    
    @youtube.command(description='確認群組內所有的youtube通知')
    async def list(self,ctx):
        guildid = ctx.guild.id
        embed = BotEmbed.general("youtube通知",ctx.guild.icon.url if ctx.guild.icon else None)
        dbdata = sclient.sqldb.get_notify_community_list(NotifyCommunityType.Youtube, guildid)
        for notify_data, community_data in dbdata:
            notify_name = community_data.name
            channel_id = notify_data.channel_id
            role_id = notify_data.role_id
            
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
            embed.add_field(name=notify_name, value=text)
        await ctx.respond(embed=embed)

    @twitter.command(description='設置x/twitter通知（測試中，目前尚不穩定）')
    async def set(self,ctx,
                  twitter_user:discord.Option(str,required=True,name='twitter用戶',description='使用者名稱，當此用戶發文時會發送通知'),
                  channel:discord.Option(discord.TextChannel,required=True,name='頻道',description='通知將會發送到此頻道'),
                  role:discord.Option(discord.Role,required=False,default=None,name='身分組',description='發送通知時tag的身分組')):
        guildid = ctx.guild.id
        channelid = channel.id
        roleid = role.id if role else None
        try:
            api_twitter_user = twitter_api.get_user(username=twitter_user)
        except TooManyRequests:
            await ctx.respond(f'錯誤：查詢過於頻繁，請稍後再試\n（X/Twitter僅提供少少的次數故容易觸發）')
            return
        
        #! api不支援id查詢 故使用username查詢
        sclient.sqldb.add_notify_community(NotifyCommunityType.TwitterTweet, api_twitter_user.data.username, CommunityType.Twitter, guildid, channelid, roleid, None)
        sclient.sqldb.merge(Community(id=str(api_twitter_user.data.id), type=CommunityType.Twitter, name=api_twitter_user.data.name, login=api_twitter_user.data.username))
        if role:
            await ctx.respond(f'設定成功：{api_twitter_user.data.name}的通知將會發送在{channel.mention}並會通知{role.mention}')
        else:
            await ctx.respond(f'設定成功：{api_twitter_user.data.name}的通知將會發送在{channel.mention}')        

        time_str = datetime.now(tz).isoformat()
        Jsondb.set_cache(JsonCacheType.TwitterTweet, api_twitter_user.data.username, time_str)

        if not channel.can_send():
            await ctx.send(embed=BotEmbed.simple('溫馨提醒',f'我無法在{channel.mention}中發送訊息，請確認我有足夠的權限'))

    @twitter.command(description='移除x/twitter通知')
    async def remove(self,ctx,twitter_user:discord.Option(str,required=True,name='twitter用戶',description='使用者名稱')):
        guildid = ctx.guild.id
        sclient.sqldb.remove_notify_community(NotifyCommunityType.TwitterTweet, twitter_user, guildid)
        await ctx.respond(f'已移除 {twitter_user} 的通知')
        
        sclient.sqldb.update_notify_community(NotifyCommunityType.TwitterTweet)

        if not sclient.sqldb.get_notify_community_count(NotifyCommunityType.TwitterTweet, twitter_user):
            Jsondb.remove_cache(JsonCacheType.TwitterTweet, twitter_user)

    @twitter.command(description='確認x/twitter通知')
    async def notify(self,ctx,twitter_user:discord.Option(str,required=True,name='twitter用戶',description='使用者名稱')):
        guildid = ctx.guild.id
        record = sclient.sqldb.get_notify_community_user_bylogin(NotifyCommunityType.TwitterTweet, twitter_user, guildid)
        if record:
            channel = self.bot.get_channel(record.channel_id)
            role = channel.guild.get_role(record.role_id)
            if role:
                await ctx.respond(f'X/Twitter名稱: {twitter_user} 的通知在 {channel.mention} 並通知 {role.mention}')
            else:
                await ctx.respond(f'X/Twitter名稱: {twitter_user} 的通知在 {channel.mention}')
        else:
            await ctx.respond(f'X/Twitter名稱: {twitter_user} 在此群組沒有設通知')

def setup(bot):
    bot.add_cog(system_community(bot))
