import discord
from BotLib.database import JsonDatabase

class BotEmbed:
    @staticmethod
    def all_anno(msg:str):
        '''全群公告'''
        picdata = JsonDatabase().picdata
        embed=discord.Embed(description=msg,color=0xc4e9ff)
        embed.set_author(name="Bot Radio Station",icon_url=picdata['radio_001'])
        embed.set_footer(text='廣播電台 | 機器人全群公告')
        return embed

    def basic(self,description:str=discord.Embed.Empty,title:str=discord.Embed.Empty,url=discord.Embed.Empty):
        '''基本:作者帶機器人名稱'''
        embed = discord.Embed(title=title,description=description, color=0xc4e9ff,url=url)
        embed.set_author(name=self.bot.user.name,icon_url=self.bot.user.display_avatar.url)
        return embed
    
    def simple(description:str=discord.Embed.Empty,title:str=discord.Embed.Empty,url=discord.Embed.Empty):
        '''簡易:不帶作者'''
        embed = discord.Embed(title=title,description=description, color=0xc4e9ff,url=url)
        return embed

    def general(name:str,icon_url:str=discord.Embed.Empty,url:str=discord.Embed.Empty):
        '''普通:自訂作者'''
        embed = discord.Embed(color=0xc4e9ff)
        embed.set_author(name=name,icon_url=icon_url,url=url)
        return embed

    def brs():
        '''Bot Radio Station 格式'''
        picdata = JsonDatabase().picdata
        embed = discord.Embed(color=0xc4e9ff)
        embed.set_author(name="Bot Radio Station",icon_url=picdata['radio_001'])
        return embed

    def lottery():
        '''Lottery System格式'''
        picdata = JsonDatabase().picdata
        embed = discord.Embed(color=0xc4e9ff)
        embed.set_author(name="Lottery System",icon_url=picdata['lottery_001'])
        return embed
    
    @staticmethod
    def bot_update(msg:str):
        '''Bot Update格式'''
        picdata = JsonDatabase().picdata
        embed = discord.Embed(description=msg,color=0xc4e9ff)
        embed.set_author(name="Bot Radio Station",icon_url=picdata['radio_001'])
        embed.set_footer(text='廣播電台 | 機器人更新通知')
        return embed


class BRS():
    async def error(self,ctx,error:str):
        jdata = JsonDatabase().jdata
        report_channel = self.bot.get_channel(jdata['report_channel'])
        embed=BotEmbed.general(name="BRS | 錯誤回報")
        embed.add_field(name='錯誤指令', value=f'```py\n{error}```', inline=True)
        if ctx.message:
            embed.add_field(name='使用指令', value=f'```{ctx.message.content}```', inline=False)
        embed.add_field(name='使用者', value=f"{ctx.author}\n{ctx.author.id}", inline=False)
        embed.add_field(name='發生頻道', value=f'{ctx.channel}\n{ctx.channel.id}', inline=True)
        embed.add_field(name='發生群組', value=f'{ctx.guild}\n{ctx.guild.id}', inline=True)
        await report_channel.send(embed=embed)
    
    async def scam(self,msg,Matchs=None):
        jdata = JsonDatabase().jdata
        scam_channel = self.bot.get_channel(jdata['scam_channel'])
        embed=BotEmbed.general(name="BRS | 詐騙回報")
        embed.add_field(name='詐騙訊息', value=msg.content, inline=True)
        embed.add_field(name='發送者', value=f"{msg.author}\n{msg.author.id}", inline=False)
        embed.add_field(name='發生頻道', value=f'{msg.channel}\n{msg.channel.id}', inline=True)
        embed.add_field(name='發生群組', value=f'{msg.guild}\n{msg.guild.id}', inline=True)
        if Matchs:
            embed.add_field(name='關鍵字', value=Matchs, inline=True)
        await scam_channel.send(embed=embed)

    async def feedback(self,ctx,msg):
        jdata = JsonDatabase().jdata
        feedback_channel = self.bot.get_channel(jdata['feedback_channel'])
        embed=BotEmbed.general(name="BRS | 回饋訊息")
        embed.add_field(name='訊息內容', value=msg, inline=True)
        embed.add_field(name='發送者', value=f"{ctx.author}\n{ctx.author.id}", inline=False)
        embed.add_field(name='來源頻道', value=f'{ctx.channel}\n{ctx.channel.id}', inline=True)
        embed.add_field(name='來源群組', value=f'{ctx.guild}\n{ctx.guild.id}', inline=True)
        await feedback_channel.send(embed=embed)

    async def dm(self,msg):
        jdata = JsonDatabase().jdata
        dm_channel = self.bot.get_channel(jdata['dm_channel'])
        embed=BotEmbed.general(name="BRS | 私人訊息")
        embed.add_field(name='訊息內容', value=msg.content, inline=True)
        if msg.channel.recipient:
            embed.add_field(name='發送者', value=f"{msg.author}->{msg.channel.recipient}\n{msg.author.id}->{msg.channel.recipient.id}", inline=False)
        else:
            embed.add_field(name='發送者', value=f"{msg.author}\n{msg.author.id}", inline=False)
        await dm_channel.send(embed=embed)

    async def mentioned(self,msg):
        jdata = JsonDatabase().jdata
        dm_channel = self.bot.get_channel(jdata['mentioned_channel'])
        embed=BotEmbed.general(name="BRS | 提及訊息")
        embed.add_field(name='訊息內容', value=msg.content, inline=True)
        embed.add_field(name='發送者', value=f"{msg.author}\n{msg.author.id}", inline=False)
        embed.add_field(name='來源頻道', value=f'{msg.channel}\n{msg.channel.id}', inline=True)
        embed.add_field(name='來源群組', value=f'{msg.guild}\n{msg.guild.id}', inline=True)
        await dm_channel.send(embed=embed)
    
    async def mention_everyone(self,msg):
        jdata = JsonDatabase().jdata
        dm_channel = self.bot.get_channel(jdata['mention_everyone_channel'])
        embed=BotEmbed.general(name="BRS | 提及所有人訊息")
        embed.add_field(name='訊息內容', value=msg.content, inline=True)
        embed.add_field(name='發送者', value=f"{msg.author}\n{msg.author.id}", inline=False)
        embed.add_field(name='來源頻道', value=f'{msg.channel}\n{msg.channel.id}', inline=True)
        embed.add_field(name='來源群組', value=f'{msg.guild}\n{msg.guild.id}', inline=True)
        await dm_channel.send(embed=embed)