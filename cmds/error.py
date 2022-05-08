import discord
from discord.ext import commands
from library import BRS
from core.classes import Cog_Extension


class error(Cog_Extension):
    @commands.Cog.listener()
    async def on_command_error(self,ctx,error):
        if hasattr(ctx.command,'on_error'):
            return

        if isinstance(error,commands.errors.MissingRequiredArgument):
            await ctx.send(f'遺失參數:遺失 {error.param} 參數')
            print("遺失參數:",error.param)
        elif isinstance(error,commands.errors.ArgumentParsingError):
            await ctx.send('參數錯誤:給予了錯誤參數')
            print("錯誤參數:",error)
        elif isinstance(error,commands.errors.BadArgument):
            await ctx.send('參數錯誤:找不到此參數')
        elif isinstance(error,commands.errors.CommandNotFound):
            await ctx.send('沒找到指令:請確認指令是否輸入錯誤')
        elif isinstance(error,commands.errors.MissingPermissions):
            await ctx.send(f'缺少權限:你沒有權限來使用此指令\n缺少權限:{error.missing_permissions}')
        elif isinstance(error,commands.errors.BotMissingPermissions):
            await ctx.send(f'缺少權限:機器人沒有權限來使用此指令\n缺少權限:{error.missing_permissions}')
            print("缺少權限:",error.missing_permissions)
        elif isinstance(error,commands.errors.NotOwner):
            await ctx.send('缺少權限:你不是機器人擁有者',delete_after=5)
        elif isinstance(error,commands.errors.CommandOnCooldown):
            await ctx.send(f'尚在冷卻:指令還在冷卻中(尚須{int(error.retry_after)}秒)',delete_after=5)
        elif isinstance(error,commands.errors.CommandInvokeError):
            await ctx.send(f'指令調用時發生錯誤:{error.original}',delete_after=5)

        elif isinstance(error,commands.errors.DisabledCommand):
            await ctx.send('禁用指令:此指令目前無法被使用',delete_after=5)
        elif isinstance(error,commands.errors.TooManyArguments):
            await ctx.send('參數過多:給入過多參數')

        elif isinstance(error,discord.HTTPException):
            await ctx.send(f'HTTP錯誤:{error.response.status}錯誤')
            print(error.response.status,error.message)
        
        else:
            if ctx.guild.id != 566533708371329024:
                await BRS.error(self,ctx,error)
            await ctx.send(f'發生錯誤\n```{error}```')
            print(error,type(error))

def setup(bot):
    bot.add_cog(error(bot))