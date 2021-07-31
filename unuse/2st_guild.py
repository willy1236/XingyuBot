import discord
from discord.ext import commands
import json
from core.classes import Cog_Extension

with open('setting.json',mode='r',encoding='utf8') as jfile:
    jdata = json.load(jfile)

with open('command.json',mode='r',encoding='utf8') as jfile:
    comdata = json.load(jfile)

class two_st_guild(Cog_Extension):
    @commands.command()
    async def crroom(self,ctx):
        if ctx.guild.id == int(jdata['main_guild']):
            name = f'私人房間 {ctx.author.name}'
            guild = ctx.guild
            category = discord.utils.get(guild.categories, id=613754532262051861)

            overwrites = {
            ctx.author: discord.PermissionOverwrite(manage_roles=True,manage_channels=True),
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            guild.me: discord.PermissionOverwrite(read_messages=True)
            }
            
            await guild.create_text_channel(name, overwrites=overwrites,category=category)
            await ctx.send(f'{ctx.author.mention} 頻道已創立!')


def setup(bot):
    bot.add_cog(two_st_guild(bot))