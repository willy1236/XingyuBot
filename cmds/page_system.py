import asyncio

import discord
from discord.commands import SlashCommandGroup
from discord.ext import commands, pages
from core.classes import Cog_Extension


class page_system(commands.Cog):
    def __init__(self,bot):
        self.bot = bot
        self.pages = ["page1","page2","page3",discord.Embed(title="Page Four"),"page5","page6"]
        self.pages[3].set_image(url="https://c.tenor.com/pPKOYQpTO8AAAAAM/monkey-developer.gif")
        

    def get_pages(self,code):
        if code == 1:
            return self.pages
        elif code == 2:
            return self.pages2

    @commands.command()
    async def pagetest_target(self, ctx: commands.Context):
        paginator = pages.Paginator(pages=self.get_pages(1))
        await paginator.send(ctx, target=ctx.channel, target_message="Paginator sent!")

    @commands.command()
    async def pagetest_target2(self, ctx: commands.Context):
        paginator = pages.Paginator(pages=self.get_pages(1), use_default_buttons=False)
        paginator.add_button(pages.PaginatorButton("prev", label="<", style=discord.ButtonStyle.green))
        paginator.add_button(pages.PaginatorButton("page_indicator", style=discord.ButtonStyle.gray, disabled=True))
        paginator.add_button(pages.PaginatorButton("next", style=discord.ButtonStyle.green))
        await paginator.send(ctx, target=ctx.channel, target_message="Paginator sent!")
        

def setup(bot):
    bot.add_cog(page_system(bot))