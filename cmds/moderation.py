import discord
from discord.ext import commands
from core.classes import Cog_Extension
from BotLib.funtions import find
from BotLib.database import Database


class moderation(Cog_Extension):
    cdata = Database().cdata
    
    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def clean(self,ctx,num:int):
        await ctx.channel.purge(limit=num+1)
        await ctx.send(content=f'清除完成，清除了{num}則訊息',delete_after=5)

    @commands.group(invoke_without_command=True)
    @commands.has_permissions(manage_channels=True)
    async def set(self,ctx,set_type,channel='remove'):
        dict = {
            'crass_chat':'跨群聊天',
            'all_anno':'全群公告',
            'earthquake':'地震通知',
            'apex_crafting':'Apex合成物品更新',
            'apex_map':'apex地圖輪替',
            'covid_update':'台灣每日疫情通知',
            'forecast':'台灣各縣市天氣預報',
            'bot':'機器人更新通知'
        }
        if set_type not in dict:
            raise commands.errors.ArgumentParsingError('所選類別功能尚未加入')
        if channel != 'remove':
            channel = await find.channel(ctx,channel)
        guild = str(ctx.guild.id)
        if set_type not in self.cdata:
            self.cdata[set_type]={}
        
        if channel == 'remove':
            if guild in self.cdata[set_type]:
                del self.cdata[set_type][guild]
                Database().write('cdata',self.cdata)
                await ctx.send(f'設定完成，已移除{dict[set_type]}頻道')
            else:
                await ctx.send('此伺服器還沒有設定頻道喔')

        elif channel:
            self.cdata[set_type][guild] = channel.id
            Database().write('cdata',self.cdata)
            await ctx.send(f'設定完成，已將{dict[set_type]}頻道設為{channel.mention}')
        else:
            raise commands.errors.ArgumentParsingError('找不到頻道')

def setup(bot):
    bot.add_cog(moderation(bot))