import discord
from discord.ext import commands
import random,asyncio
from discord.commands import SlashCommandGroup

from BotLib.funtions import find,converter,random_color,BRS
from core.classes import Cog_Extension
from BotLib.database import Database
from BotLib.basic import BotEmbed

class slash(Cog_Extension):
    picdata = Database().picdata
    rsdata = Database().rsdata

    role = SlashCommandGroup("role", "身分組管理指令",guild_only=True,guild_ids=[566533708371329024])

    @role.command(description='加身分組')
    @commands.cooldown(rate=1,per=5)
    async def add(self,
                ctx:discord.ApplicationContext,
                name:discord.Option(str,name='身分組名',description='新身分組名稱'),
                user_list:discord.Option(str,required=False,name='要加身份組的用戶',description='多個用戶請用空格隔開，若無則留空')
                ):
        await ctx.defer()
        permission = discord.Permissions.none()
        r,g,b=random_color(200)
        color = discord.Colour.from_rgb(r,g,b)
        new_role = await ctx.guild.create_role(name=name,permissions=permission,color=color)
        added_role = []
        if user_list:
            user_list = user_list.split()
            for user in user_list:
                user = await find.user(ctx,user)
                if user and user != self.bot.user:
                    await user.add_roles(new_role,reason='指令:加身分組')
                    added_role.append(user)
                elif user == self.bot.user:
                    await ctx.send("請不要加我身分組好嗎")
                elif user.bot:
                    await ctx.send("請不要加機器人身分組好嗎")
        if added_role != []:
            all_user = ''
            for user in added_role:
                all_user += f' {user.mention}'
            await ctx.respond(f"已添加 {new_role.name} 給{all_user}")
        else:
            await ctx.respond(f"已創建 {new_role.name} 身分組")


    @commands.slash_command(description='向大家說哈瞜')
    async def hello(self,ctx, name: str = None):
        await ctx.defer()
        name = name or ctx.author.name
        await ctx.respond(f"Hello {name}!")

def setup(bot):
    bot.add_cog(slash(bot))
    