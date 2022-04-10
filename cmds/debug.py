import discord,json,requests
from discord.ext import commands
from core.classes import Cog_Extension
from library import *

class debug(Cog_Extension):
    rsdata = Counter(json.load(open('database/role_save.json',mode='r',encoding='utf8')))
    
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
        dict[str(role.id)]['color']=role.color.to_rgb()
        dict[str(role.id)]['time']=role.created_at.strftime('%Y%m%d')
        print(dict)
                

    @commands.command()
    async def test(self, ctx):
        url = 123
       

    
    # @commands.command(enabled=False)
    # async def test(self,ctx,user=None):
    #     user = await find.user(ctx,user)
    #     await ctx.send(f"{user or '沒有找到用戶'}")
def setup(bot):
    bot.add_cog(debug(bot))