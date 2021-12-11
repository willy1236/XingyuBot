import discord
from discord.ext import commands
import json
from core.classes import Cog_Extension
from library import Counter, check_point,find_user

jdata = json.load(open('setting.json',mode='r',encoding='utf8'))

with open('point.json',mode='r',encoding='utf8') as jfile:
    jpt2 = json.load(jfile)
    jpt = Counter(jpt2)

class point(Cog_Extension):
    @commands.group(invoke_without_command=True,aliases=['pt'])
    async def point(self,ctx,user=None):
        if user == None:
            user = ctx.author
            pt = check_point(user.id)
            await ctx.send(f'{user.mention} 你目前擁有 {pt} Pt點數', reference=ctx.message)
        else:
            user = await find_user(ctx,user)
            if user != None:
                pt = check_point(user.id)
                await ctx.send(f'{user.name} 目前擁有 {pt} Pt點數', reference=ctx.message)
                if user.bot:
                    await ctx.send('溫馨提醒:機器人是沒有點數的喔',delete_after=5)
            else:
                await ctx.send('錯誤:找不到用戶', reference=ctx.message,delete_after=5)
            
    @point.command()
    async def give(self,ctx,give,amount:int):
        given = await find_user(ctx,give)
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
                elif check_point(giver.id)-amount < 0:
                    await ctx.message.delete()
                    await ctx.send(f'轉帳失敗:{ctx.author.mention}的Pt點數不足',delete_after=5)
                else:
                    with open('point.json',mode='r+',encoding='utf8') as jfile:
                        jpt[str(given.id)] = check_point(given.id)+amount
                        jpt[str(giver.id)] = check_point(giver.id)-amount
                        json.dump(jpt,jfile,indent=4)
                    await ctx.send(f'轉帳成功:{ctx.author.mention}已將 {amount} 點Pt轉給 {given.mention}')
        else:
            await ctx.message.delete()
            await ctx.send(content='錯誤:沒找到用戶，請填入用戶ID',delete_after=5)
    
    @commands.is_owner()
    @commands.command()
    async def ptset(self,ctx,user,mod,amount:int):
        user = await find_user(ctx,user)
        mod_list = ['+','-','set']
        if user is not None and mod in mod_list:
            pt_old = check_point(user.id)
            with open('point.json',mode='r+',encoding='utf8') as jfile:
                if mod == '+':
                    jpt[str(user.id)] = check_point(user.id)+amount 
                elif mod == '-':
                    jpt[str(user.id)] = check_point(user.id)-amount
                elif mod == 'set':
                    jpt[str(user.id)] = amount
                json.dump(jpt,jfile,indent=4)
                
            await ctx.send(f'設定成功:已將{user.mention}的Pt點數從 {pt_old} 設定為 {check_point(user.id)}')
        else:
            await ctx.send(f'錯誤:找不到用戶或模式輸入錯誤',delete_after=5)

def setup(bot):
    bot.add_cog(point(bot))