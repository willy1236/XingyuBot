import discord
from discord.ext import commands
import json
from core.classes import Cog_Extension
from library import *

jdata = json.load(open('setting.json',mode='r',encoding='utf8'))

class debug(Cog_Extension):
    @commands.command()
    @commands.is_owner()
    async def embed(self,ctx,msg):
        embed=discord.Embed(title="Bot Radio Station",description=f'{msg}',color=0xc4e9ff)
        embed.set_footer(text='廣播電台 | 機器人全群公告')
        
        await ctx.send(embed=embed)

    @commands.command()
    @commands.is_owner()
    async def debug(self,ctx,role):
        role = await find.role(ctx,role)
        dict = {}
        dict[str(role.id)] = {}
        dict[str(role.id)]['name']=role.name
        dict[str(role.id)]['color']=role.color.to_rgb( )
        dict[str(role.id)]['time']=role.created_at.strftime('%Y%m%d')
        print(dict)

    @commands.command()
    @commands.is_owner()
    async def debug2(self,ctx,*arg):
        for i in arg:
            role = await find.role(ctx,i)
            r,g,b=random_color()
            color = discord.Colour.from_rgb(r,g,b)
            await role.edit(color=color)

    @commands.command()
    @commands.is_owner()
    async def debug3(self,ctx):
        await ctx.send


    @commands.command()
    async def test(self, ctx,arg):
        #print(self.bot.command(name='lottery').__call__)
        #self.bot.command(name='lottery')
        text = converter.time(arg)
        msg = await ctx.respond(text)
        print(msg)

    #@commands.slash_command(guild_ids=[613747262291443742,566533708371329024])  # Not passing in guild_ids creates a global slash command (might take an hour to register).
    #async def hi(self, ctx):
    #    await ctx.respond("Hi, this is a global slash command from a cog!")

    
    # @commands.command(enabled=False)
    # async def test(self,ctx,user=None):
    #     user = await find.user(ctx,user)
    #     await ctx.send(f"{user or '沒有找到用戶'}")
def setup(bot):
    bot.add_cog(debug(bot))