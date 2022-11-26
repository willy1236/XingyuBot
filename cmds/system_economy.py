import discord,asyncio,random
from discord.ext import commands
from discord.commands import SlashCommandGroup
from core.classes import Cog_Extension
from BotLib.funtions import find
from BotLib.interface.user import Point,Rcoin
from BotLib.database import JsonDatabase


class system_economy(Cog_Extension):
    point = SlashCommandGroup("point", "Pt點數相關指令")

    @point.command(description='查詢Pt點數')
    async def check(self,
                    ctx,
                    user:discord.Option(discord.Member,name='成員',description='欲查詢的成員，可不輸入以查詢自己',default=None)
                    ):
        user = user or ctx.author
        pt = Point(user.id).pt
        await ctx.respond(f'{user.mention} 你目前擁有 {pt} Pt點數')
        if user.bot:
            await ctx.send('但是為什麼你要查詢機器人的點數呢?',delete_after=5)

    @point.command(description='轉移Pt點數')
    async def give(self,
                ctx,
                given:discord.Option(discord.Member,name='成員',description='欲轉給的成員',required=True),
                amount:discord.Option(int,name='點數',description='',min_value=1,required=True)
                ):
        giver = ctx.author
        if given == giver:
            await ctx.respond(f'轉帳失敗:無法轉帳給自己',ephemeral=True)
        elif given.bot == True:
            await ctx.respond(f'轉帳失敗:無法轉帳給機器人',ephemeral=True)
        elif Point(giver.id).pt < amount:
            await ctx.respond(f'轉帳失敗:{ctx.author.mention}的Pt點數不足',ephemeral=True)
        else:
            Point(given.id).add(amount)
            Point(giver.id).add(amount*-1)
            await ctx.respond(f'轉帳成功:{ctx.author.mention}已將 {amount} 點Pt轉給 {given.mention}')
    
    @commands.is_owner()
    @point.command(description='設定Pt點數')
    async def set(self,
                ctx,
                user:discord.Option(discord.Member,name='成員',description='欲調整的成員',required=True),
                mod:discord.Option(str,name='模式',description='add,set',required=True),
                amount:discord.Option(int,name='點數',description='',required=True)
                ):
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
            await ctx.respond(f'設定成功:已將{user.mention}的Pt點數從 {pt_old} 設定為 {pt_new}')
        else:
            await ctx.respond(f'錯誤:找不到用戶或模式(add set)輸入錯誤',ephemeral=True)

    @commands.slash_command(description='簽到')
    async def sign(self,ctx):
        db = JsonDatabase()
        jdsign = db.jdsign
        #jwsign = Database().jwsign
        jdata = db.jdata
        signer = str(ctx.author.id)
        
        if signer not in jdsign:    
            #日常
            jdsign.append(signer)
            db.write('jdsign',jdsign)
            #週常
            #jwsign[signer] += 1
            #Database().write('jwsign',jwsign)
            
            #Rcoin
            rcoin_add = random.randint(3,5)
            Rcoin(signer).add(rcoin_add)
            if ctx.guild.id == jdata['guild']['001']:
                Point(signer).add(1)
                await ctx.respond(f'{ctx.author.mention} 簽到完成! pt點數+1 Rcoin+{rcoin_add}')
            else:
                await ctx.respond(f'{ctx.author.mention} 簽到完成! Rcoin+{rcoin_add}')
        else:
            await ctx.send(f'{ctx.author.mention} 已經簽到過了喔',delete_after=5)

    @commands.slash_command(description='猜數字遊戲')
    async def guess(self,ctx):
        channel = ctx.channel
        pt = Point(ctx.author.id)
        if pt.pt < 2:
            await ctx.respond('你的pt點不足喔 需要2點才能遊玩')
            return
        pt.add(-2)
        await ctx.respond('猜數字遊戲 來猜個數字吧 從1~10')
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
                await channel.send('猜對了喔! 獎勵:18pt點',reference=msg)
            else:
                await channel.send(f'可惜了 答案是 {n}',reference=msg)
        except asyncio.TimeoutError:
            await channel.send(f'{ctx.author.mention} 時間超過了')

def setup(bot):
    bot.add_cog(system_economy(bot))