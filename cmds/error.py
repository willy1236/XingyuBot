import discord
from discord.ext import commands
from mysql.connector.errors import Error as sqlerror
from starcord.errors import *
from starcord import Cog_Extension,log,BRS,Jsondb

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
            permissions = [permissions_tl.get(i,i) for i in error.missing_permissions]
            text = ','.join(permissions)
            await ctx.respond(f'缺少權限:你沒有權限來使用此指令\n缺少權限: {text}',ephemeral=True)
        elif isinstance(error,commands.errors.BotMissingPermissions):
            permissions = [permissions_tl.get(i,i) for i in error.missing_permissions]
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
                await ctx.respond(f'發生未知錯誤：```py\n{error.original}```',ephemeral=True)
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

def setup(bot):
    bot.add_cog(error(bot))