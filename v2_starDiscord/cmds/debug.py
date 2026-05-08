import asyncio
import io
from datetime import datetime, timedelta, timezone

import discord
import matplotlib
import matplotlib.pyplot as plt
from discord.ext import commands, tasks
from mcstatus import JavaServer

from Instance import debug_guilds, happycamp_guild
from v2_starDiscord.checks import has_privilege_level
from v2_starlib.database import NotifyCommunityType, PrivilegeLevel
from v2_starlib.exceptions import *
from v2_starlib.utils.map import sunmon_area
from v2_starlib.utils.network import get_arp_list

from ..extension import Cog_Extension
from ..ui.embeds import BotEmbed


class MyModal(discord.ui.Modal):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.add_item(discord.ui.InputText(label="Short Input"))
        self.add_item(discord.ui.InputText(label="Long Input", style=discord.InputTextStyle.long))

    async def callback(self, interaction: discord.Interaction):
        embed = discord.Embed(title="Modal Results")
        embed.add_field(name="Short Input", value=self.children[0].value)  # pyright: ignore[reportArgumentType]
        embed.add_field(name="Long Input", value=self.children[1].value)  # pyright: ignore[reportArgumentType]
        await interaction.response.send_message(embeds=[embed])


map_dict = {"0": "⬛", "1": "◻️", "2": "🟨"}


class RPG_advanture_panel(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.map_l = 14
        self.map_w = 14
        self.area = sunmon_area(self.map_l, self.map_w)
        self.player_x = 0
        self.player_y = 0
        self.text = ""

    def map_display(self):
        self.text = ""
        # area_display = copy.deepcopy(self.area)
        area_display = []
        for i in self.area:
            row = []
            for j in i:
                row.append(map_dict.get(j))
            area_display.append(row)
        area_display[self.player_y][self.player_x] = map_dict.get("2")
        for i in area_display:
            self.text += " ".join(i) + "\n"
        return self.text

    @discord.ui.button(label="↑", style=discord.ButtonStyle.green)
    async def up(self, button: discord.ui.Button, interaction: discord.Interaction):
        if self.player_y != 0 and self.area[self.player_y - 1][self.player_x] == "0":
            self.player_y -= 1
            await interaction.response.edit_message(content=self.map_display(), view=self)
        else:
            await interaction.response.edit_message(content=self.text, view=self)

    @discord.ui.button(label="↓", style=discord.ButtonStyle.green)
    async def down(self, button: discord.ui.Button, interaction: discord.Interaction):
        if self.player_y != self.map_l - 1 and self.area[self.player_y + 1][self.player_x] == "0":
            self.player_y += 1
            if self.player_x == self.map_w - 1 and self.player_y == self.map_l - 1:
                self.disable_all_items()
                await interaction.response.edit_message(content=f"恭喜完成~\n{self.map_display()}", view=self)
            else:
                await interaction.response.edit_message(content=self.map_display(), view=self)
        else:
            await interaction.response.edit_message(content=self.text, view=self)

    @discord.ui.button(label="←", style=discord.ButtonStyle.green)
    async def left(self, button: discord.ui.Button, interaction: discord.Interaction):
        if self.player_x != 0 and self.area[self.player_y][self.player_x - 1] == "0":
            self.player_x -= 1
            await interaction.response.edit_message(content=self.map_display(), view=self)
        else:
            await interaction.response.edit_message(content=self.text, view=self)

    @discord.ui.button(label="→", style=discord.ButtonStyle.green)
    async def right(self, button: discord.ui.Button, interaction: discord.Interaction):
        if self.player_x != self.map_w - 1 and self.area[self.player_y][self.player_x + 1] == "0":
            self.player_x += 1
            if self.player_x == self.map_w - 1 and self.player_y == self.map_l - 1:
                self.disable_all_items()
                await interaction.response.edit_message(content=f"恭喜完成~\n{self.map_display()}", view=self)
            else:
                await interaction.response.edit_message(content=self.map_display(), view=self)
        else:
            await interaction.response.edit_message(content=self.text, view=self)


class MySelectMenus(discord.ui.Select):
    def __init__(self, bot: discord.Bot, guild_id: int, role_ids: list[int]):
        super().__init__(
            placeholder="Choose a Flavor!",
            min_values=1,
            max_values=3,
        )
        self.bot = bot
        self.guild = bot.get_guild(guild_id)
        assert self.guild is not None, "Guild not found"
        for role_id in role_ids:
            role = self.guild.get_role(role_id)
            assert role is not None, f"Role not found: {role_id}"
            self.append_option(discord.SelectOption(label=role.name, value=str(role.id), description=f"Role ID: {role.id}"))

    async def callback(self, interaction: discord.Interaction):
        lst = []
        assert interaction.guild is not None, "Guild not found"
        for i in self.values:  # pyright: ignore[reportOptionalIterable]
            assert isinstance(i, (str, int)), "Role ID type "
            role = interaction.guild.get_role(int(i))
            assert role is not None, f"Role not found: {i}"
            lst.append(role.name)
        await interaction.response.send_message(f"Added role: {','.join(lst)}", ephemeral=True)


class MySelectMenusView(discord.ui.View):
    def __init__(self, bot: discord.Bot, guild_id: int, role_ids: list[int]):
        super().__init__()
        select = MySelectMenus(bot, guild_id, role_ids)
        self.add_item(select)
        self.add_item(MySelect())


class MySelect(discord.ui.Section):
    def __init__(self):
        super().__init__(discord.ui.TextDisplay(content="Choose a role"), accessory=discord.ui.Thumbnail(url="https://i.imgur.com/4M34hi2.png"))


class debug(Cog_Extension):
    pass

    @commands.is_owner()
    @commands.slash_command(description="測試指令", guild_ids=debug_guilds)
    async def test(self, ctx: discord.ApplicationContext):
        # await ctx.defer()
        # command = self.bot.get_cog('command')
        # await command.dice(ctx,1,100)
        await ctx.respond(view=MySelectMenusView(self.bot, ctx.guild.id, [865582049238843422, 870929961417068565, 1424682854318735420]))
        # await ctx.respond(view=MySelect())

    @commands.is_owner()
    @commands.slash_command(description="幫助測試", guild_ids=debug_guilds)
    async def helptest(self, ctx: discord.ApplicationContext, arg: str | None = None):
        if not arg:
            command_names_list = [command.name for command in self.bot.commands]
            # await ctx.send(f"{i}. {command.name}" for i, command in enumerate(self.bot.commands, 1))
            await ctx.respond(f"指令列表：{','.join(command_names_list)}")
        else:
            cmd = self.bot.get_command(arg)
            if not cmd:
                await ctx.respond(f"找不到指令：{arg}")
            elif isinstance(cmd, discord.SlashCommandGroup):
                await ctx.respond(f"指令：{cmd.name}\n描述：{cmd.description}")
            else:
                assert isinstance(cmd, discord.SlashCommand)
                option_str = "\n> ".join([f"{option.name}：{option.description}" for option in cmd.options])
                await ctx.respond(f"指令：{cmd.full_parent_name} {cmd.name}\n描述：{cmd.description}\n參數：\n> {option_str}")

    @commands.slash_command(description="地圖生成測試")
    async def maptest(self, ctx: discord.ApplicationContext):
        await ctx.defer()
        view = RPG_advanture_panel()
        await ctx.respond(view.map_display(), view=view)

        # channel = self.bot.get_channel(566533708371329026)
        # botuser = ctx.guild.get_member(self.bot.user.id)
        # Permission = channel.permissions_for(botuser)
        # await ctx.respond((Permission.send_messages and Permission.embed_links))

    @commands.is_owner()
    @has_privilege_level(PrivilegeLevel.Level3)
    @commands.slash_command(description="ver.2.0測試", guild_ids=debug_guilds)
    async def embedtest(self, ctx: discord.ApplicationContext):
        embed = BotEmbed.sts()
        embed.add_field(name="測試", value="測試")
        await ctx.respond(embed=embed)

    @commands.is_owner()
    @commands.slash_command(description="將舊身分組的成員替換到新身分組上", guild_ids=happycamp_guild)
    async def roletest(self, ctx: discord.ApplicationContext, old_role: discord.Role, new_role: discord.Role):
        await ctx.defer()
        for member in old_role.members:
            await member.add_roles(new_role)
            await member.remove_roles(old_role)
            await asyncio.sleep(1)

        await ctx.respond(f"已將 {old_role.mention} 的成員替換到 {new_role.mention} 上", ephemeral=True)

    @commands.is_owner()
    @commands.slash_command(description="測試指令", guild_ids=debug_guilds)
    async def attachmenttest(self, ctx: discord.ApplicationContext, att: discord.Option(discord.Attachment, required=True, name="附件")):
        await ctx.respond(file=discord.File(io.BytesIO(await att.read()), filename=att.filename), ephemeral=True)

    @commands.is_owner()
    @commands.slash_command(description="伺服器偵測測試", guild_ids=debug_guilds)
    async def serverchecktest(self, ctx: discord.ApplicationContext):
        await ctx.defer()

        lst = get_arp_list()
        text_lst = []
        for i in lst:
            try:
                server = JavaServer(i[0], 25565)
                status = server.status()
                status.raw
                text_lst.append(f"伺服器：{i[0]}，人數：{status.players.online}，版本：{status.version.name}")
            except Exception as e:
                text_lst.append(f"伺服器：{i[0]}，無法連線")

        if text_lst:
            text = "\n".join(text_lst)
        else:
            text = "無法連線到任何伺服器"

        await ctx.respond(text)

    @commands.is_owner()
    @commands.slash_command(description="通知測試", guild_ids=debug_guilds)
    async def notify_test(
        self,
        ctx: discord.ApplicationContext,
        community_id=discord.Option(str, required=True, description="社群ID"),
    ):
        assert isinstance(community_id, str), "社群ID必須是字串"
        data = self.bot.sqldb.get_notify_community_guild(NotifyCommunityType.TwitchLive, community_id)
        embed = BotEmbed.sts()
        for guild_id, channel_id, role_id, message in data:
            guild = self.bot.get_guild(guild_id)
            if not guild:
                embed.add_field(
                    name=f"無法找到伺服器 {guild_id}",
                    value=f"頻道：{channel_id}\n身分組：{role_id if role_id else '無身分組'}\n訊息：{message if message else '無訊息'}",
                    inline=False,
                )
                continue

            channel = guild.get_channel(channel_id)
            role = guild.get_role(role_id) if role_id else None
            embed.add_field(
                name=guild.name,
                value=f"頻道：{channel.mention if channel else channel_id}\n身分組：{(role.mention if role.guild == ctx.guild else role.name) if role else '無身分組'}\n訊息：{message if message else '無訊息'}",
                inline=False,
            )

        await ctx.respond(embed=embed)

        # await channel.delete()

    # @commands.is_owner()
    # @commands.slash_command(description="錯誤測試", guild_ids=debug_guilds)
    # async def errortest(self, ctx: discord.ApplicationContext):
    #     # raise APIInvokeError("這是一個API調用錯誤測試", original_message="這是原始錯誤訊息")
    #     raise AttributeError("這是一個屬性錯誤測試")  # This will trigger an AttributeError

    # @commands.slash_command()
    # async def modal_slash(self,ctx: discord.ApplicationContext):
    #     """Shows an example of a modal dialog being invoked from a slash command."""
    #     modal = MyModal(title="Modal Slash Command")
    #     await ctx.send_modal(modal)

    # @commands.command()
    # @commands.is_owner()
    # async def derole(self,ctx: commands.Context):
    #     role = self.bot.get_guild(613747262291443742).get_role(706794165094187038)
    #     channel = self.bot.get_channel(706810474326655026)
    #     permission = discord.Permissions(view_channel=True)
    #     #overwrites = {}
    #     for user in role.members:
    #         #overwrites[user] = discord.PermissionOverwrite(view_channel=True)
    #         await channel.set_permissions(user,view_channel=True)
    #         await asyncio.sleep(0.5)
    #     await ctx.message.add_reaction('✅')


def setup(bot):
    bot.add_cog(debug(bot))
