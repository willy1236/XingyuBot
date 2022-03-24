import discord
from discord.ext import commands
import json
from core.classes import Cog_Extension
from library import *

jdata = json.load(open('setting.json',mode='r',encoding='utf8'))
rsdata = Counter(json.load(open('database/role_save.json',mode='r',encoding='utf8')))

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
        dict[str(role.id)]['color']=role.color.to_rgb()
        dict[str(role.id)]['time']=role.created_at.strftime('%Y%m%d')
        print(dict)

    @commands.command()
    @commands.is_owner()
    async def rolesave(self,ctx):
        for user in ctx.guild.get_role(877934319249797120).members:
            dict = rsdata
            roledata = dict[str(user.id)] or {}
            start = 0
            for i in range(len(user.roles)-1,0,-1):
                role = user.roles[i]
                if role.id == 877934319249797120:
                    start = 1
                    continue
                if role.name == '@everyone':
                    continue
                if start == 1:
                    roledata[str(role.id)] = [role.name,role.color.to_rgb(),role.created_at.strftime('%Y%m%d')]
                dict[str(user.id)] = roledata
            with open('database/role_save.json',mode='w',encoding='utf8') as jfile:
                json.dump(dict,jfile,indent=4)

    @commands.command()
    @commands.is_owner()
    async def rsmove(self,ctx):
        for user in ctx.guild.get_role(877934319249797120).members:
            print(user.name)
            for role in user.roles:
                if role.id == 877934319249797120:
                    break
                if role.name == '@everyone':
                    continue
                print(f'已移除:{role.name}')
                await role.remove()
                

    @commands.command()
    async def test(self, ctx):
        await BRS.error(self,ctx,'test')

    
    # @commands.command(enabled=False)
    # async def test(self,ctx,user=None):
    #     user = await find.user(ctx,user)
    #     await ctx.send(f"{user or '沒有找到用戶'}")
def setup(bot):
    bot.add_cog(debug(bot))