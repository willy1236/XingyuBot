import discord
from discord.commands import SlashCommandGroup
from discord.ext import commands

from starlib import BotEmbed, ChoiceList, Jsondb, sclient
from starlib.models.rpg import RPGUser
from starlib.uiElement.RPGview import RPGAdvanceView, RPGEquipmentBagPaginator, RPGEquipmentSelectView

from ..extension import Cog_Extension


class system_rpg(Cog_Extension):
    @commands.slash_command(description='查看用戶資訊')
    async def rpgui(self,ctx:discord.ApplicationContext,
                 user_dc:discord.Option(discord.Member,name='用戶',description='留空以查詢自己',default=None)):
        user_dc:discord.Member = user_dc or ctx.author
        
        user = sclient.sqldb.get_user_rpg(user_dc.id)
        if not user:
            user = RPGUser(discord_id=user_dc.id)
            sclient.sqldb.merge(user)
        await ctx.respond(embed=user.embed(user_dc))

    @commands.slash_command(description='開始冒險')
    async def advance(self,ctx:discord.ApplicationContext):
        await ctx.respond(view=RPGAdvanceView(ctx.author.id, 1, ctx.author))

    @commands.slash_command(description='查看裝備背包')
    async def equipmentbag(self,ctx:discord.ApplicationContext):
        # await RPGEquipmentBagPaginator(ctx.author).respond(ctx.interaction)
        view = RPGEquipmentSelectView(ctx.author)
        await ctx.respond(embed=view.embeds[0], view=view)


def setup(bot):
    bot.add_cog(system_rpg(bot))