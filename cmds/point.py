import discord
from discord.ext import commands
import json
from core.classes import Cog_Extension

with open('setting.json',mode='r',encoding='utf8') as jfile:
    jdata = json.load(jfile)

with open('sign_day.json',mode='r',encoding='utf8') as jfile:
    jdsign = json.load(jfile)

with open('sign_week.json',mode='r',encoding='utf8') as jfile:
    jwsign = json.load(jfile)

with open('point.json',mode='r',encoding='utf8') as jfile:
    jpt2 = json.load(jfile)

class Counter(dict):
    def __missing__(self,key): 
        return 0
jpt = Counter(jpt2)

class point(Cog_Extension):
    @commands.command()
    async def pt(self,ctx,*arg):
        if not arg:
            pt = jpt[str(ctx.author.id)]
            await ctx.send(content=f'{ctx.author.mention} 你目前擁有 {pt} Pt點數', reference=ctx.message)

        elif arg[0] == 'give':
            if self.bot.get_user(int(arg[1])):
                given = self.bot.get_user(int(arg[1]))
                giver = ctx.author
                amount = int(arg[2])
                if amount == 0:
                    await ctx.message.delete()
                    await ctx.send(content=f'轉帳失敗:無法轉帳0Pt',delete_after=5)
                elif given == giver:
                    await ctx.message.delete()
                    await ctx.send(content=f'轉帳失敗:無法轉帳給自己',delete_after=5)
                elif given.bot == True:
                    await ctx.message.delete()
                    await ctx.send(content=f'轉帳失敗:無法轉帳給機器人',delete_after=5)
                elif jpt[str(giver.id)]-amount >= 0:
                    with open('point.json',mode='w',encoding='utf8') as jfile:
                        jpt[str(given.id)] = jpt[str(given.id)]+amount
                        jpt[str(giver.id)] = jpt[str(giver.id)]-amount
                        json.dump(jpt,jfile,indent=4)
                    await ctx.send(f'轉帳成功:{ctx.author.mention}已將 {amount} 點Pt轉給 {given.mention}')
                else:
                    await ctx.message.delete()
                    await ctx.send(content=f'轉帳失敗:{ctx.author.mention}的Pt點數不足',delete_after=5)
            else:
                await ctx.message.delete()
                await ctx.send(content='錯誤:沒找到用戶，請填入用戶ID',delete_after=5)

        elif self.bot.get_user(int(arg[0])) != 'None':
            user = self.bot.get_user(int(arg[0]))
            pt = jpt[str(user.id)]
            await ctx.send(content=f'{user.name} 目前擁有 {pt} Pt點數', reference=ctx.message)
            
    
    @commands.is_owner()
    @commands.command()
    async def ptset(self,ctx,ID:int,mod,amount:int):
        user = self.bot.get_user(ID)
        pt_old = jpt[str(user.id)]
        with open('point.json',mode='w',encoding='utf8') as jfile:
            if mod == '+':
                jpt[str(user.id)] = jpt[str(user.id)]+amount
            elif mod == '-':
                jpt[str(user.id)] = jpt[str(user.id)]-amount
            elif mod == 'set':
                jpt[str(user.id)] = amount
            else:
                pass
            json.dump(jpt,jfile,indent=4)
            
        await ctx.send(f'設定成功:已將{user.mention}的Pt點數從 {pt_old} 設定為 {jpt[str(user.id)]}')

def setup(bot):
    bot.add_cog(point(bot))