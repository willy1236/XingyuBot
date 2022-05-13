import discord,asyncio
from discord.commands import SlashCommandGroup
from discord.ext import commands, pages
from core.classes import Cog_Extension


class page_system(commands.Cog):
    def __init__(self,bot):
        self.bot = bot
        self.pages = ["page1","page2",[discord.Embed(title="Page 3, Embed 1"),discord.Embed(title="Page 3, Embed 2")],discord.Embed(title="Page Four")]
        self.pages[3].set_image(url="https://c.tenor.com/pPKOYQpTO8AAAAAM/monkey-developer.gif")

    @commands.command()
    async def pagetest_target(self, ctx: commands.Context):
        paginator = pages.Paginator(pages=self.pages)
        await paginator.send(ctx, target=ctx.channel, target_message="Paginator sent!")

    @commands.command()
    async def pagetest_target2(self, ctx: commands.Context):
        paginator = pages.Paginator(pages=self.self.pages, use_default_buttons=False)
        paginator.add_button(pages.PaginatorButton("prev", label="<", style=discord.ButtonStyle.green))
        paginator.add_button(pages.PaginatorButton("page_indicator", style=discord.ButtonStyle.gray, disabled=True))
        paginator.add_button(pages.PaginatorButton("next", style=discord.ButtonStyle.green))
        await paginator.send(ctx, target=ctx.channel, target_message="Paginator sent!")
        

def setup(bot):
    bot.add_cog(page_system(bot))