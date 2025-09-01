from datetime import datetime, timedelta

import discord
from discord.commands import SlashCommandGroup
from discord.ext import commands

from starlib import BotEmbed, ChoiceList, sclient
from starlib.instance import happycamp_guild
from starlib.models.rpg import RPGUser

from ..extension import Cog_Extension
from ..uiElement.RPGview import RPGAdvanceView, RPGEquipmentSelectView


class system_rpg(Cog_Extension):
    @commands.slash_command(description="查看用戶資訊", guild_ids=happycamp_guild)
    async def rpgui(self, ctx: discord.ApplicationContext, member: discord.Option(discord.Member, name="用戶", description="留空以查詢自己", default=None)):
        user_dc:discord.Member = member or ctx.author

        player = sclient.sqldb.get_rpg_player(user_dc.id)

        time = datetime.now()
        time = time.replace(year=2044)
        description_list = [f"現在時間：{time.isoformat(sep=' ', timespec='seconds')}", f"天氣：晴"]
        time_embed = BotEmbed.bot(self.bot, description="\n".join(description_list))
        time_embed.set_footer(text="格瑞爾市 | 祝您有個愉快的一天")
        await ctx.respond(embeds=[time_embed, player.embed(user_dc)])

    @commands.slash_command(description="開始冒險", guild_ids=happycamp_guild)
    async def advance(self, ctx: discord.ApplicationContext):
        await ctx.respond(view=RPGAdvanceView(ctx.author.id, 1, ctx.author))

    @commands.slash_command(description="查看裝備背包", guild_ids=happycamp_guild)
    async def equipmentbag(self, ctx: discord.ApplicationContext):
        view = RPGEquipmentSelectView(ctx.author)
        await ctx.respond(embed=view.embeds[0], view=view)


def setup(bot):
    bot.add_cog(system_rpg(bot))
