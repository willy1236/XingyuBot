import discord
from discord.ext import commands
from core.classes import Cog_Extension


class error(Cog_Extension):
    @commands.Cog.listener()
    async def on_command_error(self,ctx,error):
        if hasattr(ctx.command,'on_error'):
            return

        if isinstance(error,commands.errors.MissingRequiredArgument):
            await ctx.send('遺失參數:缺少必要參數')
            print("遺失參數:",error.param)
        elif isinstance(error,commands.errors.ArgumentParsingError):
            await ctx.send('參數錯誤:給予了錯誤參數')
            print("錯誤參數:",error)
        elif isinstance(error,commands.errors.CommandNotFound):
            await ctx.send('沒找到指令:請確認指令是否輸入錯誤')
        elif isinstance(error,commands.errors.MissingPermissions):
            await ctx.send('缺少權限:你沒有權限來使用此指令')
        elif isinstance(error,commands.errors.BotMissingPermissions):
            await ctx.send('缺少權限:機器人沒有權限來使用此指令')
        elif isinstance(error,commands.errors.NotOwner):
            await ctx.send('缺少權限:你不是機器人擁有者')
        elif isinstance(error,commands.errors.CommandOnCooldown):
            await ctx.send(f'尚在冷卻:指令還在冷卻中(尚須{int(error.retry_after)}秒)',delete_after=5)
        
        elif isinstance(error,commands.errors.DisabledCommand):
            await ctx.send('禁用指令:此指令目前無法被使用')
        elif isinstance(error,commands.errors.TooManyArguments):
            await ctx.send('參數過多:給入過多參數')
        
        elif isinstance(error,KeyError):
            await ctx.send('參數缺失:發生KeyError錯誤')
        else:
            await ctx.send('發生未知錯誤，請向機器人擁有者回報')
            print(error)

    #@info.error
    #async def info_error(self,ctx,error):
    #    if isinstance(error,commands.errors.MissingRequiredArgument):
    #        await ctx.send('遺失參數:輸入!!info help以取得參數')

def setup(bot):
    bot.add_cog(error(bot))