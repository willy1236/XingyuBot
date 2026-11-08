import asyncio

import discord
from discord.commands import SlashCommandGroup
from discord.ext import commands

from starlib import BotEmbed, ChoiceList, Jsondb, notify_settings, sclient
from starlib.database import NotifyCommunityType, PlatformType
from starlib.instance import cli_api, google_api, tw_api
from starlib.notify_settings import LookupFailure

from ..extension import Cog_Extension

twitch_notify_option = ChoiceList.set("twitch_notify_option")

LOOKUP_UNAVAILABLE = "目前無法向平台查詢，請稍後再試"


async def resolve_account(platform: PlatformType, text: str, not_found: str) -> notify_settings.AccountInfo | str:
    """查詢帳號；失敗時回傳要告訴使用者的錯誤訊息。查詢會阻塞數十秒，放到 thread 執行。"""
    try:
        return await asyncio.to_thread(notify_settings.resolve_account, platform, text)
    except LookupFailure as e:
        if e.reason == "platform_unavailable":
            return LOOKUP_UNAVAILABLE
        return not_found if e.reason == "not_found" else f"錯誤：格式不支援 {text}"


class system_community(Cog_Extension):
    twitch = SlashCommandGroup("twitch", "Twitch相關指令", name_localizations=ChoiceList.name("twitch"))
    youtube = SlashCommandGroup("youtube", "youtube相關指令", name_localizations=ChoiceList.name("youtube"))
    twitter = SlashCommandGroup("twitter", "twitter相關指令", name_localizations=ChoiceList.name("twitter"))

    @twitch.command(name="set", description="設置twitch開台通知", name_localizations=ChoiceList.name("twitch_set"))
    @commands.has_permissions(manage_channels=True)
    @commands.guild_only()
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

        account = await resolve_account(PlatformType.Twitch, twitch_user_login, f"錯誤：找不到用戶 {twitch_user_login}")
        if isinstance(account, str):
            await ctx.respond(account)
            return

        await asyncio.to_thread(notify_settings.set_notify, account, type, guildid, channelid, roleid, msg)

        type_tw = Jsondb.get_tw(type.value, "twitch_notify_option")
        if role:
            await ctx.respond(f"設定成功：{account.display_name}({account.username})的{type_tw}將會發送在{channel.mention}並會通知{role.mention}")
        else:
            await ctx.respond(f"設定成功：{account.display_name}({account.username})的{type_tw}將會發送在{channel.mention}")

        if not channel.can_send():
            await ctx.send(embed=BotEmbed.simple("溫馨提醒", f"我無法在{channel.mention}中發送訊息，請確認我有足夠的權限"))

    @twitch.command(name="remove", description="移除twitch開台通知", name_localizations=ChoiceList.name("twitch_remove"))
    @commands.has_permissions(manage_channels=True)
    @commands.guild_only()
    async def twitch_remove(
        self,
        ctx,
        twitch_user_login: discord.Option(str, required=True, name="twitch使用者名稱", description="英文的使用者名稱"),
        notify_type: discord.Option(
            int, required=False, name="通知種類", description="要移除的通知種類，留空為移除全部", choices=twitch_notify_option, default=None
        ),
    ):
        guildid = ctx.guild.id
        account = await resolve_account(PlatformType.Twitch, twitch_user_login, f"錯誤：找不到用戶 {twitch_user_login}")
        if isinstance(account, str):
            await ctx.respond(account)
            return

        for t in (NotifyCommunityType.TwitchLive, NotifyCommunityType.TwitchVideo, NotifyCommunityType.TwitchClip):
            if not notify_type or notify_type == t:
                await asyncio.to_thread(notify_settings.remove_notify, t, account.id, guildid)

        if notify_type:
            await ctx.respond(f"已移除 {account.display_name}({account.username}) 的通知")
        else:
            await ctx.respond(f"已移除 {account.display_name}({account.username}) 的所有通知")

    @twitch.command(name="notify", description="確認twitch開台通知", name_localizations=ChoiceList.name("twitch_notify"))
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

    @twitch.command(name="list", description="確認伺服器內所有的twitch通知", name_localizations=ChoiceList.name("twitch_list"))
    async def twitch_list(self, ctx: discord.ApplicationContext):
        guildid = ctx.guild.id
        embed = BotEmbed.general("twitch通知", ctx.guild.icon.url if ctx.guild.icon else None)
        dbdata = (
            sclient.sqldb.get_notify_community_list(NotifyCommunityType.TwitchLive, guildid)
            + sclient.sqldb.get_notify_community_list(NotifyCommunityType.TwitchVideo, guildid)  # pyright: ignore[reportOperatorIssue]
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

    @twitch.command(name="user", description="取得twitch頻道的相關資訊", name_localizations=ChoiceList.name("twitch_user"))
    async def twitch_user(self, ctx, twitch_user_login: discord.Option(str, required=True, name="twitch使用者名稱", description="英文的使用者名稱")):
        user = tw_api.get_user(twitch_user_login)
        if user:
            await ctx.respond(embed=user.embed())
        else:
            await ctx.respond(f"查詢不到 {twitch_user_login}", ephemeral=True)

    @youtube.command(name="channel", description="取得youtube頻道的相關資訊", name_localizations=ChoiceList.name("youtube_channel"))
    async def youtube_channel(self, ctx, ythandle: discord.Option(str, required=True, name="youtube帳號代碼", description="youtube頻道中以@開頭的代號")):
        channel = google_api.get_channel(handle=ythandle)
        if channel:
            await ctx.respond("查詢成功", embed=channel.embed())
        else:
            await ctx.respond("查詢失敗", ephemeral=True)

    @youtube.command(name="set", description="設置youtube開台通知", name_localizations=ChoiceList.name("youtube_set"))
    @commands.has_permissions(manage_channels=True)
    @commands.guild_only()
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

        account = await resolve_account(PlatformType.Google, ythandle, f"錯誤：找不到帳號代碼 {ythandle} 的頻道")
        if isinstance(account, str):
            await ctx.respond(account)
            return

        await asyncio.to_thread(notify_settings.set_notify, account, NotifyCommunityType.Youtube, guildid, channelid, roleid, msg)

        if role:
            await ctx.respond(f"設定成功：{account.display_name}的通知將會發送在{channel.mention}並會通知{role.mention}")
        else:
            await ctx.respond(f"設定成功：{account.display_name}的通知將會發送在{channel.mention}")

        if not channel.can_send():
            await ctx.send(embed=BotEmbed.simple("溫馨提醒", f"我無法在{channel.mention}中發送訊息，請確認我有足夠的權限"))

        # TODO: 回歸定時任務
        if await asyncio.to_thread(notify_settings.ensure_youtube_push, account.id) == "failed":
            await ctx.send(embed=BotEmbed.simple("溫馨提醒", "目前無法向 YouTube 訂閱推播，請稍後再重新設定一次"))

    @youtube.command(name="remove", description="移除youtube通知", name_localizations=ChoiceList.name("youtube_remove"))
    @commands.has_permissions(manage_channels=True)
    @commands.guild_only()
    async def youtube_remove(self, ctx, ythandle: discord.Option(str, required=True, name="youtube帳號代碼", description="youtube頻道中以@開頭的代號")):
        guildid = ctx.guild.id

        account = await resolve_account(PlatformType.Google, ythandle, f"錯誤：找不到帳號代碼 {ythandle} 的頻道")
        if isinstance(account, str):
            await ctx.respond(account)
            return

        await asyncio.to_thread(notify_settings.remove_notify, NotifyCommunityType.Youtube, account.id, guildid)
        await ctx.respond(f"已移除頻道 {account.display_name} 的通知")

    @youtube.command(name="notify", description="確認youtube通知", name_localizations=ChoiceList.name("youtube_notify"))
    async def youtube_notify(self, ctx, ythandle: discord.Option(str, required=True, name="youtube帳號代碼", description="youtube頻道中以@開頭的代號")):
        guildid = ctx.guild.id

        ytchannel = google_api.get_channel(handle=ythandle)
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

    @youtube.command(name="list", description="確認群組內所有的youtube通知", name_localizations=ChoiceList.name("youtube_list"))
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

    @twitter.command(name="set", description="設置x/twitter通知", name_localizations=ChoiceList.name("twitter_set"))
    @commands.has_permissions(manage_channels=True)
    @commands.guild_only()
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

        account = await resolve_account(PlatformType.Twitter, twitter_username, f"錯誤：查無此使用者 {twitter_username}")
        if isinstance(account, str):
            await ctx.respond(account)
            return

        await asyncio.to_thread(notify_settings.set_notify, account, NotifyCommunityType.TwitterTweet, guildid, channelid, roleid, None)

        if role:
            await ctx.respond(f"設定成功：{account.display_name}的通知將會發送在{channel.mention}並會通知{role.mention}")
        else:
            await ctx.respond(f"設定成功：{account.display_name}的通知將會發送在{channel.mention}")

        if not channel.can_send():
            await ctx.send(embed=BotEmbed.simple("溫馨提醒", f"我無法在{channel.mention}中發送訊息，請確認我有足夠的權限"))

    @twitter.command(name="remove", description="移除x/twitter通知", name_localizations=ChoiceList.name("twitter_remove"))
    @commands.has_permissions(manage_channels=True)
    @commands.guild_only()
    async def twitter_remove(self, ctx, twitter_username: discord.Option(str, required=True, name="twitter使用者名稱", description="使用者名稱")):
        guildid = ctx.guild.id
        account = await resolve_account(PlatformType.Twitter, twitter_username, f"錯誤：查無此使用者 {twitter_username}")
        if isinstance(account, str):
            await ctx.respond(account)
            return
        await asyncio.to_thread(notify_settings.remove_notify, NotifyCommunityType.TwitterTweet, account.id, guildid)
        await ctx.respond(f"已移除 {twitter_username} 的通知")

    @twitter.command(name="notify", description="確認x/twitter通知", name_localizations=ChoiceList.name("twitter_notify"))
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

    @twitter.command(name="list", description="確認群組內所有的x/twitter通知", name_localizations=ChoiceList.name("twitter_list"))
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

    @twitter.command(name="user", description="取得twitter使用者的相關資訊", name_localizations=ChoiceList.name("twitter_user"))
    async def twitter_user(self, ctx, twitter_username: discord.Option(str, required=True, name="twitter使用者名稱", description="使用者名稱")):
        user = cli_api.get_user_details(twitter_username)
        if user:
            await ctx.respond(embed=user.embed())
        else:
            await ctx.respond(f"查詢不到 {twitter_username}", ephemeral=True)

    @twitter.command(name="tweet", description="取得twitter使用者的最新推文", name_localizations=ChoiceList.name("twitter_tweet"))
    async def twitter_tweet(self, ctx, tweet_id: discord.Option(str, required=True, name="推文id", description="推文的ID（數字）")):
        tweet = cli_api.get_tweet_details(tweet_id)
        if tweet:
            await ctx.respond(embed=tweet.embed())
        else:
            await ctx.respond(f"查詢不到 {tweet_id} 的推文", ephemeral=True)

def setup(bot):
    bot.add_cog(system_community(bot))
