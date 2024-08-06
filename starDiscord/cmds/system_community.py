from datetime import datetime

import discord
from discord.commands import SlashCommandGroup
from discord.ext import commands

from starlib import BotEmbed, ChoiceList, Jsondb, sclient, tz
from starlib.dataExtractor import TwitchAPI, YoutubeAPI, YoutubeRSS
from starlib.types import NotifyCommunityType
from starlib.uiElement.view import ReactionRole1, WelcomeView

from ..extension import Cog_Extension

twitch_notify_option = ChoiceList.set("twitch_notify_option")

class system_community(Cog_Extension):
    twitch = SlashCommandGroup("twitch", "Twitch相關指令")
    youtube = SlashCommandGroup("youtube", "youtube相關指令")
    
    @twitch.command(description='設置twitch開台通知')
    async def set(self,ctx,
                  notify_type:discord.Option(int,required=True,name='通知種類',description='通知種類',choices=twitch_notify_option),
                  twitch_user:discord.Option(str,required=True,name='twitch用戶',description='當此用戶開台時會發送通知'),
                  channel:discord.Option(discord.TextChannel,required=True,name='頻道',description='通知發送頻道'),
                  role:discord.Option(discord.Role,required=False,default=None,name='身分組',description='發送通知時tag的身分組')):
        await ctx.defer()
        guildid = ctx.guild.id
        channelid = channel.id
        roleid = role.id if role else None
        type = NotifyCommunityType(notify_type)
        api = TwitchAPI()

        user = api.get_user(twitch_user)
        type_tw = ChoiceList.get_tw(type.value, "twitch_notify_option")
        if user:
            sclient.sqldb.add_notify_community(type.value, user.id, guildid, channelid, roleid, user.login)
            match type:
                case NotifyCommunityType.Twitch:
                    pass
            
                case NotifyCommunityType.TwitchVideo:
                    Jsondb.cache.add_dict_data("twitch_v", user.id, datetime.now(tz=tz).isoformat(timespec="seconds"))
                
                case NotifyCommunityType.TwitchClip:
                    Jsondb.cache.add_dict_data("twitch_c", user.id, datetime.now(tz=tz).isoformat(timespec="seconds"))
            
            sclient.cache.update_notify_community(type)

            if role:
                await ctx.respond(f'設定成功：{user.display_name}({user.login})的{type_tw}將會發送在{channel.mention}並會通知{role.mention}')
            else:
                await ctx.respond(f'設定成功：{user.display_name}({user.login})的{type_tw}將會發送在{channel.mention}')

        else:
            await ctx.respond(f'錯誤：找不到用戶{twitch_user}')
    
    @twitch.command(description='移除twitch開台通知')
    async def remove(self,ctx,
                     twitch_user:discord.Option(str,required=True,name='twitch用戶'),
                     notify_type:discord.Option(int,required=False,name='通知種類',description='通知種類，留空為移除全部',choices=twitch_notify_option,default=None)):
        guildid = ctx.guild.id
        user = TwitchAPI().get_user(twitch_user)
        if not notify_type or notify_type == NotifyCommunityType.Twitch:
            sclient.sqldb.remove_notify_community(NotifyCommunityType.Twitch.value, user.id, guildid)
            Jsondb.cache.remove_dict_data("twitch", user.id)
        
        if not notify_type or notify_type == NotifyCommunityType.TwitchVideo:
            sclient.sqldb.remove_notify_community(NotifyCommunityType.TwitchVideo.value, user.id, guildid)
            Jsondb.cache.remove_dict_data("twitch_v", user.id)

        if not notify_type or notify_type == NotifyCommunityType.TwitchClip:
            sclient.sqldb.remove_notify_community(NotifyCommunityType.TwitchClip.value, user.id, guildid)
            Jsondb.cache.remove_dict_data("twitch_c", user.id)
        
        if notify_type:
            await ctx.respond(f'已移除 {user.display_name}({user.login}) 的通知')
        else:
            await ctx.respond(f'已移除 {user.display_name}({user.login}) 的所有通知')
        
        sclient.cache.update_notify_community()

    @twitch.command(description='確認twitch開台通知')
    async def notify(self,ctx,twitch_user:discord.Option(str,required=True,name='twitch用戶')):
        guildid = ctx.guild.id
        record = sclient.sqldb.get_notify_community_user(NotifyCommunityType.Twitch, twitch_user, guildid)
        if record:
            channel = self.bot.get_channel(record[0].channel_id)
            role = channel.guild.get_role(record[0].role_id)
            if role:
                await ctx.respond(f'Twitch名稱: {twitch_user} 的開台通知在 {channel.mention} 並通知 {role.mention}')
            else:
                await ctx.respond(f'Twitch名稱: {twitch_user} 的開台通知在 {channel.mention}')
        else:
            await ctx.respond(f'Twitch名稱: {twitch_user} 在此群組沒有設開台通知')
    
    @twitch.command(description='確認群組內所有的twitch通知')
    async def list(self,ctx:discord.ApplicationContext):
        guildid = ctx.guild.id
        embed = BotEmbed.general("twitch開台通知", ctx.guild.icon.url if ctx.guild.icon else None)
        dbdata = sclient.sqldb.get_notify_community_list(NotifyCommunityType.Twitch,guildid) + sclient.sqldb.get_notify_community_list(NotifyCommunityType.TwitchVideo,guildid) + sclient.sqldb.get_notify_community_list(NotifyCommunityType.TwitchClip,guildid)
        for data in dbdata:
            display_name = data.display_name or data.notify_name
            channel_id = data.channel_id
            role_id = data.role_id
            notify_type = data.notify_type
            
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
    async def user(self,ctx,twitch_username:discord.Option(str,required=True,name='twitch用戶')):
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
                  channel:discord.Option(discord.TextChannel,required=True,name='頻道',description='通知發送頻道'),
                  role:discord.Option(discord.Role,required=False,default=None,name='身分組',description='發送通知時tag的身分組')):
        guildid = ctx.guild.id
        channelid = channel.id
        roleid = role.id if role else None

        ytchannel = YoutubeAPI().get_channel(handle=ythandle)
        if ytchannel:
            sclient.sqldb.add_notify_community(NotifyCommunityType.Youtube,ytchannel.id,guildid,channelid,roleid,ytchannel.snippet.title)
            if role:
                await ctx.respond(f'設定成功：{ytchannel.title}的通知將會發送在{channel.mention}並會通知{role.mention}')
            else:
                await ctx.respond(f'設定成功：{ytchannel.title}的通知將會發送在{channel.mention}')
                
            sclient.cache.update_notify_community(NotifyCommunityType.Youtube)

            feed = YoutubeRSS().get_videos(ytchannel.id)
            updated_at = feed[0].updated_at.isoformat() if feed else None
            cache = Jsondb.cache.get("youtube")
            cache[ytchannel.id] = updated_at
            Jsondb.cache.write('youtube',cache)
        else:
            await ctx.respond(f'錯誤：找不到帳號代碼 {ythandle} 的頻道')

    @youtube.command(description='移除youtube通知')
    async def remove(self,ctx,ythandle:discord.Option(str,required=True,name='youtube帳號代碼',description="youtube頻道中以@開頭的代號")):
        guildid = ctx.guild.id

        ytchannel = YoutubeAPI().get_channel(handle=ythandle)
        if not ytchannel:
            await ctx.respond(f'錯誤：找不到帳號代碼 {ythandle} 的頻道')
            return

        sclient.sqldb.remove_notify_community(NotifyCommunityType.Youtube,ytchannel.id,guildid)
        await ctx.respond(f'已移除頻道 {ytchannel.title} 的通知')
        
        sclient.cache.update_notify_community(NotifyCommunityType.Youtube)

        cache = Jsondb.cache.get("youtube")
        del cache[ytchannel.id]
        Jsondb.cache.write('youtube',cache)

    @youtube.command(description='確認youtube通知')
    async def notify(self,ctx,ythandle:discord.Option(str,required=True,name='youtube帳號代碼',description="youtube頻道中以@開頭的代號")):
        guildid = ctx.guild.id
        
        ytchannel = YoutubeAPI().get_channel(handle=ythandle)
        if not ytchannel:
            await ctx.respond(f'錯誤：找不到帳號代碼 {ythandle} 的頻道')
            return
        
        record = sclient.sqldb.get_notify_community_user(NotifyCommunityType.Youtube,ytchannel.id,guildid)
        if record:
            channel = self.bot.get_channel(record[0].channel_id)
            role = channel.guild.get_role(record[0].role_id)
            if role:
                await ctx.respond(f'Youtube頻道: {ytchannel.title} 的通知在 {channel.mention} 並通知 {role.mention}')
            else:
                await ctx.respond(f'Youtube頻道: {ytchannel.title} 的通知在 {channel.mention}')
        else:
            await ctx.respond(f'Youtube頻道: {ytchannel.title} 在此群組沒有設通知')
    
    @youtube.command(description='確認群組內所有的youtube通知')
    async def list(self,ctx):
        guildid = ctx.guild.id
        embed = BotEmbed.general("youtube通知",ctx.guild.icon.url if ctx.guild.icon else None)
        dbdata = sclient.sqldb.get_notify_community_list(NotifyCommunityType.Youtube, guildid)
        for data in dbdata:
            notify_name = data.display_name or data.notify_name
            channel_id = data.channel_id
            role_id = data.role_id
            
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

    @commands.slash_command(description='加入伺服器按鈕',debug_guilds=[1058234922076217415])
    @commands.has_permissions(manage_channels=True)
    async def welcome(self, ctx):
        view = WelcomeView()
        await ctx.channel.send(view=view)
        await ctx.respond("按鈕創建完成",ephemeral=True)

    @commands.slash_command(description='反應身分組按鈕',debug_guilds=[1058234922076217415])
    @commands.has_permissions(manage_channels=True)
    async def reactionrole(self, ctx):
        view = ReactionRole1()
        await ctx.channel.send("請依自身喜好點選身分組",view=view)
        await ctx.respond("按鈕創建完成",ephemeral=True)

def setup(bot):
    bot.add_cog(system_community(bot))
