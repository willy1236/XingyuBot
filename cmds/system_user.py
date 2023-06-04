import discord
from discord.ext import commands
from core.classes import Cog_Extension
from discord.commands import SlashCommandGroup

from starcord.interface.user import *
from starcord import BotEmbed,Jsondb,ChoiceList,sqldb,UserClient
from starcord.ui_element.button import Delete_Pet_button

jdict = Jsondb.jdict
option = ChoiceList.set('pet_option')

class system_user(Cog_Extension):
    pet = SlashCommandGroup("pet", "寵物相關指令")
    #shop = SlashCommandGroup("shop", "商店相關指令")

    @pet.command(description='查看寵物資訊')
    async def check(self,ctx,user_dc:discord.Option(discord.Member,name='用戶',description='可不輸入以查詢自己',default=None)):
        user_dc = user_dc or ctx.author
        pet = UserClient.get_pet(str(user_dc.id))
        if pet:
            embed = pet.desplay()
            embed.title = f'{ctx.author.name} 的寵物'
            await ctx.respond(embed=embed)
        else:
            await ctx.respond('用戶沒有認養寵物')
    
    @pet.command(description='認養寵物')
    async def add(self,ctx,
                  species:discord.Option(str,name='物種',description='想認養的寵物物種',choices=option),
                  name:discord.Option(str,name='寵物名',description='想幫寵物取的名子')):
        r = sqldb.create_user_pet(str(ctx.author.id),species,name)
        if r:
            await ctx.respond(r)
        else:
            await ctx.respond(f"你收養了一隻名叫 {name} 的{list(filter(lambda x: jdict['pet_option'][x]==species,jdict['pet_option']))[0]}!")
    
    @pet.command(description='放生寵物')
    async def remove(self,ctx):
        # def check(m):
        #     try:
        #         return m.content == 'y' and m.author == ctx.author
        #     except:
        #         return False
        
        pet = UserClient.get_pet(str(ctx.author.id))
        if not pet:
            await ctx.respond('你沒有寵物')
            return
        await ctx.respond('你真的確定要放生寵物嗎?',view=Delete_Pet_button())
        # try:
            
        #     # msg = await self.bot.wait_for('message', check=check,timeout=60)
        #     # if msg.content == 'y':
        #     #     self.sqldb.delete_user_pet(str(ctx.author.id))
        #     #     await res.message.edit('寵物已放生')
        #     # else:
        #     #     await ctx.send(f'取消放生寵物')
        # except asyncio.TimeoutError:
        #     await ctx.respond(f'{ctx.author.name} 超時自動取消放生')

    # @shop.command(description='打開商店列表（開發中）',)
    # async def list(self,ctx):
    #     embed = discord.Embed(color=0xc4e9ff)
    #     embed.set_author(name="商城")
    #     embed.add_field(name="[1] 石頭",value='$1')
    #     await ctx.respond(embed=embed)

    # @shop.command(description='購買物品（開發中）')
    # async def buy(self,ctx,
    #               id:discord.Option(str,name='商品id',description='想購買的商品'),
    #               amount:discord.Option(int,name='數量',description='')):
    #     await ctx.respond('敬請期待')
    #     return
    #     if id == '1':
    #         user = User(ctx.author.id)
    #         if int(user.rcoin) >= 1 * amount:
    #             db = Database()
    #             jbag = db.jbag
    #             if jbag[str(ctx.author.id)]['stone']:   
    #                 jbag[str(ctx.author.id)]['stone'] += amount
    #             else:
    #                 jbag[str(ctx.author.id)]['stone'] = amount
    #             db.write('jbag',jbag)
    #             user.rcoin.add(-1 * 1 * amount)
    #             await ctx.respond('購買已完成')
    #         else:
    #             raise commands.errors.ArgumentParsingError('你的錢不購買此商品')
    #     else:
    #         raise commands.errors.ArgumentParsingError('沒有此商品')

def setup(bot):
    bot.add_cog(system_user(bot))