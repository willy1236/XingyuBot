import discord,asyncio,random
from discord.ext import commands
from discord.commands import SlashCommandGroup
from core.classes import Cog_Extension
from starcord import sqldb,Jsondb

debug_guild = Jsondb.jdata.get('debug_guild')

class system_economy(Cog_Extension):
    point = SlashCommandGroup("point", "Pt點數相關指令")

    @point.command(description='查詢Pt點數')
    async def check(self,ctx,
                    user:discord.Option(discord.Member,name='成員',description='欲查詢的成員，留空以查詢自己',default=None)):
        user = user or ctx.author
        records = sqldb.get_point(str(user.id))
        pt = records['point'] or 0
        await ctx.respond(f'{user.mention} 目前擁有 {pt} Pt點數')
        if user.bot:
            await ctx.send('但是為什麼你要查詢機器人的點數呢?',delete_after=5)

    @point.command(description='轉移Pt點數')
    async def give(self,ctx,
                   given:discord.Option(discord.Member,name='成員',description='欲轉給的成員',required=True),
                   amount:discord.Option(int,name='點數',description='',min_value=1,required=True)):
        giver = ctx.author
        if given == giver:
            await ctx.respond(f'轉帳失敗:無法轉帳給自己',ephemeral=True)
        elif given.bot == True:
            await ctx.respond(f'轉帳失敗:無法轉帳給機器人',ephemeral=True)
        else:
            code = sqldb.give_point(str(giver.id),str(given.id),amount)
            if not code:
                await ctx.respond(f'轉帳成功:{ctx.author.mention}已將 {amount} 點Pt轉給 {given.mention}')
            elif code == 1 :
                await ctx.respond(f'轉帳失敗:{ctx.author.mention}的Pt點數不足',ephemeral=True)
    
    @commands.is_owner()
    @point.command(description='設定Pt點數',guild_ids=debug_guild)
    async def set(self,ctx,
                  user:discord.Option(discord.Member,name='成員',description='欲調整的成員',required=True),
                  mod:discord.Option(str,name='模式',description='add,set',required=True),
                  amount:discord.Option(int,name='點數',description='',required=True)):
        mod_list = ['add','set']
        if user and mod in mod_list:
            sqldb.update_point(mod,str(user.id),amount)
            await ctx.respond(f'設定成功:已更改{user.mention}的Pt點數')
        else:
            await ctx.respond(f'錯誤:找不到用戶或模式(add,set)輸入錯誤',ephemeral=True)

    @commands.slash_command(description='簽到')
    async def sign(self,ctx):
        signer = str(ctx.author.id)

        code = sqldb.user_sign(signer)
        if not code:
            point_add  = random.randint(1,2)
            rcoin_add = random.randint(3,5)
            sqldb.sign_add_coin(signer,point_add,rcoin_add)
            await ctx.respond(f'{ctx.author.mention} 簽到完成! pt點數+{point_add} Rcoin+{rcoin_add}')
        #可用enum改寫
        elif code == 1:
            await ctx.respond(f'{ctx.author.mention} 已經簽到過了喔')

    @commands.slash_command(description='猜數字遊戲')
    async def guess(self,ctx):
        channel = ctx.channel
        userid = str(ctx.author.id)
        r = sqldb.getif_point(userid,2)
        if not r:
            await ctx.respond('你的pt點不足喔 需要2點才能遊玩')
            return
        
        sqldb.update_point('add',userid,-2)
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
                sqldb.update_point('add',userid,18)
                await channel.send('猜對了喔! 獎勵:18pt點',reference=msg)
            else:
                await channel.send(f'可惜了 答案是 {n}',reference=msg)
        except asyncio.TimeoutError:
            await channel.send(f'{ctx.author.mention} 時間超過了')

def setup(bot):
    bot.add_cog(system_economy(bot))