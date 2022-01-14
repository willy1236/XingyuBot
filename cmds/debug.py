import discord
from discord.ext import commands
import json
from core.classes import Cog_Extension
from library import converter,find

jdata = json.load(open('setting.json',mode='r',encoding='utf8'))

class debug(Cog_Extension):
    @commands.command()
    @commands.is_owner()
    async def embed(self,ctx,msg):
        embed=discord.Embed(title="Bot Radio Station",description=f'{msg}',color=0xc4e9ff)
        embed.set_footer(text='廣播電台 | 機器人全群公告')
        
        channel = self.bot.get_channel(870936349023285268)
        await ctx.send(embed=embed)

    @commands.command()
    @commands.is_owner()
    async def debug(self,ctx,role):
        role = await find.role(ctx,role)
        print(role.id,role.name,role.color,role.created_at)

    @commands.command()
    async def test(self, ctx,arg):
        #print(self.bot.command(name='lottery').__call__)
        #self.bot.command(name='lottery')
        text = converter.time(arg)
        await ctx.send(text)

    
    # @commands.command(enabled=False)
    # async def test(self,ctx,user=None):
    #     user = await find.user(ctx,user)
    #     await ctx.send(f"{user or '沒有找到用戶'}")
def setup(bot):
    bot.add_cog(debug(bot))