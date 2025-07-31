import asyncio
import datetime
import os

import discord
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from starlib import BotEmbed, Jsondb, log, sqldb
from starlib.instance import debug_mode
from starlib.types import APIType, NotifyChannelType, NotifyCommunityType


class DiscordBot(discord.Bot):
    _COG_PATH = "./starDiscord/cmds"

    def __init__(self, bot_code):
        super().__init__(
            owner_id=419131103836635136,
            intents=discord.Intents.all(),
            help_command=None
        )

        self.debug_mode = debug_mode
        self.bot_code = bot_code
        self.scheduler = AsyncIOScheduler()

        if bot_code != "1":
            self.debug_guilds = Jsondb.config.get("debug_guilds")

    def run(self):
        token = sqldb.get_bot_token(APIType.Discord, self.bot_code).access_token
        super().run(token)

    def load_all_extensions(self):
        for filename in os.listdir(self._COG_PATH):
            if filename.endswith(".py"):
                self.load_extension(f"starDiscord.cmds.{filename[:-3]}")

    @property
    def mention_owner(self):
        return f"<@{self.owner_id}>"

    async def error(self, ctx: discord.ApplicationContext, error: str) -> None:
        error_report = self.get_channel(Jsondb.config.get("error_report"))
        embed = BotEmbed.general(
            name=str(ctx.author), icon_url=ctx.author.display_avatar.url, title="❌錯誤回報")
        embed.add_field(name="錯誤訊息", value=f"```py\n{error}```", inline=True)
        if ctx.command:
            embed.add_field(name="使用指令", value=f"```{ctx.command}```", inline=False)
            embed.add_field(name="參數", value=f"```{ctx.selected_options}```", inline=False)
        embed.add_field(name="使用者", value=f"{ctx.author}\n{ctx.author.id}", inline=False)
        embed.add_field(name="發生頻道", value=f"{ctx.channel}\n{ctx.channel.id}", inline=True)
        embed.add_field(name="發生群組", value=f"{ctx.guild}\n{ctx.guild.id}", inline=True)
        embed.timestamp = datetime.datetime.now()

        assert isinstance(error_report ,discord.abc.Messageable)
        await error_report.send(embed=embed)

    async def report(self, msg: str, refer_msg: discord.Message | None = None):
        report_channel = self.get_channel(Jsondb.config.get("report_channel"))
        embed = BotEmbed.general(name="回報訊息")
        embed.add_field(name="訊息", value=msg, inline=True)
        if refer_msg:
            embed.add_field(name="參考訊息", value=f"[{refer_msg.content}]({refer_msg.jump_url})", inline=False)
            embed.add_field(name="訊息ID", value=refer_msg.id, inline=True)
            embed.add_field(name="來源頻道", value=f"{refer_msg.channel}\n{refer_msg.channel.id}", inline=True)
            embed.add_field(name="來源群組", value=f"{refer_msg.guild}\n{refer_msg.guild.id}", inline=True)
        else:
            embed.add_field(name="訊息ID", value="無", inline=True)

        assert isinstance(report_channel ,discord.abc.Messageable)
        await report_channel.send(embed=embed)

    async def feedback(self, ctx: discord.ApplicationContext, msg: discord.Message):
        feedback_channel = self.get_channel(Jsondb.config.get("feedback_channel"))
        embed = BotEmbed.general(
            name=str(msg.author), icon_url=msg.author.display_avatar.url, title="💬回饋訊息", description=msg.content)
        # embed.add_field(name='訊息內容', value=msg, inline=True)
        embed.add_field(name="發送者", value=f"{ctx.author}\n{ctx.author.id}", inline=False)
        embed.add_field(name="來源頻道", value=f"{ctx.channel}\n{ctx.channel.id}", inline=True)
        embed.add_field(name="來源群組", value=f"{ctx.guild}\n{ctx.guild.id}", inline=True)
        embed.timestamp = msg.created_at
        await feedback_channel.send(embed=embed)

    async def dm(self, msg: discord.Message):
        dm_channel = self.get_channel(Jsondb.config.get("dm_channel"))
        embed = BotEmbed.general(
            name=msg.author.name, icon_url=msg.author.display_avatar.url, title="💭私訊", description=msg.content)
        # embed.add_field(name='訊息內容', value=msg.content, inline=True)
        if msg.channel.recipient:
            embed.add_field(name="發送者", value=f"{msg.author}->{msg.channel.recipient}\n{msg.author.id}->{msg.channel.recipient.id}", inline=False)
        else:
            embed.add_field(name="發送者", value=f"{msg.author}\n{msg.author.id}", inline=False)
        embed.set_footer(text=self.user.display_name,
                         icon_url=self.user.display_avatar.url)
        embed.timestamp = msg.created_at
        await dm_channel.send(embed=embed)

    async def mentioned(self, msg: discord.Message):
        dm_channel = self.get_channel(Jsondb.config.get("mentioned_channel"))
        embed = BotEmbed.general(name=msg.author, icon_url=msg.author.display_avatar.url,
                                 title="提及訊息", description=f"{msg.content}\n{msg.jump_url}")
        # embed.add_field(name='訊息內容', value=msg.content, inline=True)
        embed.add_field(name="發送者", value=f"{msg.author}\n{msg.author.id}", inline=False)
        embed.add_field(name="來源頻道", value=f"{msg.channel}\n{msg.channel.id}", inline=True)
        embed.add_field(name="來源群組", value=f"{msg.guild}\n{msg.guild.id}", inline=True)
        embed.timestamp = msg.created_at
        await dm_channel.send(embed=embed)

    async def mention_everyone(self, msg: discord.Message):
        dm_channel = self.get_channel(Jsondb.config.get("mention_everyone_channel"))
        embed = BotEmbed.general(name=msg.author, icon_url=msg.author.display_avatar.url,
                                 title="提及所有人訊息", description=f"{msg.content}\n{msg.jump_url}")
        embed.add_field(name="發送者", value=f"{msg.author}\n{msg.author.id}", inline=False)
        embed.add_field(name="來源頻道", value=f"{msg.channel}\n{msg.channel.id}", inline=True)
        embed.add_field(name="來源群組", value=f"{msg.guild}\n{msg.guild.id}", inline=True)
        embed.timestamp = msg.created_at
        await dm_channel.send(embed=embed)

    async def send_notify_communities(
        self,
        embed: discord.Embed,
        notify_type: NotifyCommunityType,
        community_id: str,
        default_content: str | None = None,
        no_mention: bool = False,
        additional_content: str | None = None,
    ):
        """
        Sends notification messages to multiple Discord communities with embeds and role mentions.
        This method retrieves a list of guilds/channels configured to receive notifications for a specific
        community and notification type, then sends the notification message with an embed to each channel.
        Args:
            embed (discord.Embed): The Discord embed to include with the notification message.
            notify_type (NotifyCommunityType): The type of notification being sent.
            community_id (str): The ID of the community this notification is for.
            default_content (str, optional): Default text content to send if no custom message is configured.
                Defaults to None.
            no_mention (bool, optional): If True, disables role mentions in the message. Defaults to False.
            additional_content (str, optional): Extra content to append to the message. Defaults to None.
        Returns:
            None
        Raises:
            discord.Forbidden: When the bot lacks permissions to send messages to a channel.
                This exception is caught and logged as a warning.
        Note:
            - Includes a 0.5 second delay between sends to avoid rate limiting
            - Logs warnings for channels that cannot be found or accessed
            - Role mentions are prepended to the message text unless no_mention is True
            - Additional content is appended with a newline separator if both text and additional_content exist
        """
        guilds = sqldb.get_notify_community_guild(notify_type, community_id)
        for guild_id, channel_id, role_id, message in guilds:
            channel = self.get_channel(channel_id)
            if channel:
                text = message or default_content
                role = channel.guild.get_role(role_id)
                if role and not no_mention:
                    text = f"{role.mention} {text}" if text is not None else f"{role.mention}"

                if additional_content:
                    text = additional_content if text is None else f"{text}\n{additional_content}"

                log.debug("send_notify_communities: %s/%s: %s", guild_id, channel_id, text)
                try:
                    await channel.send(text, embed=embed)
                except discord.Forbidden:
                    log.warning("NotifyCommunity:%s, channel missing access: %s/%s", notify_type, guild_id, channel_id)
                await asyncio.sleep(0.5)
            else:
                log.warning("NotifyCommunity:%s, channel not found: %s/%s", notify_type, guild_id, channel_id)

    async def send_notify_channel(self, embed: discord.Embed, notify_type: NotifyChannelType, default_content: str | None = None):
        notify_channels = sqldb.get_notify_channel_by_type(notify_type)
        for no_channel in notify_channels:
            channel = self.get_channel(no_channel.channel_id)
            if channel:
                role = channel.guild.get_role(no_channel.role_id)
                if role:
                    text = f"{default_content} {role.mention}" if default_content is not None else f"{role.mention}"
                else:
                    text = default_content

                try:
                    await channel.send(text, embed=embed)
                except discord.Forbidden:
                    log.warning("%s channel missing access: %s/%s", notify_type, no_channel.guild_id, no_channel.channel_id)
                await asyncio.sleep(0.5)
            else:
                log.warning("%s not found: %s/%s", notify_type, no_channel.guild_id, no_channel.channel_id)

    async def edit_notify_channel(self, embed: discord.Embed | list[discord.Embed], notify_type: NotifyChannelType, default_content: str = None):
        records = sqldb.get_notify_channel_by_type(notify_type)
        for i in records:
            channel = self.get_channel(i.channel_id)
            if channel:
                try:
                    msg = await channel.fetch_message(channel.last_message_id)
                except discord.NotFound:
                    msg = None

                if msg and msg.author == self.user:
                    await msg.edit(default_content, embeds=embed if isinstance(embed, list) else [embed])
                else:
                    await channel.send(
                        embed=BotEmbed.simple("溫馨提醒", "此為定時通知，請將機器人的訊息保持在此頻道的最新訊息，以免機器人找不到訊息而重複發送")
                    )
                    await channel.send(default_content, embeds=embed if isinstance(embed, list) else [embed])
                await asyncio.sleep(0.5)

            else:
                log.warning("NotifyChannel:%s, channel not found: %s/%s", notify_type, i.guild_id, i.channel_id)

    def about_embed(self):
        embed = BotEmbed.bot(
            self, description="你好~我是星羽，你可以輸入 </help:1067700245015834638> 來查看所有指令的用法\n\n希望我能在discord上幫助到你喔~\n有任何建議、需求、協助與合作可以使用 </feedback:1067700244848058386> 指令\n\n支援伺服器：https://discord.gg/P4jqdcMxkH")
        embed.set_footer(text="此機器人由 威立 負責維護")
        return embed

    def send_message(self, channel_id=566533708371329026, *, content=None, embed=None) -> discord.Message | None:
        if not content and not embed:
            raise ValueError("Content and embed must provided at least one.")
        channel = self.get_channel(channel_id)
        if channel:
            r = asyncio.run_coroutine_threadsafe(
                channel.send(content=content, embed=embed), self.loop)
            return r.result()

# commands.Bot
# shard_count=1,
# command_prefix=commands.when_mentioned_or('b!'),
# command_prefix='b!',
# case_insensitive=True,
