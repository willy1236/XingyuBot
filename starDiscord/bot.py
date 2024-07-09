import asyncio
import os

import discord

from starlib import BotEmbed, Jsondb, log, sqldb
from starlib.types import NotifyCommunityType


class DiscordBot(discord.Bot):
    _COG_PATH = './starDiscord/cmds'

    def __init__(self,bot_code):
        super().__init__(
            owner_id = 419131103836635136,
            intents = discord.Intents.all(),
            help_command = None
        )
        
        self.bot_code = bot_code
        self.main_guilds = Jsondb.config.get('main_guilds')
        self.debug_mode = Jsondb.config.get('debug_mode',True)

        if bot_code != 'Bot1':
            self.debug_guilds = Jsondb.config.get('debug_guilds')

    def run(self):
        token = Jsondb.tokens.get(self.bot_code)
        super().run(token)

    def load_all_extensions(self):
        for filename in os.listdir(self._COG_PATH):
            if filename.endswith('.py'):
                self.load_extension(f'starDiscord.cmds.{filename[:-3]}')

    async def error(self, ctx:discord.ApplicationContext, error:str) -> None:
        error_report = self.get_channel(Jsondb.config.get('error_report'))
        embed = BotEmbed.general(name="BRS | 錯誤回報")
        embed.add_field(name='錯誤訊息', value=f'```py\n{error}```', inline=True)
        if ctx.command:
            embed.add_field(name='使用指令', value=f'```{ctx.command}```', inline=False)
            embed.add_field(name='參數', value=f'```{ctx.selected_options}```', inline=False)
        embed.add_field(name='使用者', value=f"{ctx.author}\n{ctx.author.id}", inline=False)
        embed.add_field(name='發生頻道', value=f'{ctx.channel}\n{ctx.channel.id}', inline=True)
        embed.add_field(name='發生群組', value=f'{ctx.guild}\n{ctx.guild.id}', inline=True)
        await error_report.send(embed=embed)

    async def report(self,msg):
        report_channel = self.get_channel(Jsondb.config.get('report_channel'))
        embed = BotEmbed.general(name="BRS | 回報訊息")
        embed.add_field(name='訊息', value=msg, inline=True)
        await report_channel.send(embed=embed)

    async def feedback(self,ctx:discord.ApplicationContext, msg) -> None:
        feedback_channel = self.get_channel(Jsondb.config.get('feedback_channel'))
        embed = BotEmbed.general(name="BRS | 回饋訊息")
        embed.add_field(name='訊息內容', value=msg, inline=True)
        embed.add_field(name='發送者', value=f"{ctx.author}\n{ctx.author.id}", inline=False)
        embed.add_field(name='來源頻道', value=f'{ctx.channel}\n{ctx.channel.id}', inline=True)
        embed.add_field(name='來源群組', value=f'{ctx.guild}\n{ctx.guild.id}', inline=True)
        await feedback_channel.send(embed=embed)

    async def dm(self,msg:discord.Message) -> None:
        dm_channel = self.get_channel(Jsondb.config.get('dm_channel'))
        embed = BotEmbed.general(name="BRS | 私人訊息")
        embed.add_field(name='訊息內容', value=msg.content, inline=True)
        if msg.channel.recipient:
            embed.add_field(name='發送者', value=f"{msg.author}->{msg.channel.recipient}\n{msg.author.id}->{msg.channel.recipient.id}", inline=False)
        else:
            embed.add_field(name='發送者', value=f"{msg.author}\n{msg.author.id}", inline=False)
        await dm_channel.send(embed=embed)

    async def mentioned(self,msg:discord.Message) -> None:
        dm_channel = self.get_channel(Jsondb.config.get('mentioned_channel'))
        embed=BotEmbed.general(name="BRS | 提及訊息",description=msg.jump_url)
        embed.add_field(name='訊息內容', value=msg.content, inline=True)
        embed.add_field(name='發送者', value=f"{msg.author}\n{msg.author.id}", inline=False)
        embed.add_field(name='來源頻道', value=f'{msg.channel}\n{msg.channel.id}', inline=True)
        embed.add_field(name='來源群組', value=f'{msg.guild}\n{msg.guild.id}', inline=True)
        await dm_channel.send(embed=embed)
    
    async def mention_everyone(self,msg:discord.Message) -> None:
        dm_channel = self.get_channel(Jsondb.config.get('mention_everyone_channel'))
        embed=BotEmbed.general(name="BRS | 提及所有人訊息",description=f"https://discord.com/channels/{msg.guild.id}/{msg.channel.id}/{msg.id}")
        embed.add_field(name='訊息內容', value=msg.content, inline=True)
        embed.add_field(name='發送者', value=f"{msg.author}\n{msg.author.id}", inline=False)
        embed.add_field(name='來源頻道', value=f'{msg.channel}\n{msg.channel.id}', inline=True)
        embed.add_field(name='來源群組', value=f'{msg.guild}\n{msg.guild.id}', inline=True)
        await dm_channel.send(embed=embed)

    async def send_message_to_notify_communities(self, embed:discord.Embed, notify_type:NotifyCommunityType, notify_name:str):
            guilds = sqldb.get_notify_community_guild(notify_type.value, notify_name)
            log.debug(f"{notify_type} guilds: {guilds}")
            for guildid in guilds:
                guild = self.get_guild(guildid)
                channel = self.get_channel(guilds[guildid][0])
                role = guild.get_role(guilds[guildid][1])
                if channel:
                    if role:
                        await channel.send(f'{role.mention}',embed=embed)
                    else:
                        await channel.send(embed=embed)
                    await asyncio.sleep(0.5)
                else:
                    log.warning(f"{notify_type} not found: {guild.id}/{channel.id}")

    def about_embed(self):
        embed = BotEmbed.bot(self,description=f"你好~我是星羽，你可以輸入 </help:1067700245015834638> 來查看所有指令的用法\n\n希望我能在discord上幫助到你喔~\n有任何建議、需求、協助與合作可以使用 </feedback:1067700244848058386> 指令\n\n支援伺服器：https://discord.gg/ye5yrZhYGF")
        embed.set_footer(text="此機器人由 威立 負責維護")
        return embed

#commands.Bot
#shard_count=1,
#command_prefix=commands.when_mentioned_or('b!'),
#command_prefix='b!',
#case_insensitive=True,
