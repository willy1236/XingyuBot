import discord
from discord.ext import commands
import random,asyncio
from discord.commands import SlashCommandGroup

from library import find,converter,random_color,BRS
from core.classes import Cog_Extension
from BotLib.database import Database
from BotLib.basic import BotEmbed

class slash(Cog_Extension):
    picdata = Database().picdata
    rsdata = Database().rsdata

    role = SlashCommandGroup("role", "身分組管理指令")

    @role.command(description='加身分組')
    @commands.cooldown(rate=1,per=5)
    async def add(self,
                ctx:discord.ApplicationContext,
                name:discord.Option(str,name='身分組名'),
                user_list:discord.Option(str,required=False,name='要加身份組的用戶',description='多個用戶請用空格隔開，若無則留空')
                ):
        await ctx.defer()
        permission = discord.Permissions.none()
        r,g,b=random_color(200)
        color = discord.Colour.from_rgb(r,g,b)
        new_role = await ctx.guild.create_role(name=name,permissions=permission,color=color)
        if user_list:
            user_list = user_list.split()
            for user in user_list:
                user = await find.user(ctx,user)
                if user and user != self.bot.user:
                    await user.add_roles(new_role,reason='指令:加身分組')
                elif user == self.bot.user:
                    await ctx.send("請不要加我身分組好嗎")
                elif user.bot:
                    await ctx.send("請不要加機器人身分組好嗎")
        await ctx.respond(f"添加完成，已創建 {new_role.name} 身分組")


    @commands.slash_command(description='向大家說哈瞜')
    async def hello(self,ctx, name: str = None):
        await ctx.defer()
        name = name or ctx.author.name
        await ctx.respond(f"Hello {name}!")

def setup(bot):
    bot.add_cog(slash(bot))
    