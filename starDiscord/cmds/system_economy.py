import discord
from discord.commands import SlashCommandGroup
from discord.ext import commands

from starlib import BotEmbed, sclient
from starlib.instance import debug_guilds

from ..extension import Cog_Extension


class system_economy(Cog_Extension):
    point = SlashCommandGroup("point", "PT點數相關指令")
    shop = SlashCommandGroup("shop", "商店相關指令")

    @point.command(description='查詢擁有的星塵數')
    async def check(self,ctx:discord.ApplicationContext,
                    user:discord.Option(discord.Member,name='成員',description='留空以查詢自己',default=None)):
        user_dc:discord.Member = user or ctx.author
        coins = sclient.sqldb.get_coin(user_dc.id)
        embed = BotEmbed.simple(f'{user_dc.name} 的點數')
        embed.add_field(name='⭐星塵',value=coins.stardust)
        embed.add_field(name='PT點數',value=coins.point)
        embed.add_field(name='Rcoin',value=coins.rcoin)
        await ctx.respond(embed=embed)
        if user_dc.bot:
            await ctx.send('但是為什麼你要查詢機器人的點數呢?',delete_after=5)

    @point.command(description='轉移星塵')
    async def give(self,ctx:discord.ApplicationContext,
                   given:discord.Option(discord.Member,name='成員',description='欲轉給的成員',required=True),
                   amount:discord.Option(int,name='點數',description='',min_value=1,required=True)):
        giver:discord.Member = ctx.author
        if given == giver:
            await ctx.respond(f'轉帳失敗：無法轉帳給自己',ephemeral=True)
        elif given.bot == True:
            await ctx.respond(f'轉帳失敗：無法轉帳給機器人',ephemeral=True)
        else:
            code = sclient.sqldb.transfer_scoin(giver.id,given.id,amount)
            if not code:
                await ctx.respond(f'轉帳成功：{ctx.author.mention} 已將 {amount} 星塵⭐轉給 {given.mention}')
            else:
                await ctx.respond(f'{ctx.author.mention}：{code}',ephemeral=True)
    
    @commands.is_owner()
    @point.command(description='設定星塵',guild_ids=debug_guilds)
    async def set(self,ctx,
                  user:discord.Option(discord.User,name='成員',description='欲調整的成員',required=True),
                  mod:discord.Option(str,name='模式',description='add,set',required=True,choices=['add','set']),
                  amount:discord.Option(int,name='點數',description='',required=True)):
        user_point = sclient.sqldb.get_coin(user.id)
        if mod == 'add':
            user_point.stardust += amount
        elif mod == 'set':
            user_point.stardust = amount
        sclient.sqldb.merge(user_point)
        await ctx.respond(f'設定成功：已更改{user.mention}的星塵⭐為{user_point.stardust}')

    # @commands.slash_command(description='猜數字遊戲')
    # async def guess(self,ctx):
    #     channel = ctx.channel
    #     userid = ctx.author.id
    #     r = sclient.sqldb.getif_coin(userid,2)
    #     if not r:
    #         await ctx.respond('你的星塵不足喔 需要2元才能遊玩')
    #         return
        
    #     sclient.sqldb.update_coins(userid,'add',Coins.Stardust,-2)
    #     await ctx.respond('猜數字遊戲 來猜個數字吧 從1~10')
    #     n = random.randint(1,10)
    #     def check(m):
    #         try:
    #             text = int(m.content)
    #             return text in range(1,11) and m.author == ctx.author
    #         except:
    #             return False

    #     try:
    #         msg = await self.bot.wait_for('message', check=check,timeout=60)
    #         if msg.content == str(n):
    #             sclient.sqldb.update_coins(userid,'add',Coins.Stardust,18)
    #             await channel.send('猜對了喔! 獎勵:18星塵⭐',reference=msg)
    #         else:
    #             await channel.send(f'可惜了 答案是 {n}',reference=msg)
    #     except asyncio.TimeoutError:
    #         await channel.send(f'{ctx.author.mention} 時間超過了')

    # @shop.command(description='打開商店列表（開發中）')
    # async def list(self,ctx):
    #     embed = BotEmbed.general(name="商城")
    #     #embed.add_field(name="[1] 稱號(僅限Felis catus快樂營)",value='$10')
    #     embed.add_field(name="[1] 石頭",value='$10')
    #     await ctx.respond(embed=embed)
    
    # @shop.command(description='購買商店物品（開發中）')
    # async def buy(self,ctx,item_id):
    #     item = sclient.sqldb.get_scoin_shop_item(item_id)
    #     if not item:
    #         await ctx.respond(f"{ctx.author.mention}：商店沒有賣這個喔")
    #         return
        
    #     buyer_id = sclient.sqldb.getif_coin(ctx.author.id,item.price)
    #     if buyer_id:
    #         sclient.sqldb.update_bag(ctx.author.id,item.item_uid,1)
    #         await ctx.respond(f"{ctx.author.mention}：已購買 {item.name} * 1")
    #     else:
    #         await ctx.respond(f"{ctx.author.mention}：星塵不足")

def setup(bot):
    bot.add_cog(system_economy(bot))