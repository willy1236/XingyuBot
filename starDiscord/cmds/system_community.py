import asyncio
from datetime import datetime

import discord
from discord.commands import SlashCommandGroup
from tweepy.errors import TooManyRequests

from starlib import BotEmbed, ChoiceList, Jsondb, sclient, tz
from starlib.instance import cli_api, tw_api, twitter_api, yt_api, yt_push
from starlib.models.mysql import Community
from starlib.types import APIType, CommunityType, NotifyCommunityType

from ..extension import Cog_Extension

twitch_notify_option = ChoiceList.set("twitch_notify_option")


class system_community(Cog_Extension):
    twitch = SlashCommandGroup("twitch", "Twitch相關指令")
    youtube = SlashCommandGroup("youtube", "youtube相關指令")
    twitter = SlashCommandGroup("twitter", "twitter相關指令")

    @twitch.command(name="set", description="設置twitch開台通知")
    async def twitch_set(
        self,
        ctx,
        notify_type: discord.Option(int, required=True, name="通知種類", description="通知種類", choices=twitch_notify_option),
        twitch_user_login: discord.Option(str, required=True, name="twitch使用者名稱", description="英文的使用者名稱，當此用戶開台時會發送通知"),
        channel: discord.Option(discord.TextChannel, required=True, name="頻道", description="通知將會發送到此頻道"),
        role: discord.Option(discord.Role, default=None, name="身分組", description="發送通知時tag的身分組，若無則不會tag"),
        msg: discord.Option(str, default=None, name="通知文字", description="發送通知時的自訂文字"),
    ):
        await ctx.defer()
        guildid = ctx.guild.id
        channelid = channel.id
        roleid = role.id if role else None
        type = NotifyCommunityType(notify_type)

        twitch_user = tw_api.get_user(twitch_user_login)
        if twitch_user:
            sclient.sqldb.add_notify_community(type, twitch_user.id, guildid, channelid, roleid, msg, cache_time=datetime.now(tz=tz))
            sclient.sqldb.merge(Community(id=twitch_user.id, type=CommunityType.Twitch, display_name=twitch_user.display_name, username=twitch_user.login))

            type_tw = Jsondb.get_tw(type.value, "twitch_notify_option")
            if role:
                await ctx.respond(f"設定成功：{twitch_user.display_name}({twitch_user.login})的{type_tw}將會發送在{channel.mention}並會通知{role.mention}")
            else:
                await ctx.respond(f"設定成功：{twitch_user.display_name}({twitch_user.login})的{type_tw}將會發送在{channel.mention}")

            if not channel.can_send():
                await ctx.send(embed=BotEmbed.simple("溫馨提醒", f"我無法在{channel.mention}中發送訊息，請確認我有足夠的權限"))

        else:
            await ctx.respond(f"錯誤：找不到用戶 {twitch_user_login}")

    @twitch.command(name="remove", description="移除twitch開台通知")
    async def twitch_remove(
        self,
        ctx,
        twitch_user_login: discord.Option(str, required=True, name="twitch使用者名稱", description="英文的使用者名稱"),
        notify_type: discord.Option(
            int, required=False, name="通知種類", description="要移除的通知種類，留空為移除全部", choices=twitch_notify_option, default=None
        ),
    ):
        guildid = ctx.guild.id
        twitch_user = tw_api.get_user(twitch_user_login)

        if not notify_type or notify_type == NotifyCommunityType.TwitchLive:
            sclient.sqldb.remove_notify_community(NotifyCommunityType.TwitchLive, twitch_user.id, guildid)
        if not notify_type or notify_type == NotifyCommunityType.TwitchVideo:
            sclient.sqldb.remove_notify_community(NotifyCommunityType.TwitchVideo, twitch_user.id, guildid)
        if not notify_type or notify_type == NotifyCommunityType.TwitchClip:
            sclient.sqldb.remove_notify_community(NotifyCommunityType.TwitchClip, twitch_user.id, guildid)

        if notify_type:
            await ctx.respond(f"已移除 {twitch_user.display_name}({twitch_user.login}) 的通知")
        else:
            await ctx.respond(f"已移除 {twitch_user.display_name}({twitch_user.login}) 的所有通知")

    @twitch.command(name="notify", description="確認twitch開台通知")
    async def twitch_notify(self, ctx, twitch_user_login: discord.Option(str, required=True, name="twitch使用者名稱", description="英文的使用者名稱")):
        guildid = ctx.guild.id
        record = sclient.sqldb.get_notify_community_user_byname(NotifyCommunityType.TwitchLive, twitch_user_login, guildid)
        if record:
            channel = self.bot.get_channel(record.channel_id)
            role = channel.guild.get_role(record.role_id)
            if role:
                await ctx.respond(f"Twitch名稱: {twitch_user_login} 的開台通知在 {channel.mention} 並通知 {role.mention}")
            else:
                await ctx.respond(f"Twitch名稱: {twitch_user_login} 的開台通知在 {channel.mention}")
        else:
            await ctx.respond(f"Twitch名稱: {twitch_user_login} 在此群組沒有設開台通知")

    @twitch.command(name="list", description="確認伺服器內所有的twitch通知")
    async def twitch_list(self, ctx: discord.ApplicationContext):
        guildid = ctx.guild.id
        embed = BotEmbed.general("twitch通知", ctx.guild.icon.url if ctx.guild.icon else None)
        dbdata = (
            sclient.sqldb.get_notify_community_list(NotifyCommunityType.TwitchLive, guildid)
            + sclient.sqldb.get_notify_community_list(NotifyCommunityType.TwitchVideo, guildid)
            + sclient.sqldb.get_notify_community_list(NotifyCommunityType.TwitchClip, guildid)
        )  # type: ignore
        for notify_data, community_data in dbdata:
            display_name = f"{community_data.display_name}（{community_data.username}）"
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

    @twitch.command(name="user", description="取得twitch頻道的相關資訊")
    async def twitch_user(self, ctx, twitch_user_login: discord.Option(str, required=True, name="twitch使用者名稱", description="英文的使用者名稱")):
        user = tw_api.get_user(twitch_user_login)
        if user:
            await ctx.respond(embed=user.desplay())
        else:
            await ctx.respond(f"查詢不到 {twitch_user_login}", ephemeral=True)

    @youtube.command(name="channel", description="取得youtube頻道的相關資訊")
    async def youtube_channel(self, ctx, ythandle: discord.Option(str, required=True, name="youtube帳號代碼", description="youtube頻道中以@開頭的代號")):
        channel = yt_api.get_channel(handle=ythandle)
        if channel:
            await ctx.respond("查詢成功", embed=channel.embed())
        else:
            await ctx.respond("查詢失敗", ephemeral=True)

    @youtube.command(name="set", description="設置youtube開台通知")
    async def youtube_set(
        self,
        ctx,
        ythandle: discord.Option(str, required=True, name="youtube帳號代碼", description="youtube頻道中以@開頭的代號"),
        channel: discord.Option(discord.TextChannel, required=True, name="頻道", description="通知將會發送到此頻道"),
        role: discord.Option(discord.Role, required=False, default=None, name="身分組", description="發送通知時tag的身分組"),
        msg: discord.Option(str, default=None, name="通知文字", description="發送通知時的自訂文字"),
    ):
        guildid = ctx.guild.id
        channelid = channel.id
        roleid = role.id if role else None

        ytchannel = yt_api.get_channel(handle=ythandle)
        if ytchannel:
            sclient.sqldb.add_notify_community(NotifyCommunityType.Youtube, ytchannel.id, guildid, channelid, roleid, msg, cache_time=datetime.now(tz=tz))
            sclient.sqldb.merge(
                Community(id=ytchannel.id, type=CommunityType.Youtube, display_name=ytchannel.snippet.title, username=ytchannel.snippet.customUrl)
            )

            if role:
                await ctx.respond(f"設定成功：{ytchannel.snippet.title}的通知將會發送在{channel.mention}並會通知{role.mention}")
            else:
                await ctx.respond(f"設定成功：{ytchannel.snippet.title}的通知將會發送在{channel.mention}")

            if not channel.can_send():
                await ctx.send(embed=BotEmbed.simple("溫馨提醒", f"我無法在{channel.mention}中發送訊息，請確認我有足夠的權限"))
        else:
            await ctx.respond(f"錯誤：找不到帳號代碼 {ythandle} 的頻道")
            return

        record = sclient.sqldb.get_push_record(ytchannel.id)
        if record.is_expired:
            callback_url = sclient.sqldb.get_bot_token(APIType.Google, 4).callback_uri
            yt_push.add_push(ytchannel.id, callback_url)
            await asyncio.sleep(3)
            data = yt_push.get_push(ytchannel.id, callback_url)

            if data.has_verify:
                record.push_at = data.last_successful_verification
                record.expire_at = data.expiration_time
                sclient.sqldb.merge(record)

    @youtube.command(name="remove", description="移除youtube通知")
    async def youtube_remove(self, ctx, ythandle: discord.Option(str, required=True, name="youtube帳號代碼", description="youtube頻道中以@開頭的代號")):
        guildid = ctx.guild.id

        ytchannel = yt_api.get_channel(handle=ythandle)
        if not ytchannel:
            await ctx.respond(f"錯誤：找不到帳號代碼 {ythandle} 的頻道")
            return

        sclient.sqldb.remove_notify_community(NotifyCommunityType.Youtube, ytchannel.id, guildid)
        await ctx.respond(f"已移除頻道 {ytchannel.snippet.title} 的通知")

    @youtube.command(name="notify", description="確認youtube通知")
    async def youtube_notify(self, ctx, ythandle: discord.Option(str, required=True, name="youtube帳號代碼", description="youtube頻道中以@開頭的代號")):
        guildid = ctx.guild.id

        ytchannel = yt_api.get_channel(handle=ythandle)
        if not ytchannel:
            await ctx.respond(f"錯誤：找不到帳號代碼 {ythandle} 的頻道")
            return

        record = sclient.sqldb.get_notify_community_user_byid(NotifyCommunityType.Youtube,ytchannel.id,guildid)
        if record:
            channel = self.bot.get_channel(record.channel_id)
            role = channel.guild.get_role(record.role_id)
            if role:
                await ctx.respond(f"Youtube頻道: {ytchannel.snippet.title} 的通知在 {channel.mention} 並通知 {role.mention}")
            else:
                await ctx.respond(f"Youtube頻道: {ytchannel.snippet.title} 的通知在 {channel.mention}")
        else:
            await ctx.respond(f"Youtube頻道: {ytchannel.snippet.title} 在此群組沒有設通知")

    @youtube.command(name="list", description="確認群組內所有的youtube通知")
    async def youtube_list(self,ctx):
        guildid = ctx.guild.id
        embed = BotEmbed.general("youtube通知",ctx.guild.icon.url if ctx.guild.icon else None)
        dbdata = sclient.sqldb.get_notify_community_list(NotifyCommunityType.Youtube, guildid)
        for notify_data, community_data in dbdata:
            notify_name = community_data.display_name
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

    @twitter.command(name="set", description="設置x/twitter通知")
    async def twitter_set(
        self,
        ctx,
        twitter_username: discord.Option(str, required=True, name="twitter使用者名稱", description="使用者名稱，當此用戶發文時會發送通知"),
        channel: discord.Option(discord.TextChannel, required=True, name="頻道", description="通知將會發送到此頻道"),
        role: discord.Option(discord.Role, required=False, default=None, name="身分組", description="發送通知時tag的身分組"),
    ):
        guildid = ctx.guild.id
        channelid = channel.id
        roleid = role.id if role else None

        api_twitter_user = cli_api.get_user_details(twitter_username)
        # try:
        #     api_twitter_user = twitter_api.get_user(username=twitter_username)
        # except TooManyRequests:
        #     await ctx.respond(f"錯誤：查詢過於頻繁，請稍後再試\n（X/Twitter短時間內僅提供少少的次數故容易觸發）")
        #     return

        sclient.sqldb.add_notify_community(
            NotifyCommunityType.TwitterTweet, api_twitter_user.id, guildid, channelid, roleid, None, cache_time=datetime.now(tz=tz)
        )
        sclient.sqldb.merge(
            Community(id=str(api_twitter_user.id), type=CommunityType.Twitter, display_name=api_twitter_user.fullName, username=api_twitter_user.userName)
        )

        if role:
            await ctx.respond(f"設定成功：{api_twitter_user.fullName}的通知將會發送在{channel.mention}並會通知{role.mention}")
        else:
            await ctx.respond(f"設定成功：{api_twitter_user.fullName}的通知將會發送在{channel.mention}")

        if not channel.can_send():
            await ctx.send(embed=BotEmbed.simple("溫馨提醒", f"我無法在{channel.mention}中發送訊息，請確認我有足夠的權限"))

    @twitter.command(name="remove", description="移除x/twitter通知")
    async def twitter_remove(self, ctx, twitter_username: discord.Option(str, required=True, name="twitter使用者名稱", description="使用者名稱")):
        guildid = ctx.guild.id
        twitter_user = cli_api.get_user_details(twitter_username)
        sclient.sqldb.remove_notify_community(NotifyCommunityType.TwitterTweet, twitter_user.id, guildid)
        await ctx.respond(f"已移除 {twitter_username} 的通知")

    @twitter.command(name="notify", description="確認x/twitter通知")
    async def twitter_notify(self, ctx, twitter_username: discord.Option(str, required=True, name="twitter使用者名稱", description="使用者名稱")):
        guildid = ctx.guild.id
        record = sclient.sqldb.get_notify_community_user_byname(NotifyCommunityType.TwitterTweet, twitter_username, guildid)
        if record:
            channel = self.bot.get_channel(record.channel_id)
            role = channel.guild.get_role(record.role_id)
            if role:
                await ctx.respond(f"X/Twitter名稱: {twitter_username} 的通知在 {channel.mention} 並通知 {role.mention}")
            else:
                await ctx.respond(f"X/Twitter名稱: {twitter_username} 的通知在 {channel.mention}")
        else:
            await ctx.respond(f"X/Twitter名稱: {twitter_username} 在此群組沒有設通知")

    @twitter.command(name="list", description="確認群組內所有的x/twitter通知")
    async def twitter_list(self, ctx):
        guildid = ctx.guild.id
        records = sclient.sqldb.get_notify_community_list(NotifyCommunityType.TwitterTweet, guildid)
        if records:
            embed = BotEmbed.general("X/Twitter通知列表", ctx.guild.icon.url if ctx.guild.icon else None)
            for notify_record, community_record in records:
                channel = self.bot.get_channel(notify_record.channel_id)
                role = channel.guild.get_role(notify_record.role_id)
                if role:
                    embed.add_field(name=community_record.username, value=f"{channel.mention} {role.mention}")
                else:
                    embed.add_field(name=community_record.username, value=channel.mention)
            await ctx.respond(embed=embed)
        else:
            await ctx.respond("此群組沒有設置任何X/Twitter通知")

    @twitter.command(name="user", description="取得twitter使用者的相關資訊")
    async def twitter_user(self, ctx, twitter_username: discord.Option(str, required=True, name="twitter使用者名稱", description="使用者名稱")):
        user = cli_api.get_user_details(twitter_username)
        if user:
            await ctx.respond(embed=user.embed())
        else:
            await ctx.respond(f"查詢不到 {twitter_username}", ephemeral=True)


def setup(bot):
    bot.add_cog(system_community(bot))
