import discord
from discord.ext import commands
import json
from core.classes import Cog_Extension

with open('setting.json',mode='r',encoding='utf8') as jfile:
    jdata = json.load(jfile)

with open('command.json',mode='r',encoding='utf8') as jfile:
    comdata = json.load(jfile)

class info(Cog_Extension):
    # info
    @commands.command()
    async def info(self, ctx, arg):
        if arg == 'help':
            await ctx.send(comdata['co.info'])

        elif arg == 'crass_chat':
            await ctx.send(comdata['co.info.crass_chat'])
        
        elif arg == 'vpn':
            await ctx.send(comdata['co.info.vpn'])
        elif arg == 'vpn01':
            await ctx.send(comdata['co.info.vpn01'])
        
        else:
            await ctx.send('參數錯誤，請輸入!!info help取得幫助')

    @commands.command()
    async def help(self,ctx):
        bot_name = self.bot.user.name

        embed = discord.Embed(title=bot_name, description="目前可使用的指令如下:", color=0xeee657)
        embed.add_field(name="!!info <內容/help>", value="獲得相關資訊", inline=False)
        embed.add_field(name="!!sign", value="每日簽到(更多功能敬請期待)", inline=False)
        embed.add_field(name="!!lol <player> <玩家名稱>", value="查詢LOL戰績(更多功能敬請期待)", inline=False)
        #embed.add_field(name="!!osu <player> <玩家名稱>", value="查詢Osu玩家(更多功能敬請期待)", inline=False)
        

        await ctx.send(embed=embed)
    
    @commands.command()
    @commands.is_owner()
    async def help_owner(self,ctx):
        bot_name = self.bot.user.name

        embed = discord.Embed(title=bot_name, description="目前可使用的指令如下(onwer):", color=0xeee657)
        embed.add_field(name="!!send <頻道ID> <內容>", value="發送指定訊息", inline=False)
        embed.add_field(name="!!all_anno <內容>", value="對所有伺服器進行公告", inline=False)
        
        await ctx.send(embed=embed)

    @commands.command()
    async def help_admin(self,ctx):
        bot_name = self.bot.user.name

        embed = discord.Embed(title=bot_name, description="目前可使用的指令如下(admin):", color=0xeee657)
        embed.add_field(name="!!clean <數字>", value="清除訊息(需求管理訊息)", inline=False)
        
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(info(bot))