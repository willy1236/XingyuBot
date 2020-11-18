import discord
from discord.ext import commands
import json
from core.classes import Cog_Extension
from cmds.info import info

with open('setting.json',mode='r',encoding='utf8') as jfile:
    jdata = json.load(jfile)

with open('command.json',mode='r',encoding='utf8') as jfile:
    comdata = json.load(jfile)

class error(Cog_Extension):
    @commands.Cog.listener()
    async def on_command_error(self,ctx,error):
        if hasattr(ctx.command,'on_error'):
            return

        if isinstance(error,commands.errors.MissingRequiredArgument):
            await ctx.send('遺失參數:缺少必要參數')
        elif isinstance(error,commands.errors.CommandNotFound):
            await ctx.send('沒找到指令:請確認指令是否輸入錯誤')
        else:
            await ctx.send(error)
            print(error)

    #@info.error
    #async def info_error(self,ctx,error):
    #    if isinstance(error,commands.errors.MissingRequiredArgument):
    #        await ctx.send('遺失參數:輸入!!info help以取得參數')
    
    #@info.error
    #async def comm_error(self,ctx,error):
    #    if isinstance(error,commands.errors.MissingRequiredArgument):
    #        await ctx.send('遺失參數:輸入!!comm help以取得參數')

def setup(bot):
    bot.add_cog(error(bot))