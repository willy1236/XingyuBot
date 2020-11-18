import discord
from discord.ext import commands
import json
from core.classes import Cog_Extension

with open('setting.json',mode='r',encoding='utf8') as jfile:
    jdata = json.load(jfile)

with open('command.json',mode='r',encoding='utf8') as jfile:
    comdata = json.load(jfile)

class main_guild(Cog_Extension):
    @commands.command()
    async def room(self,ctx):
        print("1")
        if ctx.guild.id == int(jdata['main_guild']):
            print("2")
            name = f'私人房間 {ctx.author.name}'
            print("3")
            guild = ctx.guild
            #print("3-2")
            overwrites = {
            ctx.author: discord.PermissionOverwrite(manage_roles=True,manage_channels=True),
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            guild.me: discord.PermissionOverwrite(read_messages=True)
            }
            print("4")
            category = id(693484159833735269)
            print("5")            
            await guild.create_text_channel(name, overwrites=overwrites,category=id(category))
            print("6")
            
            await ctx.send(f'{ctx.author.mention} 頻道已創立!')
            print('ids')
            #ctx.author:discord.PermissionOverwrite(manage_roles=True,manage_channels=True)

    @commands.command()
    async def b(self,ctx):
        print(categorier)

def setup(bot):
    bot.add_cog(main_guild(bot))