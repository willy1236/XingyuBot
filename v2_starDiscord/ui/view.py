from __future__ import annotations

import asyncio
import io
import logging
from typing import TYPE_CHECKING

import discord
import matplotlib
import numpy as np
from discord.utils import format_dt

from v2_starlib.base import get_settings
from v2_starlib.database import (
    Giveaway,
    GiveawayUser,
    HappycampApplicationForm,
    HappycampVIP,
    McssServerAction,
    McssServerStatues,
    Poll,
    PollRole,
    SQLRepository,
    TicketChannel,
)
from v2_starlib.utils.network import find_radmin_vpn_network
from v2_starlib.utils.time import nowtz

from .embeds import BotEmbed, to_embed

if TYPE_CHECKING:
    from starlib.database import SQLRepository
    from starlib.database.postgresql.models import PollOption, ReactionRoleOption
    from starlib.providers import McssServer

    from ..bot import DiscordBot

log = logging.getLogger(__name__)


class DeletePetView(discord.ui.View):
    def __init__(self, sqldb: SQLRepository):
        super().__init__(timeout=30)
        self.sqldb = sqldb

    @discord.ui.button(label="放生寵物", style=discord.ButtonStyle.danger)
    async def button_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        user = interaction.user
        self.sqldb.remove_user_pet(user.id)
        button.disabled = True
        await interaction.response.edit_message(content="寵物已放生", view=self)


class DeleteAddRoleView(discord.ui.View):
    def __init__(self, role: discord.Role, creater: discord.Member, sqldb: SQLRepository):
        super().__init__(timeout=30)
        self.role = role
        self.creater = creater
        self.sqldb = sqldb

    async def on_timeout(self):
        try:
            self.clear_items()
            self.sqldb.add_role_save(self.role)
            log.info("Role %s has been saved.", self.role)
            await self.message.edit(view=self)
        except discord.errors.NotFound:
            pass

    @discord.ui.button(label="刪除身分組", style=discord.ButtonStyle.danger)
    async def button_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        if interaction.user == self.creater:
            role = self.role
            await role.delete()
            self.clear_items()
            await interaction.message.delete()
        else:
            await interaction.response.send_message(content="只有使用此指令的用戶可以刪除", ephemeral=True)


class PollOptionButton(discord.ui.Button):
    def __init__(self, option: PollOption, custom_id: str, row: int = None):
        super().__init__(label=option.option_name, custom_id=custom_id, row=row)
        self.option = option

    async def callback(self, interaction):
        view: PollView = self.view
        can_vote = False
        have_only_role = False
        vote_magnification = 1
        if view.role_dict:
            for roleid in view.role_dict:
                if view.role_dict[roleid][0]:
                    have_only_role = True
                    role = interaction.user.get_role(roleid)
                    if role:
                        can_vote = True

                if view.role_dict[roleid][1] > vote_magnification:
                    vote_magnification = view.role_dict[roleid][1]

        if not view.role_dict or (have_only_role and can_vote):
            r = view.sqldb.set_user_poll(self.option.poll_id, interaction.user.id, self.option.option_id, nowtz(), vote_magnification, view.poll.number_of_user_votes)
            if r == 2:
                await interaction.response.send_message(f"{interaction.user.mention} 已投了 {view.poll.number_of_user_votes} 票而無法投票", ephemeral=True)
            elif r == 1:
                await interaction.response.send_message(f"{interaction.user.mention} 已投票給 {self.label} {vote_magnification} 票", ephemeral=True)
            else:
                await interaction.response.send_message(f"{interaction.user.mention} 已取消投票給 {self.label}", ephemeral=True)
        else:
            await interaction.response.send_message(f"{interaction.user.mention}：你沒有投票資格", ephemeral=True)


class PollEndButton(discord.ui.Button):
    def __init__(self, poll_id):
        super().__init__(label="結算投票", custom_id=f"end_poll_{poll_id}", style=discord.ButtonStyle.danger)

    async def callback(self, interaction):
        view: PollView = self.view
        if interaction.user.id == view.poll.creator_id or (view.bot and await view.bot.is_owner(interaction.user)):
            view.clear_items()
            view.poll.end_at = nowtz()
            view.poll = view.sqldb.merge(view.poll)

            embed, image_buffer = view.results_embed(interaction, True)  # type: ignore

            await interaction.response.edit_message(embed=embed, view=view, file=discord.File(image_buffer, filename="pie.png"))
        else:
            await interaction.response.send_message(f"錯誤：只有投票發起人才能結算", ephemeral=True)


class PollResultButton(discord.ui.Button):
    def __init__(self, poll_id):
        super().__init__(label="查看結果", custom_id=f"poll_result_{poll_id}", style=discord.ButtonStyle.primary)

    async def callback(self, interaction):
        view: PollView = self.view
        if not view.poll.results_only_initiator:
            embed = view.results_embed(interaction)
            await interaction.response.send_message(embed=embed, ephemeral=True)

        else:
            await interaction.response.send_message(f"錯誤：此投票只有發起人才能查看結果", ephemeral=True)


class PollCanenlButton(discord.ui.Button):
    def __init__(self, poll_id):
        super().__init__(label="取消投票", custom_id=f"vote_canenl_{poll_id}", style=discord.ButtonStyle.primary)

    async def callback(self, interaction):
        view: PollView = self.view
        view.sqldb.remove_user_poll(view.poll.poll_id, interaction.user.id)
        await interaction.response.send_message(f"{interaction.user.mention} 已取消投票", ephemeral=True)


class PollNowButton(discord.ui.Button):
    def __init__(self, poll_id):
        super().__init__(label="目前選擇", custom_id=f"vote_now_{poll_id}", style=discord.ButtonStyle.primary)

    async def callback(self, interaction):
        view: PollView = self.view
        dbdata = view.sqldb.get_user_poll(view.poll.poll_id, interaction.user.id)
        if dbdata:
            vote_mag = dbdata[0][0].vote_magnification
            options_name = ",".join([data[1] for data in dbdata])
            await interaction.response.send_message(f"{interaction.user.mention} 投給 {options_name} {vote_mag}票", ephemeral=True)
        else:
            await interaction.response.send_message(f"{interaction.user.mention} 沒有投給任何選項", ephemeral=True)


class PollView(discord.ui.View):
    if TYPE_CHECKING:
        poll: Poll
        sqldb: SQLRepository
        bot: discord.Bot

    def __init__(self, poll: Poll, bot: DiscordBot):
        super().__init__(timeout=None)
        self.poll = poll
        self.bot = bot
        self.sqldb = bot.sqldb

        self._role_dict = {}
        # TODO: change_vote (decide if user can change his/her vote or not)

        self.add_item(PollEndButton(poll.poll_id))
        if poll.check_results_in_advance:
            self.add_item(PollResultButton(poll.poll_id))
        self.add_item(PollCanenlButton(poll.poll_id))
        self.add_item(PollNowButton(poll.poll_id))

        dbdata = self.sqldb.get_poll_options(poll.poll_id)
        i = 5
        for option in dbdata:
            custom_id = f"poll_{poll.poll_id}_{option.option_id}"
            self.add_item(PollOptionButton(option=option, custom_id=custom_id, row=int(i / 5)))
            i += 1

    @classmethod
    def create(
        cls,
        bot: DiscordBot,
        title: str,
        options: list,
        creator_id: int,
        guild_id: int,
        ban_alternate_account_voting=False,
        show_name=False,
        check_results_in_advance=True,
        results_only_initiator=False,
        number_of_user_votes=1,
        can_change_vote=True,
        only_role_list: list | None = None,
        role_magnification_dict: dict | None = None,
    ):
        """創建投票"""
        poll = Poll(
            title=title,
            creator_id=creator_id,
            created_at=nowtz(),
            message_id=None,
            guild_id=guild_id,
            ban_alternate_account_voting=ban_alternate_account_voting,
            show_name=show_name,
            check_results_in_advance=check_results_in_advance,
            results_only_initiator=results_only_initiator,
            number_of_user_votes=number_of_user_votes,
            can_change_vote=can_change_vote,
        )
        sqldb = bot.sqldb
        sqldb.add(poll)
        sqldb.add_poll_option(poll.poll_id, options)

        if only_role_list is None:
            only_role_list = []
        if role_magnification_dict is None:
            role_magnification_dict = {}

        poll_role_dict = {}
        for role_id in only_role_list:
            poll_role_dict[role_id] = [True, 1]

        for role_id in role_magnification_dict:
            if role_id in poll_role_dict:
                poll_role_dict[role_id][1] = role_magnification_dict[role_id]
            else:
                poll_role_dict[role_id] = [False, role_magnification_dict[role_id]]

        for role_id in poll_role_dict:
            is_only_role = poll_role_dict[role_id][0]
            role_magnification = poll_role_dict[role_id][1]
            sqldb.merge(PollRole(poll_id=poll.poll_id, role_id=role_id, is_only_role=is_only_role, role_magnification=role_magnification))

        view = cls(poll, bot)
        return view

    @property
    def role_dict(self) -> dict[int, tuple[bool, int]]:
        if not self._role_dict:
            dbdata = self.sqldb.get_poll_role(self.poll.poll_id)
            self._role_dict = {}
            if dbdata:
                for data in dbdata:
                    role_id = data.role_id
                    is_only_role = data.is_only_role
                    role_magnification = data.role_magnification
                    self._role_dict[role_id] = (is_only_role, role_magnification)
        return self._role_dict

    def embed(self):
        """guild: 提供投票所在的伺服器"""
        only_role_list = []
        role_magification_list = []
        guild = self.bot.get_guild(self.poll.guild_id)
        for roleid in self.role_dict:
            role = guild.get_role(roleid)
            if self.role_dict[roleid][0] is True:
                only_role_list.append(role.mention if role else roleid)
            if self.role_dict[roleid][1] > 1:
                mag = self.role_dict[roleid][1]
                role_magification_list.append(f"{role.mention}({mag})" if role else f"{roleid}({mag})")

        description = ""
        description += "- 使用投票實名制" if self.poll.show_name else "- 匿名投票"
        description += ("\n- 僅限發起人能預先查看結果" if self.poll.results_only_initiator else "\n- 所有人都能預先查看結果") if self.poll.check_results_in_advance else "\n- 結果將在結束時公佈"
        description += f"\n- 可選擇 {self.poll.number_of_user_votes} 個選項"
        if not self.poll.can_change_vote:
            description += f"\n- 不允許變更投票"
        if self.poll.ban_alternate_account_voting:
            description += f"\n- 小帳不算有效票"

        if only_role_list:
            description += "\n- 可投票身分組：" + ",".join(only_role_list)
        if role_magification_list:
            description += "\n- 身分組投票權重：" + ",".join(role_magification_list)
        embed = BotEmbed.general(name="投票系統", title=self.poll.title, description=description)
        embed.set_footer(text=f"投票ID：{self.poll.poll_id}")

        author = guild.get_member(self.poll.creator_id)
        if author:
            embed.set_author(name=author.name, icon_url=author.avatar.url)
        return embed

    def results_embed(self, with_chart=False) -> tuple[discord.Embed, io.BytesIO] | discord.Embed:
        """
        Generate a Discord embed displaying poll results with vote counts and optionally voter names.
        Args:
            with_chart (bool, optional): Whether to include a chart image with the embed. Defaults to False.
        Returns:
            tuple[discord.Embed, io.BytesIO] | discord.Embed:
                - If with_chart is True: Returns a tuple containing the embed and chart image as BytesIO
                - If with_chart is False: Returns only the Discord embed
        The embed includes:
            - Poll title as the embed title
            - Vote counts for each option
            - Voter names (if show_name is enabled) with vote magnification indicators
            - Poll ID in the footer
        Notes:
            - Retrieves vote count data and poll options from the database
            - If show_name is enabled, displays voter mentions for each option
            - Vote magnification is shown in parentheses when not equal to 1
            - Chart generation is optional and only includes options with votes > 0
        """
        vote_count_data = self.sqldb.get_poll_vote_count(self.poll.poll_id, not self.poll.ban_alternate_account_voting)
        options_data = self.sqldb.get_poll_options(self.poll.poll_id)
        guild = self.bot.get_guild(self.poll.guild_id)

        if self.poll.show_name:
            user_vote_data = self.sqldb.get_users_poll(self.poll.poll_id, not self.poll.ban_alternate_account_voting)
            user_vote_list = {}
            for i in range(1, len(options_data) + 1):
                user_vote_list[str(i)] = []

            for i in user_vote_data:
                discord_id = i.discord_id
                vote_option = i.vote_option
                vote_magnification = i.vote_magnification

                user = guild.get_member(discord_id)
                username = user.mention if user else f"<@{discord_id}>"
                if vote_magnification != 1:
                    username += f"({vote_magnification})"
                user_vote_list[str(vote_option)].append(username)

        text = ""
        if with_chart:
            labels = []
            sizes = []

        for option in options_data:
            name = option.option_name
            id = option.option_id
            count = vote_count_data.get(str(id), 0)
            text += f"{name}： {count}票\n"

            if self.poll.show_name:
                text += ",".join(user_vote_list[str(id)]) + "\n"

            if with_chart and count > 0:
                labels.append(name)
                sizes.append(count)

        embed = BotEmbed.simple(self.poll.title, description=text)
        embed.set_footer(text=f"投票ID：{self.poll.poll_id}")

        if with_chart:
            return embed, self.generate_chart(labels, sizes)
        else:
            return embed

    def generate_chart(self, labels, sizes):
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots()

        # 圖表製作
        def data_string(s, d) -> str:
            t = int(round(s / 100.0 * float(sum(d))))  # 透過百分比反推原本的數值
            return f"{t}\n（{s:.1f}%）"

        # 字形
        matplotlib.rc("font", family="Microsoft JhengHei")
        matplotlib.rcParams["font.sans-serif"] = ["Microsoft JhengHei"]

        # 設置顏色
        colors = ["gold", "yellowgreen", "lightcoral", "lightskyblue"]

        # 設置圓餅圖的突出顯示
        # explode = (0.1, 0, 0, 0)  # 將第一塊突出顯示

        # 繪製圓餅圖
        ax.pie(sizes, labels=labels, colors=colors, autopct=lambda i: data_string(i, sizes), shadow=False, startangle=140)
        # plt.pie()

        # 添加標題
        ax.set_title(self.poll.title)
        # plt.title()

        image_buffer = io.BytesIO()
        plt.savefig(image_buffer, format="png", dpi=200, bbox_inches="tight")
        image_buffer.seek(0)

        return image_buffer


class ReactionRoleButton(discord.ui.Button):
    def __init__(self, dbdata: ReactionRoleOption):
        super().__init__(
            label=dbdata.title,
            style=dbdata.style if dbdata.style else discord.ButtonStyle.primary,
            emoji=dbdata.emoji,
            custom_id=f"ReactionRole_{dbdata.message_id}_{dbdata.role_id}",
        )
        self.role_id = dbdata.role_id

    async def callback(self, interaction):
        role = interaction.guild.get_role(self.role_id)
        if not role:
            await interaction.response.send_message(f"錯誤：身分組不存在，請聯絡管理員", ephemeral=True)
            return

        if interaction.user.get_role(self.role_id):
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"已移除 {role.name} 身分組！", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"已給予 {role.name} 身分組！", ephemeral=True)


class ReactionRoleView(discord.ui.View):
    def __init__(self, message_id, roles: list[ReactionRoleOption]):
        super().__init__(timeout=None)
        self.message_id = message_id

        for r in roles:
            self.add_item(ReactionRoleButton(r))

    async def on_error(self, error: Exception, item: discord.ui.Item, interaction: discord.Interaction):
        if isinstance(error, discord.Forbidden):
            await interaction.response.send_message(f"錯誤：我沒有權限給予或移除身分組，可能為我的身分組位階較低或缺少必要權限", ephemeral=True)
        else:
            await interaction.response.send_message(f"發生錯誤：{error}", ephemeral=True)
            log.error("ReactionRoleView error: %s / %s", item, error)


class GiveawayJoinButton(discord.ui.Button):
    def __init__(self, giveaway: Giveaway):
        super().__init__(label="參加抽獎", style=discord.ButtonStyle.primary, custom_id=f"giveaway_join_{giveaway.id}")

    async def callback(self, interaction: discord.Interaction):
        view: GiveawayView = self.view
        giveaway_user = view.sqldb.get_user_in_giveaway(view.giveaway.id, interaction.user.id)
        if giveaway_user:
            view.sqldb.delete(giveaway_user)
            await interaction.response.send_message(f"{interaction.user.mention} 離開了抽獎", ephemeral=True)
        else:
            giveaway_user = GiveawayUser(giveaway_id=view.giveaway.id, user_id=interaction.user.id, user_weight=1, join_at=nowtz())
            view.sqldb.add(giveaway_user)
            await interaction.response.send_message(f"{interaction.user.mention} 參加了抽獎！", ephemeral=True)


class GiveawayEndButton(discord.ui.Button):
    def __init__(self, giveaway: Giveaway):
        super().__init__(label="結束抽獎", style=discord.ButtonStyle.danger, custom_id=f"giveaway_end_{giveaway.id}")

    async def callback(self, interaction: discord.Interaction):
        view: GiveawayView = self.view
        if interaction.user.id == view.giveaway.creator_id or (view.bot and await view.bot.is_owner(interaction.user)):
            embed = view.end_giveaway()
            await interaction.message.edit(embed=embed, view=view)
        else:
            await interaction.response.send_message("只有發起人才能結束抽獎！", ephemeral=True)


class GiveawayView(discord.ui.View):
    def __init__(self, giveaway: Giveaway, bot: DiscordBot, timeout=None):
        super().__init__(timeout=timeout)
        self.giveaway = giveaway
        self.sqldb = bot.sqldb
        self.bot = bot
        self.Jsondb = bot.Jsondb
        if giveaway.is_on:
            self.add_item(GiveawayJoinButton(giveaway))
            self.add_item(GiveawayEndButton(giveaway))

    def embed(self):
        description = self.giveaway.description if self.giveaway.description else "按下下方按鈕開始抽獎！"
        description += f"\n- 抽出人數：{self.giveaway.winner_count} 人"
        description += f"\n- 舉辦人：{self.bot.get_user(self.giveaway.creator_id).mention}"
        description += f"\n- 開始時間：{format_dt(self.giveaway.created_at)}"
        if self.giveaway.end_at:
            description += f"\n- 結束時間：{format_dt(self.giveaway.end_at)}"
        embed = BotEmbed.general("抽獎系統", self.Jsondb.get_picture("dice_001"), title=f"{self.giveaway.prize_name}", description=description)
        embed.set_footer(text=f"抽獎ID：{self.giveaway.id}")
        embed.timestamp = self.giveaway.created_at
        return embed

    def result_embed(self, joiner_count: int):
        description = self.giveaway.description or "抽獎結束" if joiner_count else "沒有參加抽獎的用戶"
        description += f"\n- 中獎人數：{self.giveaway.winner_count} / {joiner_count} 人"
        description += f"\n- 舉辦人：{self.bot.get_user(self.giveaway.creator_id).mention}"
        description += f"\n- 開始時間：{format_dt(self.giveaway.created_at)}"
        description += f"\n- 結束時間：{format_dt(self.giveaway.end_at)}"
        embed = BotEmbed.general("抽獎系統", self.Jsondb.get_picture("dice_001"), title=f"{self.giveaway.prize_name}", description=description)
        embed.set_footer(text=f"抽獎ID：{self.giveaway.id}")
        return embed

    def end_giveaway(self):
        if not self.giveaway.end_at:
            self.giveaway.end_at = nowtz().replace(microsecond=0)
        self.giveaway.is_on = False
        self.clear_items()
        joiner = self.sqldb.get_giveaway_users(self.giveaway.id)
        joiner_ids = [i.user_id for i in joiner]
        weights = [i.user_weight for i in joiner]

        embed = self.result_embed(len(joiner_ids))
        if joiner_ids:
            winners_id = np.random.choice(joiner_ids, size=self.giveaway.winner_count, replace=False, p=np.array(weights) / sum(weights)).tolist() if len(joiner_ids) > self.giveaway.winner_count else joiner_ids
            self.sqldb.set_giveaway_winner(self.giveaway.id, winners_id)

            winners_mention = []
            for i in winners_id:
                user = self.bot.get_user(i)
                if user:
                    winners_mention.append(user.mention)
                else:
                    winners_mention.append(f"<@{i}>")
            embed.add_field(name="得獎者", value=", ".join(winners_mention), inline=False)

        self.sqldb.merge(self.giveaway)

        return embed

    def redraw_winner_giveaway(self, old_winner: GiveawayUser | None = None):
        if not old_winner:
            self.sqldb.reset_giveaway_winner(self.giveaway.id)
            redraw_count = self.giveaway.winner_count
        else:
            redraw_count = 1
            old_winner.is_winner = False
            self.sqldb.merge(old_winner)

        joiner = self.sqldb.get_giveaway_users(self.giveaway.id)
        joiner_ids = [i.user_id for i in joiner if not i.is_winner]
        weights = [i.user_weight for i in joiner if not i.is_winner]
        winners_id = [i.user_id for i in joiner if i.is_winner]
        winners_id.extend((np.random.choice(joiner_ids, size=redraw_count, replace=False, p=np.array(weights) / sum(weights)).tolist()) if len(joiner_ids) > redraw_count else joiner_ids)
        self.sqldb.set_giveaway_winner(self.giveaway.id, winners_id)

        winners_mention = []
        for i in winners_id:
            user = self.bot.get_user(i)
            if user:
                winners_mention.append(user.mention)
            else:
                winners_mention.append(f"<@{i}>")

        self.giveaway.redraw_count += 1
        self.sqldb.merge(self.giveaway)

        embed = self.result_embed(len(joiner))
        embed.add_field(name="得獎者", value=", ".join(winners_mention), inline=False)
        embed.set_footer(text=f"抽獎ID：{self.giveaway.id}，重新抽獎第 {self.giveaway.redraw_count} 次")
        return embed

    async def on_timeout(self):
        embed = self.end_giveaway()
        await self.message.edit(embed=embed, view=self)
        self.stop()


class McServerSelect(discord.ui.Select):
    def __init__(self, servers: list[McssServer]):
        options = [discord.SelectOption(label=server.name if server.name else f"伺服器 {server.server_id}", value=server.server_id, description=server.description) for server in servers]
        super().__init__(placeholder="選擇伺服器", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        view: McServerPanel = self.view
        view.server_id = self.values[0]  # pyright: ignore[reportOptionalSubscript]
        embed = to_embed(view)
        await interaction.response.edit_message(embed=embed, view=view)


class McServerPanel(discord.ui.View):
    def __init__(self, bot: DiscordBot):
        super().__init__(timeout=600)
        self.server_id: str | None = None
        self.bot = bot
        self.mcss_api = bot.api.mcss_api
        self.add_item(McServerSelect(self.mcss_api.get_servers()))

    async def on_timeout(self):
        self.clear_items()
        if not self.server_id:
            await self.message.delete()
        else:
            await self.message.edit(view=self)
        self.stop()

    def embed(self):
        if not self.server_id:
            return BotEmbed.simple("請選擇伺服器", "使用下方的選單來選擇伺服器")
        server = self.mcss_api.get_server_detail(self.server_id)
        if not server:
            return BotEmbed.simple("伺服器未找到", "請確認伺服器ID是否正確")

        embed = to_embed(server)
        return embed

    @discord.ui.button(label="啟動伺服器", style=discord.ButtonStyle.primary)
    async def start_button_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        if not self.server_id:
            await interaction.followup.send("請先選擇伺服器", ephemeral=True)
            return

        if server := self.mcss_api.get_server_detail(self.server_id):
            if server.status == McssServerStatues.Running:
                await interaction.followup.send("🟢伺服器已經在運行中", ephemeral=True)
                return
            elif server.status == McssServerStatues.Stopped:
                self.mcss_api.excute_action(self.server_id, McssServerAction.Start)
                await interaction.followup.send("🟡已發送開啟指令，伺服器正在啟動...", ephemeral=True)

                server = self.mcss_api.get_server_detail(self.server_id)
                await interaction.edit_original_response(embed=to_embed(server))
                for _ in range(20):
                    await asyncio.sleep(10)
                    server = self.mcss_api.get_server_detail(self.server_id)
                    if server and server.status == McssServerStatues.Running:
                        await interaction.followup.send("🟢伺服器已開啟", ephemeral=True)
                        await interaction.edit_original_response(embed=to_embed(server))
                        return

        await interaction.followup.send("伺服器啟動超時，請確認伺服器狀態", ephemeral=True)

    @discord.ui.button(label="關閉伺服器", style=discord.ButtonStyle.danger)
    async def stop_button_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        if not self.server_id:
            await interaction.followup.send("請先選擇伺服器", ephemeral=True)
            return

        if server := self.mcss_api.get_server_detail(self.server_id):
            if server.status == McssServerStatues.Stopped:
                await interaction.followup.send("🛑伺服器已處於關閉狀態", ephemeral=True)
                return
            elif server.status == McssServerStatues.Running:
                self.mcss_api.excute_action(self.server_id, McssServerAction.Stop)
                await interaction.followup.send("🟠伺服器正在關閉...", ephemeral=True)

                server = self.mcss_api.get_server_detail(self.server_id)
                await interaction.edit_original_response(embed=to_embed(server))
                for _ in range(20):
                    await asyncio.sleep(10)
                    server = self.mcss_api.get_server_detail(self.server_id)
                    if server and server.status == McssServerStatues.Stopped:
                        await interaction.followup.send("🛑伺服器已關閉", ephemeral=True)
                        await interaction.edit_original_response(embed=to_embed(server))
                        return

        await interaction.followup.send("伺服器關閉超時，請確認伺服器狀態", ephemeral=True)

    @discord.ui.button(label="取得IP位置", style=discord.ButtonStyle.secondary)
    async def ip_button_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        if not self.server_id:
            await interaction.followup.send("請先選擇伺服器", ephemeral=True)
            return

        if server := self.mcss_api.get_server_detail(self.server_id):
            ip = find_radmin_vpn_network()
            if not ip:
                await interaction.followup.send("無法獲取Radmin VPN IP", ephemeral=True)
                return

            port = server.find_port() or "XXXXX（請確認這個數字是多少）"
            if port == 25565:
                port = "25565（預設端口可省略）"

            await interaction.followup.send(f"伺服器IP位置：`{ip}:{port}`")
        else:
            await interaction.followup.send("伺服器未找到", ephemeral=True)


class TicketChannelView(discord.ui.View):
    def __init__(self, sqldb: SQLRepository, channel: discord.TextChannel, creator: discord.Member):
        super().__init__(timeout=None)
        self.sqldb = sqldb
        self.channel = channel
        self.creator = creator
        self.add_item(self.TicketCloseButton(channel.id))

    class TicketCloseButton(discord.ui.Button):
        def __init__(self, channel_id: int):
            super().__init__(label="關閉頻道", style=discord.ButtonStyle.danger, custom_id=f"close_ticket_channel_{channel_id}")

        async def callback(self, interaction: discord.Interaction):
            view: TicketChannelView = self.view
            if interaction.user == view.creator or (view.creator.guild and await view.creator.guild.get_member(interaction.user.id).guild_permissions.manage_channels):
                ticket = view.sqldb.get_ticket_channel(view.channel.id)
                if ticket:
                    ticket.closed_at = nowtz()
                    ticket.closer_id = interaction.user.id
                    view.sqldb.merge(ticket)

                # await self.channel.delete()
                overwrites = view.channel.overwrites
                for target in overwrites:
                    overwrites[target].send_messages = False
                await view.channel.edit(overwrites=overwrites)
                view.clear_items()
                await interaction.response.edit_message(view=view)
                await interaction.followup.send(content=f"頻道已由{interaction.user.mention}鎖定")
            else:
                await interaction.response.send_message(content="只有頻道建立者或管理員可以關閉頻道", ephemeral=True)


class TicketLobbyView(discord.ui.View):
    def __init__(self, sqldb: SQLRepository, channel_id: int):
        super().__init__(timeout=None)
        self.sqldb = sqldb
        self.add_item(self.CreateTicketButton(channel_id))

    class CreateTicketButton(discord.ui.Button):
        def __init__(self, channel_id: int):
            super().__init__(label="建立私人頻道", style=discord.ButtonStyle.primary, custom_id=f"create_ticket_{channel_id}")

        async def callback(self, interaction: discord.Interaction):
            view: TicketLobbyView = self.view
            channel = await interaction.channel.category.create_text_channel(name=f"ticket-{interaction.user.name}", topic=f"Ticket channel for {interaction.user} ({interaction.user.id})")
            msg = await channel.send(f"{interaction.user.mention}，你好！請在此頻道描述你的問題，我們會盡快協助你。", view=TicketChannelView(view.sqldb, channel, interaction.user))
            view.sqldb.merge(TicketChannel(channel_id=channel.id, guild_id=interaction.guild.id, creator_id=interaction.user.id, created_at=nowtz(), close_message_id=msg.id))
            await msg.pin()
            await interaction.response.send_message(f"已建立私人頻道，請前往{channel.mention}進行對話", ephemeral=True)


class VIPApplicationForm(discord.ui.Modal):
    def __init__(self, sqldb: SQLRepository):
        super().__init__(title="VIP申請表單")
        self.sqldb = sqldb
        self.add_item(discord.ui.InputText(label="請輸入你希望的VIP等級", style=discord.InputTextStyle.short, required=False))
        self.add_item(discord.ui.InputText(label="請輸入你的備註", style=discord.InputTextStyle.long, required=False))

    async def callback(self, interaction: discord.Interaction):
        vip_level = self.children[0].value
        remarks = self.children[1].value
        form = HappycampApplicationForm(discord_id=interaction.user.id, content=f"申請VIP等級：{vip_level}\n備註：{remarks}", submitted_at=nowtz(), change_vip_level=vip_level)
        self.sqldb.add(form)

        channel = interaction.client.get_channel(get_settings().VIP_ADMIN_CHANNEL)
        if channel:
            await channel.send(embed=to_embed(form))
        else:
            log.warning("無法找到VIP申請審核頻道，請確認頻道ID是否正確")

        await interaction.response.send_message("申請提交完成", ephemeral=True)


class VIPView(discord.ui.View):
    def __init__(self, sqldb: SQLRepository):
        super().__init__()
        self.sqldb = sqldb

    @discord.ui.button(label="取得當前等級", style=discord.ButtonStyle.primary)
    async def button_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        vip = self.sqldb.get_vip(interaction.user.id)
        if not vip:
            await interaction.response.send_message("你無法使用此功能", ephemeral=True)
            return

        description = f"- VIP等級：{vip.vip_level}\n- 取得時間：{vip.created_at}"
        embed = BotEmbed.general("VIP系統", title=f"{interaction.user.name} 的VIP資訊", description=description)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="申請更高等級", style=discord.ButtonStyle.primary)
    async def button2_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        vip = self.sqldb.get_vip(interaction.user.id)
        if not vip:
            await interaction.response.send_message("你無法使用此功能", ephemeral=True)
            return

        await interaction.response.send_modal(VIPApplicationForm(self.sqldb))


class VIPAuditView(discord.ui.View):
    def __init__(self, form: HappycampApplicationForm, sqldb: SQLRepository):
        super().__init__()
        self.form = form
        self.sqldb = sqldb

    async def on_timeout(self):
        try:
            await self.message.delete()
        except discord.errors.NotFound:
            pass
        self.stop()

    def embed(self):
        status_dict = {0: "待審核", 1: "已通過", 2: "已拒絕"}
        embed = discord.Embed(
            title=f"申請表單 #{self.form.form_id} - {status_dict.get(self.form.status, '未知狀態')}",
            description=f"- 申請人：<@{self.form.discord_id}>\n- 提交時間：{self.form.submitted_at.strftime('%Y-%m-%d %H:%M:%S')}\n- 審核時間：{self.form.reviewed_at.strftime('%Y-%m-%d %H:%M:%S') if self.form.reviewed_at else '尚未審核'}\n- 審核者：{f'<@{self.form.reviewer_id}>' if self.form.reviewer_id else '尚未審核'}\n- 審核意見：{self.form.review_comment if self.form.review_comment else '無'}",
            color=0xC4E9FF,
        )
        embed.add_field(name="申請內容", value=self.form.content or "無")
        embed.add_field(name="變更 VIP 等級", value=str(self.form.change_vip_level) if self.form.change_vip_level is not None else "無")
        return embed

    @discord.ui.button(label="通過", style=discord.ButtonStyle.success)
    async def approve_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        remark = self.FormRemark()
        await interaction.response.send_modal(remark)
        if await remark.wait():
            self.form.review_comment = remark.children[0].value
            self.form.status = 1
            self.form.reviewed_at = nowtz()
            self.form.reviewer_id = interaction.user.id
            self.sqldb.merge(self.form)
            await interaction.edit_original_message(embed=to_embed(self.form))
            await interaction.followup.send(content="已通過申請", ephemeral=True)

            if self.form.change_vip_level is not None:
                vip = self.sqldb.get_vip(self.form.discord_id)
                if not vip:
                    vip = HappycampVIP(discord_id=self.form.discord_id, vip_level=self.form.change_vip_level, created_at=nowtz(), updated_at=nowtz())
                else:
                    vip.vip_level = self.form.change_vip_level
                    vip.updated_at = nowtz()

                self.sqldb.merge(vip)

                vip_channels = self.sqldb.get_vip_channels()
                member = interaction.guild.get_member(self.form.discord_id)
                assert member is not None, "會員不存在於伺服器中"
                for vip_c in vip_channels:
                    channel = interaction.guild.get_channel(vip_c.channel_id)
                    if not channel:
                        log.error("VIP頻道不存在，無法更新權限，頻道ID：%s", vip_c.channel_id)
                        continue

                    overwrite = channel.overwrites_for(member)
                    if vip.vip_level >= vip_c.vip_level and overwrite.view_channel is not True:
                        await channel.set_permissions(member, overwrite=discord.PermissionOverwrite(view_channel=True, send_messages=True))
                    elif overwrite.view_channel is True:
                        await channel.set_permissions(member, overwrite=None)
                # user = interaction.client.get_user(self.form.discord_id)
                # if user:
                #     try:
                #         await user.send(f"你的VIP等級已被提升至 {self.form.change_vip_level}！")
                #     except Exception as e:
                #         log.error(f"無法傳送VIP等級提升通知給用戶 {self.form.discord_id}：{e}")

        else:
            await interaction.response.send_message("已取消審核", ephemeral=True)

    @discord.ui.button(label="拒絕", style=discord.ButtonStyle.danger)
    async def deny_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        remark = self.FormRemark()
        await interaction.response.send_modal(remark)
        if await remark.wait():
            self.form.review_comment = remark.children[0].value
            self.form.status = 2
            self.form.reviewed_at = nowtz()
            self.form.reviewer_id = interaction.user.id
            self.sqldb.merge(self.form)
            await interaction.edit_original_message(embed=to_embed(self.form))
            await interaction.followup.send(content="已拒絕申請", ephemeral=True)
        else:
            await interaction.response.send_message("已取消審核", ephemeral=True)

    class FormRemark(discord.ui.Modal):
        def __init__(self):
            super().__init__(title="審核意見")
            self.add_item(discord.ui.InputText(label="請輸入審核意見", style=discord.InputTextStyle.long, required=False))

        async def callback(self, interaction: discord.Interaction):
            await interaction.response.send_message("已填入審核意見", ephemeral=True)


class RegisterView(discord.ui.View):
    def __init__(self, sqldb: SQLRepository):
        super().__init__(timeout=60)
        self.sqldb = sqldb

    @discord.ui.button(label="直接開始（建立新用戶）", style=discord.ButtonStyle.green)
    async def create_new(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.sqldb.add_cloud_user_by_discord(interaction.user.id, interaction.user.display_name)
        await interaction.response.edit_message(content="✅ 註冊成功！請重新輸入指令。", view=None)
        self.stop()

    @discord.ui.button(label="我有其他帳號（進行綁定）", style=discord.ButtonStyle.secondary)
    async def link_existing(self, button: discord.ui.Button, interaction: discord.Interaction):
        from v2_starDiscord.ui.modal import LinkAccountModal

        await interaction.response.send_modal(LinkAccountModal(self.sqldb))
