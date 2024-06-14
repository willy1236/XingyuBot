import asyncio

import discord
from discord.ext import commands
from ..fileDatabase import Jsondb
from ..database import sqldb
from ..types import NotifyCommunityType
from ..utilities import log, BotEmbed

class DiscordBot(discord.Bot):
    def __init__(self,bot_code):
        super().__init__(
            owner_id = 419131103836635136,
            intents = discord.Intents.all(),
            help_command = None
        )
        
        self.bot_code = bot_code
        self.main_guilds = Jsondb.jdata.get('main_guilds')
        self.debug_mode = Jsondb.jdata.get('debug_mode',True)

        if bot_code != 'Bot1':
            self.debug_guilds = Jsondb.jdata.get('debug_guilds')

    def run(self):
        token = Jsondb.get_token(self.bot_code)
        super().run(token)

    async def error(self, ctx:discord.ApplicationContext, error:str) -> None:
        error_report = self.get_channel(Jsondb.jdata['error_report'])
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
        report_channel = self.get_channel(Jsondb.jdata['report_channel'])
        embed = BotEmbed.general(name="BRS | 回報訊息")
        embed.add_field(name='訊息', value=msg, inline=True)
        await report_channel.send(embed=embed)

    async def feedback(self,ctx:discord.ApplicationContext, msg) -> None:
        feedback_channel = self.get_channel(Jsondb.jdata['feedback_channel'])
        embed = BotEmbed.general(name="BRS | 回饋訊息")
        embed.add_field(name='訊息內容', value=msg, inline=True)
        embed.add_field(name='發送者', value=f"{ctx.author}\n{ctx.author.id}", inline=False)
        embed.add_field(name='來源頻道', value=f'{ctx.channel}\n{ctx.channel.id}', inline=True)
        embed.add_field(name='來源群組', value=f'{ctx.guild}\n{ctx.guild.id}', inline=True)
        await feedback_channel.send(embed=embed)

    async def dm(self,msg:discord.Message) -> None:
        dm_channel = self.get_channel(Jsondb.jdata['dm_channel'])
        embed = BotEmbed.general(name="BRS | 私人訊息")
        embed.add_field(name='訊息內容', value=msg.content, inline=True)
        if msg.channel.recipient:
            embed.add_field(name='發送者', value=f"{msg.author}->{msg.channel.recipient}\n{msg.author.id}->{msg.channel.recipient.id}", inline=False)
        else:
            embed.add_field(name='發送者', value=f"{msg.author}\n{msg.author.id}", inline=False)
        await dm_channel.send(embed=embed)

    async def mentioned(self,msg:discord.Message) -> None:
        dm_channel = self.get_channel(Jsondb.jdata['mentioned_channel'])
        embed=BotEmbed.general(name="BRS | 提及訊息",description=msg.jump_url)
        embed.add_field(name='訊息內容', value=msg.content, inline=True)
        embed.add_field(name='發送者', value=f"{msg.author}\n{msg.author.id}", inline=False)
        embed.add_field(name='來源頻道', value=f'{msg.channel}\n{msg.channel.id}', inline=True)
        embed.add_field(name='來源群組', value=f'{msg.guild}\n{msg.guild.id}', inline=True)
        await dm_channel.send(embed=embed)
    
    async def mention_everyone(self,msg:discord.Message) -> None:
        dm_channel = self.get_channel(Jsondb.jdata['mention_everyone_channel'])
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
        embed = BotEmbed.bot(self.bot,description=f"你好~我是星羽，你可以輸入 </help:1067700245015834638> 來查看所有指令的用法\n\n希望我能在discord上幫助到你喔~\n有任何建議、需求、協助與合作可以使用 </feedback:1067700244848058386> 指令\n\n支援伺服器：https://discord.gg/ye5yrZhYGF")
        embed.set_footer(text="此機器人由 威立 負責維護")
        return embed

#commands.Bot
#shard_count=1,
#command_prefix=commands.when_mentioned_or('b!'),
#command_prefix='b!',
#case_insensitive=True,

class Cog_Extension(commands.Cog):
    def __init__(self, bot:DiscordBot): 
        self.bot = bot

class StarCache:
    dict_type = ["dynamic_voice","voice_log"]
    list_type = ["dynamic_voice_room"]
    notify_community_type = [NotifyCommunityType.Twitch, NotifyCommunityType.Youtube, NotifyCommunityType.TwitchVideo, NotifyCommunityType.TwitchClip]

    def __init__(self):
        self.cache = {}
        self.set_data()

    def set_data(self):
        """設定或重置所有資料"""
        for t in self.dict_type:
            dbdata = sqldb.get_notify_channel_by_type(t)
            self[t] = self.generate_notify_channel_dbdata(dbdata)

        for t in self.list_type:
            if t == "dynamic_voice_room":
                self[t] = sqldb.get_all_dynamic_voice()
    
        self.update_notify_notify_community()

    @staticmethod
    def generate_notify_channel_dbdata(dbdata):
        dict = {}
        for data in dbdata:
            guildid = data['guild_id']
            channelid = data['channel_id']
            roleid = data['role_id']
            dict[guildid] = [channelid, roleid]
        return dict
    
    @staticmethod
    def generate_notify_community_dbdata(dbdata):
        lst = []
        for data in dbdata:
            if data['notify_name'] not in lst:
                lst.append(data['notify_name'])
        return lst

    def __setitem__(self, key, value):
        self.cache[key] = value

    def __delitem__(self, key):
        try:
            del self.cache[key]
        except KeyError:
            pass

    def __getitem__(self, key):
        try:
            value = self.cache[key]
            return value
        except KeyError:
            log.debug(f"cache KeyError: {key}")
            return None

    def update_dynamic_voice(self,add_channel=None,remove_channel=None):
        """更新動態語音頻道"""
        if add_channel and add_channel not in self.cache["dynamic_voice"]:
            self["dynamic_voice"].append(add_channel)
        if remove_channel:
            self["dynamic_voice"].remove(remove_channel)

    def update_dynamic_voice_room(self,add_channel=None,remove_channel=None):
        """更新動態語音房間"""
        if add_channel and add_channel not in self.cache["dynamic_voice_room"]:
            self["dynamic_voice_room"].append(add_channel)
        if remove_channel:
            self["dynamic_voice_room"].remove(remove_channel)

    def update_notify_channel(self,notify_type):
        """更新通知頻道"""
        if notify_type not in self.cache["dict_type"]:
            raise KeyError(f"Not implemented notify type: {notify_type}")
        dbdata = sqldb.get_notify_channel_by_type(notify_type)
        self[notify_type] = self.generate_notify_channel_dbdata(dbdata)

    def update_notify_notify_community(self,notify_type:NotifyCommunityType=None):
        """更新社群通知"""
        if notify_type:
            if notify_type not in self.cache["notify_community_type"]:
                raise KeyError(f"Not implemented notify type: {notify_type}")
            
            dbdata = sqldb.get_notify_community(notify_type.value)
            self[notify_type] = self.generate_notify_community_dbdata(dbdata)
        else:
            for t in self.notify_community_type:
                dbdata = sqldb.get_notify_community(t.value)
                self[t] = self.generate_notify_community_dbdata(dbdata)

    def getif_dynamic_voice_room(self,channel_id):
        """取得動態語音房間"""
        return channel_id if channel_id in self["dynamic_voice_room"] else None