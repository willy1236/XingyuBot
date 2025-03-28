import asyncio
import os

import discord

from starlib import BotEmbed, Jsondb, log, sqldb
from starlib.instance import debug_mode
from starlib.types import NotifyChannelType, NotifyCommunityType


class DiscordBot(discord.Bot):
    _COG_PATH = './starDiscord/cmds'

    def __init__(self,bot_code):
        super().__init__(
            owner_id = 419131103836635136,
            intents = discord.Intents.all(),
            help_command = None
        )
        
        self.debug_mode = debug_mode
        self.bot_code = bot_code

        if bot_code != 'Bot1':
            self.debug_guilds = Jsondb.config.get('debug_guilds')

    def run(self):
        token = Jsondb.tokens.get(self.bot_code)
        super().run(token)
        
    def load_all_extensions(self):
        for filename in os.listdir(self._COG_PATH):
            if filename.endswith('.py'):
                self.load_extension(f'starDiscord.cmds.{filename[:-3]}')

    @property
    def mention_owner(self):
        return f'<@{self.owner_id}>'

    async def error(self, ctx:discord.ApplicationContext, error:str) -> None:
        error_report = self.get_channel(Jsondb.config.get('error_report'))
        embed = BotEmbed.general(name=ctx.author,icon_url=ctx.author.display_avatar.url, title="❌錯誤回報")
        embed.add_field(name='錯誤訊息', value=f'```py\n{error}```', inline=True)
        if ctx.command:
            embed.add_field(name='使用指令', value=f'```{ctx.command}```', inline=False)
            embed.add_field(name='參數', value=f'```{ctx.selected_options}```', inline=False)
        embed.add_field(name='使用者', value=f"{ctx.author}\n{ctx.author.id}", inline=False)
        embed.add_field(name='發生頻道', value=f'{ctx.channel}\n{ctx.channel.id}', inline=True)
        embed.add_field(name='發生群組', value=f'{ctx.guild}\n{ctx.guild.id}', inline=True)
        await error_report.send(embed=embed)

    async def report(self,msg:str):
        report_channel = self.get_channel(Jsondb.config.get('report_channel'))
        embed = BotEmbed.general(name="回報訊息")
        embed.add_field(name='訊息', value=msg, inline=True)
        await report_channel.send(embed=embed)

    async def feedback(self,ctx:discord.ApplicationContext, msg:discord.Message):
        feedback_channel = self.get_channel(Jsondb.config.get('feedback_channel'))
        embed = BotEmbed.general(name=msg.author,icon_url=msg.author.display_avatar.url, title="💬回饋訊息", description=msg.content)
        #embed.add_field(name='訊息內容', value=msg, inline=True)
        embed.add_field(name='發送者', value=f"{ctx.author}\n{ctx.author.id}", inline=False)
        embed.add_field(name='來源頻道', value=f'{ctx.channel}\n{ctx.channel.id}', inline=True)
        embed.add_field(name='來源群組', value=f'{ctx.guild}\n{ctx.guild.id}', inline=True)
        embed.timestamp = msg.created_at
        await feedback_channel.send(embed=embed)

    async def dm(self,msg:discord.Message):
        dm_channel = self.get_channel(Jsondb.config.get('dm_channel'))
        embed = BotEmbed.general(name=msg.author.name, icon_url=msg.author.display_avatar.url, title="💭私訊", description=msg.content)
        # embed.add_field(name='訊息內容', value=msg.content, inline=True)
        if msg.channel.recipient:
            embed.add_field(name='發送者', value=f"{msg.author}->{msg.channel.recipient}\n{msg.author.id}->{msg.channel.recipient.id}", inline=False)
        else:
            embed.add_field(name='發送者', value=f"{msg.author}\n{msg.author.id}", inline=False)
        embed.set_footer(text=self.user.display_name, icon_url=self.user.display_avatar.url)
        embed.timestamp = msg.created_at
        await dm_channel.send(embed=embed)

    async def mentioned(self,msg:discord.Message):
        dm_channel = self.get_channel(Jsondb.config.get('mentioned_channel'))
        embed=BotEmbed.general(name=msg.author,icon_url=msg.author.display_avatar.url, title="提及訊息", description=f"{msg.content}\n{msg.jump_url}")
        #embed.add_field(name='訊息內容', value=msg.content, inline=True)
        embed.add_field(name='發送者', value=f"{msg.author}\n{msg.author.id}", inline=False)
        embed.add_field(name='來源頻道', value=f'{msg.channel}\n{msg.channel.id}', inline=True)
        embed.add_field(name='來源群組', value=f'{msg.guild}\n{msg.guild.id}', inline=True)
        embed.timestamp = msg.created_at
        await dm_channel.send(embed=embed)
    
    async def mention_everyone(self,msg:discord.Message):
        dm_channel = self.get_channel(Jsondb.config.get('mention_everyone_channel'))
        embed=BotEmbed.general(name=msg.author,icon_url=msg.author.display_avatar.url, title="提及所有人訊息", description=f"{msg.content}\n{msg.jump_url}")
        embed.add_field(name='發送者', value=f"{msg.author}\n{msg.author.id}", inline=False)
        embed.add_field(name='來源頻道', value=f'{msg.channel}\n{msg.channel.id}', inline=True)
        embed.add_field(name='來源群組', value=f'{msg.guild}\n{msg.guild.id}', inline=True)
        embed.timestamp = msg.created_at
        await dm_channel.send(embed=embed)

    async def send_notify_communities(self, embed:discord.Embed, notify_type:NotifyCommunityType, community_id:str, content:str=None):
        guilds = sqldb.get_notify_community_guild(notify_type.value, community_id)
        log.debug(f"{notify_type} guilds: {guilds}")
        for guildid in guilds:
            channel = self.get_channel(guilds[guildid][0])
            if channel:
                text = content or guilds[guildid][2]
                role = channel.guild.get_role(guilds[guildid][1])
                if role:
                    text = f'{role.mention} {text}' if text is not None else f'{role.mention}'
                    
                log.debug(f"send_notify_communities: {guildid}/{guilds[guildid][0]}: {text}")
                await channel.send(text, embed=embed)
                await asyncio.sleep(0.5)
            else:
                log.warning(f"{notify_type} not found: {guildid}/{guildid[0]}")
    
    async def send_notify_channel(self, embed:discord.Embed, notify_type:NotifyChannelType, content:str=None):
        notify_channels = sqldb.get_notify_channel_by_type(notify_type)
        log.debug(f"{notify_type} channels: {notify_channels}")
        for no_channel in notify_channels:
            channel = self.get_channel(no_channel.channel_id)
            if channel:
                role = channel.guild.get_role(no_channel.role_id)
                if role:
                    text = f'{content} {role.mention}' if content is not None else f'{role.mention}'
                else:
                    text = content

                await channel.send(text, embed=embed)
                await asyncio.sleep(0.5)
            else:
                log.warning(f"{notify_type} not found: {no_channel.guild_id}/{no_channel.channel_id}")

    async def edit_notify_channel(self, embed:discord.Embed | list[discord.Embed], notify_type:NotifyChannelType, content:str=None):
        records = sqldb.get_notify_channel_by_type(notify_type)
        for i in records:
            channel = self.get_channel(i.channel_id)
            if channel:
                try:
                    msg = await channel.fetch_message(channel.last_message_id)
                except:
                    msg = None

                if msg and msg.author == self.user:
                    await msg.edit(content, embeds=embed if isinstance(embed, list) else [embed])
                else:
                    await channel.send(embed=BotEmbed.simple('溫馨提醒','此為定時通知，請將機器人的訊息保持在此頻道的最新訊息，以免機器人找不到訊息而重複發送'))
                    await channel.send(content, embeds=embed if isinstance(embed, list) else [embed])
                await asyncio.sleep(0.5)
            
            else:
                log.warning(f"{notify_type} not found: {i.guild_id}/{i.channel_id}")

    def about_embed(self):
        embed = BotEmbed.bot(self,description=f"你好~我是星羽，你可以輸入 </help:1067700245015834638> 來查看所有指令的用法\n\n希望我能在discord上幫助到你喔~\n有任何建議、需求、協助與合作可以使用 </feedback:1067700244848058386> 指令\n\n支援伺服器：https://discord.gg/P4jqdcMxkH")
        embed.set_footer(text="此機器人由 威立 負責維護")
        return embed
    
    def send_message(self, channel_id=566533708371329026, *, content=None, embed=None) -> discord.Message | None:
        if not content and not embed:
            raise ValueError('Content and embed must provided at least one.')
        channel = self.get_channel(channel_id)
        if channel:
            r = asyncio.run_coroutine_threadsafe(channel.send(content=content, embed=embed), self.loop)
            return r.result()

#commands.Bot
#shard_count=1,
#command_prefix=commands.when_mentioned_or('b!'),
#command_prefix='b!',
#case_insensitive=True,
