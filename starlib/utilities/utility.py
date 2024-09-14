from datetime import datetime, timedelta

import discord

from ..fileDatabase import Jsondb
from .funtions import find


class BotEmbed:
    @staticmethod
    def bot(bot:discord.Bot,title:str=None,description:str=None,url=None):
        '''機器人 格式'''
        embed = discord.Embed(title=title, description=description, color=0xc4e9ff, url=url)
        embed.set_author(name=bot.user.name,icon_url=bot.user.display_avatar.url)
        return embed
    
    @staticmethod
    def user(user:discord.User,title:str=None,description:str=None,url=None):
        '''使用者 格式'''
        embed = discord.Embed(title=title, description=description, color=0x00ffff,url=url)
        embed.set_author(name=user.name,icon_url=user.display_avatar.url)
        return embed
    
    @staticmethod
    def simple(title:str=None,description:str=None,url=None):
        '''簡易:不帶作者'''
        embed = discord.Embed(title=title, description=description, color=0xc4e9ff,url=url)
        return embed

    @staticmethod
    def general(name:str=None,icon_url:str=None,url:str=None,title:str=None,description:str=None):
        '''普通:自訂作者'''
        embed = discord.Embed(title=title, description=description, color=0xc4e9ff)
        embed.set_author(name=name,icon_url=icon_url,url=url)
        return embed
    
    @staticmethod
    def rpg(title:str=None,description:str=None):
        """RPG系統 格式"""
        embed = discord.Embed(title=title, description=description, color=0xc4e9ff)
        embed.set_footer(text= "RPG系統（開發版） | 開發時期所有東西皆有可能重置")
        return embed

    @staticmethod
    def brs():
        '''Bot Radio System 格式'''
        picdata = Jsondb.picdata
        embed = discord.Embed(color=0xc4e9ff)
        embed.set_author(name="Bot Radio System", icon_url=picdata['radio_001'])
        return embed

    @staticmethod
    def lottery():
        '''Lottery System格式'''
        picdata = Jsondb.picdata
        embed = discord.Embed(color=0xc4e9ff)
        embed.set_author(name="Lottery System", icon_url=picdata['lottery_001'])
        return embed
    
    @staticmethod
    def star_radio():
        '''星系電台 格式'''
        picdata = Jsondb.picdata
        embed = discord.Embed(color=0xc4e9ff)
        embed.set_author(name="Star Rd.", icon_url=picdata['radio_001'])
        return embed
    
    @staticmethod
    def sts():
        '''星光終端系統 格式'''
        picdata = Jsondb.picdata
        embed = discord.Embed(color=0xc4e9ff)
        embed.set_author(name="「星光」終端系統", icon_url=picdata['radio_001'])
        return embed
    
    @staticmethod
    def info(title:str=None,description:str=None,url:str=None):
        '''一般資訊 格式'''
        embed = discord.Embed(title=title, description=description, color=0xc4e9ff,url=url)
        return embed
    
    @staticmethod
    def simple_warn_sheet(warn_user:discord.User, moderate_user:discord.User, create_at:datetime=None, last=timedelta(seconds=15), reason:str=None, title="已被禁言"):
        '''簡易警告表格'''
        if create_at is None:
            create_at = datetime.now()
        timestamp = int((create_at + last).timestamp())
        embed = discord.Embed(description=f"{warn_user.mention}：{reason}", color=0xc4e9ff)
        embed.set_author(name=f"{warn_user.name} {title}",icon_url=warn_user.display_avatar.url)
        embed.add_field(name="執行人員",value=moderate_user.mention)
        embed.add_field(name="結束時間",value=f"<t:{timestamp}>（{last.total_seconds():0f}s）")
        embed.timestamp = create_at
        return embed
class ChoiceList():
    @staticmethod
    def set(option_name):
        return [discord.OptionChoice(name=name_loc.get("en-US",name_loc.get("zh-TW")),
                                     value=value, 
                                     name_localizations=name_loc
                                     ) for value, name_loc in Jsondb.options[option_name].items()
                ]
        if Jsondb.jdict[option_name].get(lcode):
            for value,name in Jsondb.jdict[option_name][lcode].items():
                list.append()
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
        if Jsondb.jdict.get(option_name):
            if Jsondb.jdict[option_name].get("zh-TW"):
                return Jsondb.jdict[option_name]["zh-TW"].get(str(value),value)
            else:
                return Jsondb.jdict[option_name].get(str(value),value)
            
        else:
            if Jsondb.options[option_name].get(str(value)):
                return Jsondb.options[option_name][str(value)]["zh-TW"]
            else:
                return value

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
        return timedelta(days=days,hours=hours,minutes=minutes,seconds=seconds)
    
async def create_only_role_list(text:str,ctx):
    """投票系統：建立限制投票身分組清單"""
    only_role_list = []
    for i in text.split(","):
        role = await find.role(ctx,i)
        if role:
            only_role_list.append(role.id)
    return only_role_list

async def create_role_magification_dict(text:str,ctx):
    """投票系統：建立身分組權重列表"""
    role_magnification_dict = {}
    text = text.split(",")
    for i in range(0,len(text),2):
        role = await find.role(ctx,text[i])
        if role:
            role_magnification_dict[role.id] = int(text[i+1])
    return role_magnification_dict

def calculate_eletion_session(current_date:datetime) -> int:
    """選舉屆數計算器"""
    start_date = datetime(2023, 10, 11)
    return (current_date.year - start_date.year) * 12 + current_date.month - start_date.month + 1