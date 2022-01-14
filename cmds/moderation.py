import discord
from discord.ext import commands
import json
from core.classes import Cog_Extension
from library import find

cdata = json.load(open("channel_settings.json", "r",encoding="utf-8"))

class moderation(Cog_Extension):
    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def clean(self,ctx,num:int):
        await ctx.channel.purge(limit=num+1)
        await ctx.send(content=f'清除完成，清除了{num}則訊息',delete_after=5)

    @commands.group(invoke_without_command=True)
    async def set(self,ctx):
        pass

    @set.command()
    async def crass_chat(self,ctx,channel='remove'):
        if channel != 'remove':
            channel = await find.channel(ctx,channel)
        guild = str(ctx.guild.id)
        
        if channel == 'remove':
            if guild in cdata['crass_chat']:
                with open('channel_settings.json','w+',encoding='utf8') as f:
                    del cdata['crass_chat'][guild]
                    json.dump(cdata,f,indent=4)
                await ctx.send(f'設定完成，已移除跨群聊天頻道')
            else:
                await ctx.send('此伺服器還沒有設定頻道喔')

        elif channel != None:
            with open('channel_settings.json','w+',encoding='utf8') as f:
                cdata['crass_chat'][guild] = channel.id
                json.dump(cdata,f,indent=4)
            await ctx.send(f'設定完成，已將跨群聊天頻道設為{channel.mention}')

    @set.command()
    async def all_anno(self,ctx,channel='remove'):
        if channel != 'remove':
            channel = await find.channel(ctx,channel)
        guild = str(ctx.guild.id)
        
        if channel == 'remove':
            if guild in cdata['all_anno']:
                with open('channel_settings.json','w+',encoding='utf8') as f:
                    del cdata['all_anno'][guild]
                    json.dump(cdata,f,indent=4)
                await ctx.send(f'設定完成，已移除全群公告頻道')
            else:
                await ctx.send('此伺服器還沒有設定頻道喔')

        elif channel != None:
            with open('channel_settings.json','w+',encoding='utf8') as f:
                cdata['all_anno'][guild] = channel.id
                json.dump(cdata,f,indent=4)
            await ctx.send(f'設定完成，已將全群公告頻道設為{channel.mention}')

def setup(bot):
    bot.add_cog(moderation(bot))