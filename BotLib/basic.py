import discord
from BotLib.database import Database

class BotEmbed:
    @staticmethod
    def all_anno(msg:str):
        '''全群公告'''
        picdata = Database().picdata
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
        picdata = Database().picdata
        embed = discord.Embed(color=0xc4e9ff)
        embed.set_author(name="Bot Radio Station",icon_url=picdata['radio_001'])
        return embed

    def lottery():
        '''Lottery System格式'''
        picdata = Database().picdata
        embed = discord.Embed(color=0xc4e9ff)
        embed.set_author(name="Lottery System",icon_url=picdata['lottery_001'])
        return embed
    
    @staticmethod
    def bot_update(msg:str):
        '''Bot Update格式'''
        picdata = Database().picdata
        embed = discord.Embed(description=msg,color=0xc4e9ff)
        embed.set_author(name="Bot Radio Station",icon_url=picdata['radio_001'])
        embed.set_footer(text='廣播電台 | 機器人更新通知')
        return embed