import discord
from discord.ext import commands
import json
from core.classes import Cog_Extension
from library import find,Counter
from BotLib.user import Point

jdata = json.load(open('setting.json',mode='r',encoding='utf8'))

class economy_system(Cog_Extension):
    @commands.group(invoke_without_command=True,aliases=['pt'])
    async def point(self,ctx,user=None):
        if user == None:
            pt = Point(ctx.author.id).pt
            await ctx.send(f'{user.mention} 你目前擁有 {pt} Pt點數', reference=ctx.message)
        else:
            user = await find.user(ctx,user)
            if user != None:
                pt = Point(user.id).pt
                await ctx.send(f'{user.name} 目前擁有 {pt} Pt點數', reference=ctx.message)
                if user.bot:
                    await ctx.send('溫馨提醒:機器人是沒有點數的喔',delete_after=5)
            else:
                await ctx.send('錯誤:找不到用戶', reference=ctx.message,delete_after=5)
            
    @point.command()
    async def give(self,ctx,give,amount:int):
        given = await find.user(ctx,give)
        if not given is None:
                giver = ctx.author
                if amount <= 0:
                    await ctx.message.delete()
                    await ctx.send(f'轉帳失敗:無法轉帳少於1Pt',delete_after=5)
                elif given == giver:
                    await ctx.message.delete()
                    await ctx.send(f'轉帳失敗:無法轉帳給自己',delete_after=5)
                elif given.bot == True:
                    await ctx.message.delete()
                    await ctx.send(f'轉帳失敗:無法轉帳給機器人',delete_after=5)
                elif Point(giver.id).pt < amount:
                    await ctx.message.delete()
                    await ctx.send(f'轉帳失敗:{ctx.author.mention}的Pt點數不足',delete_after=5)
                else:
                    Point(given.id).add(amount)
                    Point(giver.id).add(amount*-1)
                    await ctx.send(f'轉帳成功:{ctx.author.mention}已將 {amount} 點Pt轉給 {given.mention}')
        else:
            await ctx.message.delete()
            await ctx.send(content='錯誤:沒找到用戶，請填入用戶ID',delete_after=5)
    
    @commands.is_owner()
    @commands.command()
    async def ptset(self,ctx,user,mod,amount:int):
        user = await find.user(ctx,user)
        mod_list = ['+','-','set']
        if user is not None and mod in mod_list:
            pt = Point(user.id)
            pt_old = pt.pt
            if mod == '+':
                pt.add(amount)
            elif mod == '-':
                pt.add(amount*-1)
            elif mod == 'set':
                pt.set(amount)
            pt_new = pt.pt
            await ctx.send(f'設定成功:已將{user.mention}的Pt點數從 {pt_old} 設定為 {pt_new}')
        else:
            await ctx.send(f'錯誤:找不到用戶或模式輸入錯誤',delete_after=5)

    @commands.command()
    async def sign(self,ctx):
        await ctx.message.delete()
        jdsign = json.load(open('database/sign_day.json',mode='r',encoding='utf8'))
        jwsign = Counter(json.load(open('database/sign_week.json',mode='r',encoding='utf8')))
        
        if ctx.author.id not in jdsign:
            signer = str(ctx.author.id)
            #日常
            jdsign.append(ctx.author.id)
            with open('database/sign_day.json',mode='w',encoding='utf8') as jfile:
                json.dump(jdsign,jfile,indent=4)
            #週常
            with open('database/sign_week.json','w',encoding='utf8') as jfile:
                jwsign[signer] = jwsign[signer]+1
                json.dump(jwsign,jfile,indent=4)
            
            if ctx.guild.id == jdata['guild']['001']:
                Point(signer).add(1)
                await ctx.send(f'{ctx.author.mention} 簽到完成:pt點數+1',delete_after=5)
            else:
                await ctx.send(f'{ctx.author.mention} 簽到完成!',delete_after=5)

        else:
            await ctx.send(f'{ctx.author.mention} 已經簽到過了喔',delete_after=5)

    @commands.command()
    async def shop(self,ctx):
        embed=discord.Embed(color=0xc4e9ff)
        embed.set_author(name="商城")
        await ctx.send(embed=embed)

def setup(bot):
    bot.add_cog(economy_system(bot))