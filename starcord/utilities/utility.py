import discord,datetime
from starcord.FileDatabase import Jsondb

class BotEmbed:
    @staticmethod
    def bot(bot:discord.Bot,title:str=discord.Embed.Empty,description:str=discord.Embed.Empty,url=discord.Embed.Empty):
        '''機器人 格式'''
        embed = discord.Embed(title=title,description=description, color=0xc4e9ff,url=url)
        embed.set_author(name=bot.user.name,icon_url=bot.user.display_avatar.url)
        return embed
    
    @staticmethod
    def simple(title:str=discord.Embed.Empty,description:str=discord.Embed.Empty,url=discord.Embed.Empty):
        '''簡易:不帶作者'''
        embed = discord.Embed(title=title,description=description or discord.Embed.Empty, color=0xc4e9ff,url=url)
        return embed

    @staticmethod
    def general(name:str=discord.Embed.Empty,icon_url:str=discord.Embed.Empty,url:str=discord.Embed.Empty,title:str=discord.Embed.Empty,description:str=discord.Embed.Empty):
        '''普通:自訂作者'''
        embed = discord.Embed(title=title,description=description or discord.Embed.Empty,color=0xc4e9ff)
        embed.set_author(name=name,icon_url=icon_url,url=url)
        return embed
    
    @staticmethod
    def rpg(title:str=discord.Embed.Empty,description:str=discord.Embed.Empty):
        """RPG系統 格式"""
        embed = discord.Embed(title=title,description=description or discord.Embed.Empty, color=0xc4e9ff)
        embed.set_footer(text= "RPG系統（開發版） | 開發時期所有東西皆有可能重置")
        return embed

    @staticmethod
    def brs():
        '''Bot Radio System 格式'''
        picdata = Jsondb.picdata
        embed = discord.Embed(color=0xc4e9ff)
        embed.set_author(name="Bot Radio System",icon_url=picdata['radio_001'])
        return embed

    @staticmethod
    def lottery():
        '''Lottery System格式'''
        picdata = Jsondb.picdata
        embed = discord.Embed(color=0xc4e9ff)
        embed.set_author(name="Lottery System",icon_url=picdata['lottery_001'])
        return embed
    
    @staticmethod
    def star_radio():
        '''星系電台 格式'''
        picdata = Jsondb.picdata
        embed = discord.Embed(color=0xc4e9ff)
        embed.set_author(name="Star Rd.",icon_url=picdata['radio_001'])
        return embed
    
    @staticmethod
    def info(title:str=discord.Embed.Empty,description:str=discord.Embed.Empty,url:str=discord.Embed.Empty):
        '''一般資訊 格式'''
        embed = discord.Embed(title=title,description=description or discord.Embed.Empty, color=0xc4e9ff,url=url)
        return embed


class BRS():
    @staticmethod
    async def error(bot,ctx,error:str):
        error_report = bot.get_channel(Jsondb.jdata['error_report'])
        embed=BotEmbed.general(name="BRS | 錯誤回報")
        embed.add_field(name='錯誤訊息', value=f'```py\n{error}```', inline=True)
        if ctx.command:
            embed.add_field(name='使用指令', value=f'```{ctx.command}```', inline=False)
            embed.add_field(name='參數', value=f'```{ctx.selected_options}```', inline=False)
        embed.add_field(name='使用者', value=f"{ctx.author}\n{ctx.author.id}", inline=False)
        embed.add_field(name='發生頻道', value=f'{ctx.channel}\n{ctx.channel.id}', inline=True)
        embed.add_field(name='發生群組', value=f'{ctx.guild}\n{ctx.guild.id}', inline=True)
        await error_report.send(embed=embed)

    @staticmethod
    async def report(bot,msg):
        report_channel = bot.get_channel(Jsondb.jdata['report_channel'])
        embed=BotEmbed.general(name="BRS | 回報訊息")
        embed.add_field(name='訊息', value=msg, inline=True)
        await report_channel.send(embed=embed)

    @staticmethod
    async def feedback(self,ctx,msg):
        feedback_channel = self.bot.get_channel(Jsondb.jdata['feedback_channel'])
        embed=BotEmbed.general(name="BRS | 回饋訊息")
        embed.add_field(name='訊息內容', value=msg, inline=True)
        embed.add_field(name='發送者', value=f"{ctx.author}\n{ctx.author.id}", inline=False)
        embed.add_field(name='來源頻道', value=f'{ctx.channel}\n{ctx.channel.id}', inline=True)
        embed.add_field(name='來源群組', value=f'{ctx.guild}\n{ctx.guild.id}', inline=True)
        await feedback_channel.send(embed=embed)

    @staticmethod
    async def dm(bot,msg):
        dm_channel = bot.get_channel(Jsondb.jdata['dm_channel'])
        embed=BotEmbed.general(name="BRS | 私人訊息")
        embed.add_field(name='訊息內容', value=msg.content, inline=True)
        if msg.channel.recipient:
            embed.add_field(name='發送者', value=f"{msg.author}->{msg.channel.recipient}\n{msg.author.id}->{msg.channel.recipient.id}", inline=False)
        else:
            embed.add_field(name='發送者', value=f"{msg.author}\n{msg.author.id}", inline=False)
        await dm_channel.send(embed=embed)

    @staticmethod
    async def mentioned(bot,msg:discord.Message):
        dm_channel = bot.get_channel(Jsondb.jdata['mentioned_channel'])
        embed=BotEmbed.general(name="BRS | 提及訊息",description=f"https://discord.com/channels/{msg.guild.id}/{msg.channel.id}/{msg.id}")
        embed.add_field(name='訊息內容', value=msg.content, inline=True)
        embed.add_field(name='發送者', value=f"{msg.author}\n{msg.author.id}", inline=False)
        embed.add_field(name='來源頻道', value=f'{msg.channel}\n{msg.channel.id}', inline=True)
        embed.add_field(name='來源群組', value=f'{msg.guild}\n{msg.guild.id}', inline=True)
        await dm_channel.send(embed=embed)
    
    @staticmethod
    async def mention_everyone(bot,msg:discord.Message):
        dm_channel = bot.get_channel(Jsondb.jdata['mention_everyone_channel'])
        embed=BotEmbed.general(name="BRS | 提及所有人訊息",description=f"https://discord.com/channels/{msg.guild.id}/{msg.channel.id}/{msg.id}")
        embed.add_field(name='訊息內容', value=msg.content, inline=True)
        embed.add_field(name='發送者', value=f"{msg.author}\n{msg.author.id}", inline=False)
        embed.add_field(name='來源頻道', value=f'{msg.channel}\n{msg.channel.id}', inline=True)
        embed.add_field(name='來源群組', value=f'{msg.guild}\n{msg.guild.id}', inline=True)
        await dm_channel.send(embed=embed)

class ChoiceList():
    @staticmethod
    def set(option_name,lcode:str="zh-TW"):
        list = []
        if Jsondb.jdict[option_name].get(lcode):
            for value,name in Jsondb.jdict[option_name][lcode].items():
                list.append(discord.OptionChoice(name=name,value=value))
            return list
        else:
            for value,name in Jsondb.jdict[option_name].items():
                list.append(discord.OptionChoice(name=name,value=value))
            return list
    
    @staticmethod
    def set_with_localizations(option_name):
        list = []
        for option in Jsondb.jdict[option_name]['zh-TW']:
            dict = {}
            for lcode in Jsondb.jdict[option_name]:
                value = option
                name = Jsondb.jdict[option_name][lcode][value]
                dict[lcode] = name
            list.append(discord.OptionChoice(name=name,value=value,name_localizations=dict))
        return list

    @staticmethod
    def get_tw(value,option_name):
        if Jsondb.jdict[option_name].get("zh-TW"):
            return Jsondb.jdict[option_name]["zh-TW"].get(str(value),value)
        else:
            return Jsondb.jdict[option_name].get(str(value),value)

class converter():
    def time_to_sec(arg:str):
        '''10s->1,0用str相加 s則轉換後用int相乘'''
        dict = {'s':1,'m':60,'h':3600}
        n=0
        m=''
        for i in arg:
            try:
                int(i)
                m+=i
            except ValueError:
                try:
                    m=int(m)
                    n=n+(m*dict[i])
                    m=''
                except KeyError:
                    raise KeyError
        return n
    
    def time_to_datetime(arg:str): 
        m = ""
        days = 0
        hours = 0
        minutes = 0
        seconds = 0
        for i in arg:
            try:
                int(i)
                m+=i
            except ValueError:
                m=int(m)
                if i == "d":
                    days = m
                elif i == "h":
                    hours = m
                elif i == "m":
                    minutes = m
                elif i == "s":
                    seconds = m
                m=''
        return datetime.timedelta(days=days,hours=hours,minutes=minutes,seconds=seconds)