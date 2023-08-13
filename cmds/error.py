import discord
from discord.ext import commands
from core.classes import Cog_Extension
from mysql.connector.errors import Error as sqlerror
from starcord.errors import *
from starcord import log,BRS,Jsondb,sqldb

permissions_tl = Jsondb.jdict.get('permissions')
debug_guild = Jsondb.jdata.get('debug_guild')
debug_mode = Jsondb.jdata.get('debug_mode')

class error(Cog_Extension):
    @commands.Cog.listener()
    async def on_application_command_error(self, ctx: discord.ApplicationContext, error: discord.DiscordException):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.respond(f'尚在冷卻:指令還在冷卻中(尚須{int(error.retry_after)}秒)',ephemeral=True)
        elif isinstance(error,commands.errors.NotOwner):
            await ctx.respond('缺少權限:你不是機器人擁有者',ephemeral=True)
        elif isinstance(error,commands.errors.MissingPermissions):
            permissions = []
            for i in error.missing_permissions:
                permissions.append(permissions_tl.get(i,i))
            text = ','.join(permissions)
            await ctx.respond(f'缺少權限:你沒有權限來使用此指令\n缺少權限: {text}',ephemeral=True)
        elif isinstance(error,commands.errors.BotMissingPermissions):
            permissions = []
            for i in error.missing_permissions:
                permissions.append(permissions_tl.get(i,i))    
            text = ','.join(permissions)
            await ctx.respond(f'缺少權限:我沒有權限來使用此指令\n缺少權限: {text}',ephemeral=True)

        elif isinstance(error,commands.errors.NoPrivateMessage):
            await ctx.respond(f'頻道錯誤：此指令不可在DM中使用',ephemeral=True)
        
        elif isinstance(error,discord.ApplicationCommandInvokeError):
            if isinstance(error.original,StarException):
                await ctx.respond(error.original,ephemeral=True)
                if error.original.original_message:
                    if debug_mode:
                        log.error(f'{error},{error.original.original_message},{type(error.original)}')
                    else:
                        await BRS.error(self.bot,ctx,f"{error.original} ({error.original.original_message})")

            elif isinstance(error.original,discord.errors.Forbidden):
                await ctx.respond(f'錯誤：我缺少權限執行這項操作，可能為我的身分組位階較低或缺少必要權限導致',ephemeral=True)

            elif isinstance(error.original,sqlerror) and error.original.errno == 1062:
                await ctx.respond(f'錯誤：資料重複新增',ephemeral=True)
            
            else:
                await ctx.respond(f'指令調用時發生錯誤，已自動回報：```py\n{error.original}```',ephemeral=True)
                if not ctx.guild or ctx.guild.id not in debug_guild:
                    await BRS.error(self.bot,ctx,error)

                log.error(f'{error},{type(error)},{type(error.original)}')
        
        elif isinstance(error,discord.ApplicationCommandError):
            await ctx.respond(f'{error}',ephemeral=True)
        
        elif isinstance(error,commands.errors.ArgumentParsingError):
            await ctx.respond(f'參數錯誤:{error}',ephemeral=True)
        
        else:
            if not ctx.guild or ctx.guild.id not in debug_guild:
                await BRS.error(self.bot,ctx,error)
            await ctx.respond(f'發生未知錯誤\n```{error.original}```',ephemeral=True)
            log.error(f'{error},{type(error)}')

    # @commands.Cog.listener()
    # async def on_command_error(self,ctx,error):
    #     if hasattr(ctx.command,'on_error'):
    #         return

    #     if isinstance(error,commands.errors.MissingRequiredArgument):
    #         await ctx.send(f'遺失參數:遺失 {error.param} 參數')
    #         print("遺失參數:",error.param)
    #     elif isinstance(error,commands.errors.ArgumentParsingError):
    #         await ctx.send(f'參數錯誤:{error}')
    #         print("錯誤參數:",error)
    #     elif isinstance(error,commands.errors.BadArgument):
    #         await ctx.send('參數錯誤:找不到此參數')
    #     elif isinstance(error,commands.errors.CommandNotFound):
    #         await ctx.send('沒找到指令:請確認指令是否輸入錯誤')
    #     elif isinstance(error,commands.errors.MissingPermissions):
    #         permissions = []
    #         for i in error.missing_permissions:
    #             permissions.append(dict.get(i,i))    
    #         text = ','.join(permissions)
    #         await ctx.send(f'缺少權限:你沒有權限來使用此指令\n缺少權限:{text}')
    #     elif isinstance(error,commands.errors.BotMissingPermissions):
    #         permissions = []
    #         for i in error.missing_permissions:
    #             permissions.append(dict.get(i,i))    
    #         text = ','.join(permissions)
    #         await ctx.send(f'缺少權限:機器人沒有權限來使用此指令\n缺少權限:{text}')
    #         print("缺少權限:",error.missing_permissions)
    #     elif isinstance(error,commands.errors.NotOwner):
    #         await ctx.send('缺少權限:你不是機器人擁有者',delete_after=5)
    #     elif isinstance(error,commands.errors.CommandOnCooldown):
    #         await ctx.send(f'尚在冷卻:指令還在冷卻中(尚須{int(error.retry_after)}秒)',delete_after=5)
    #     # elif isinstance(error,commands.errors.CommandInvokeError):
    #     #     await ctx.send(f'指令調用時發生錯誤:{error.original}',delete_after=5)
    #     elif isinstance(error,discord.errors.Forbidden):
    #         await BRS.error(self,ctx,error)

    #     elif isinstance(error,commands.errors.DisabledCommand):
    #         await ctx.send('禁用指令:此指令目前無法被使用',delete_after=5)
    #     elif isinstance(error,commands.errors.TooManyArguments):
    #         await ctx.send('參數過多:給入過多參數')

    #     elif isinstance(error,commands.errors.MemberNotFound):
    #         await ctx.send('找不到用戶:無此用戶或輸入錯誤')

    #     elif isinstance(error,discord.HTTPException):
    #         await ctx.send(f'HTTP錯誤:{error.response.status}錯誤')
    #         print(error.response.status,error.message)
        
    #     else:
    #         if ctx.guild.id != 566533708371329024:
    #             await BRS.error(self,ctx,error)
    #         await ctx.send(f'發生錯誤\n```{error}```')
    #         print(error,type(error))

def setup(bot):
    bot.add_cog(error(bot))