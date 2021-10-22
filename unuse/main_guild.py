import discord
from discord.ext import commands
import json
from core.classes import Cog_Extension

with open('setting.json',mode='r',encoding='utf8') as jfile:
    jdata = json.load(jfile)

class main_guild(Cog_Extension):
    @commands.command()
    async def room(self,ctx):
        print("1")
        if ctx.guild.id == int(jdata['main_guild']):
            name = f'私人房間 {ctx.author.name}'
            guild = ctx.guild
            category = discord.utils.get(guild.categories, id=768121309779197974)

            overwrites = {
            ctx.author: discord.PermissionOverwrite(manage_roles=True,manage_channels=True),
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            guild.me: discord.PermissionOverwrite(read_messages=True)
            }
            
            await guild.create_text_channel(name, overwrites=overwrites,category=category)
            await ctx.send(f'{ctx.author.mention} 頻道已創立!')
            #ctx.author:discord.PermissionOverwrite(manage_roles=True,manage_channels=True)

    @commands.command()
    async def b(self,ctx):
        print(categorier)

def setup(bot):
    bot.add_cog(main_guild(bot))