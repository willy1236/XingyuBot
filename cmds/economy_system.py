import discord,asyncio,random
from discord.ext import commands
from core.classes import Cog_Extension
from library import find
from BotLib.user import Point
from BotLib.database import Database


class economy_system(Cog_Extension):
    @commands.group(invoke_without_command=True,aliases=['pt'])
    async def point(self,ctx,user=None):
        if not user:
            user = ctx.author
            pt = Point(ctx.author.id).pt
            await ctx.send(f'{user.mention} 你目前擁有 {pt} Pt點數', reference=ctx.message)
        else:
            user = await find.user(ctx,user)
            if user:
                pt = Point(user.id).pt
                await ctx.send(f'{user.name} 目前擁有 {pt} Pt點數', reference=ctx.message)
                if user.bot:
                    await ctx.send('但是為什麼你要查詢機器人的點數呢?',delete_after=5)
            else:
                await ctx.send('錯誤:找不到用戶', reference=ctx.message,delete_after=5)
            
    @point.command()
    async def give(self,ctx,give,amount:int):
        given = await find.user(ctx,give)
        if given:
            giver = ctx.author
            if amount <= 0:
                await ctx.send(f'轉帳失敗:無法轉帳少於1Pt',delete_after=5)
            elif given == giver:
                await ctx.send(f'轉帳失敗:無法轉帳給自己',delete_after=5)
            elif given.bot == True:
                await ctx.send(f'轉帳失敗:無法轉帳給機器人',delete_after=5)
            elif Point(giver.id).pt < amount:
                await ctx.send(f'轉帳失敗:{ctx.author.mention}的Pt點數不足',delete_after=5)
            else:
                Point(given.id).add(amount)
                Point(giver.id).add(amount*-1)
                await ctx.send(f'轉帳成功:{ctx.author.mention}已將 {amount} 點Pt轉給 {given.mention}')
        else:
            await ctx.send(content='錯誤:沒找到用戶，請填入用戶ID',delete_after=5)
    
    @commands.is_owner()
    @commands.command()
    async def ptset(self,ctx,user,mod,amount:int):
        user = await find.user(ctx,user)
        mod_list = ['add','set']
        if user and mod in mod_list:
            pt = Point(user.id)
            pt_old = pt.pt
            if mod == 'add':
                pt.add(amount)
            elif mod == 'set':
                pt.set(amount)
            pt_new = Point(user.id).pt
            await ctx.send(f'設定成功:已將{user.mention}的Pt點數從 {pt_old} 設定為 {pt_new}')
        else:
            await ctx.send(f'錯誤:找不到用戶或模式(add set)輸入錯誤',delete_after=5)

    @commands.command()
    async def sign(self,ctx):
        jdsign = Database().jdsign
        #jwsign = Database().jwsign
        jdata = Database().jdata
        signer = str(ctx.author.id)
        
        if signer not in jdsign:    
            #日常
            jdsign.append(signer)
            Database().write('jdsign',jdsign)
            #週常
            #jwsign[signer] += 1
            #Database().write('jwsign',jwsign)
            
            if ctx.guild.id == jdata['guild']['001']:
                Point(signer).add(1)
                await ctx.send(f'{ctx.author.mention} 簽到完成! pt點數+1',delete_after=5)
            else:
                await ctx.send(f'{ctx.author.mention} 簽到完成!',delete_after=5)
        else:
            await ctx.send(f'{ctx.author.mention} 已經簽到過了喔',delete_after=5)

    @commands.command()
    async def guess(self,ctx):
        channel = ctx.channel
        pt = Point(ctx.author.id)
        if pt.pt < 2:
            await channel.send('你的pt點不足喔 需要2點才能遊玩')
            return
        pt.add(-2)
        await channel.send('猜數字遊戲 來猜個數字吧 從1~10')
        n = random.randint(1,10)
        def check(m):
            try:
                text = int(m.content)
                return text in range(1,11) and m.author == ctx.author
            except:
                return False
        
        try:
            msg = await self.bot.wait_for('message', check=check,timeout=60)
            if msg.content == str(n):
                pt.add(18)
                await channel.send('猜對了喔! 獎勵:18pt點')
            else:
                await channel.send(f'可惜了 答案是 {n}')
        except asyncio.TimeoutError:
            await channel.send(f'{ctx.author.mention} 時間超過了')

    @commands.command()
    async def shop(self,ctx):
        embed=discord.Embed(color=0xc4e9ff)
        embed.set_author(name="商城")
        await ctx.send(embed=embed)

def setup(bot):
    bot.add_cog(economy_system(bot))