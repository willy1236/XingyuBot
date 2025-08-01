import asyncio
import math
import random
import re
from datetime import date, datetime, timedelta

import discord
from discord.commands import OptionChoice, SlashCommandGroup
from discord.errors import Forbidden, NotFound
from discord.ext import commands, pages
from discord.utils import format_dt

from starlib import BotEmbed, ChoiceList, log, sclient, tz
from starlib.dataExtractor import GoogleCloud
from starlib.instance import *
from starlib.models.mysql import DiscordUser, Giveaway
from starlib.types import Coins
from starlib.utils import converter, create_only_role_list, create_role_magification_dict, find, random_color

from ..extension import Cog_Extension
from ..uiElement.view import DeleteAddRoleView, GiveawayView, PollView, TRPGPlotView
from .bot_event import check_registration

bet_option = ChoiceList.set("bet_option")
position_option = ChoiceList.set("position_option")
party_option = ChoiceList.set("party_option")

trpg_plot_start = [OptionChoice(name="劇情開始：米爾（威立）", value=1)]

async def trpg_plot_autocomplete(ctx: discord.AutocompleteContext):
    return trpg_plot_start if not ctx.options["故事id"] else []

class command(Cog_Extension):
    bet = SlashCommandGroup("bet", "賭盤相關指令")
    role = SlashCommandGroup("role", "身分組管理指令", guild_ids=happycamp_guild)
    poll = SlashCommandGroup("poll", "投票相關指令")
    party = SlashCommandGroup("party", "政黨相關指令", guild_ids=happycamp_guild)
    registration = SlashCommandGroup("registration", "戶籍相關指令", guild_ids=happycamp_guild)
    giveaway = SlashCommandGroup("giveaway", "抽獎相關指令")
    register = SlashCommandGroup("register", "註冊相關指令")
    date_cmd = SlashCommandGroup("date", "日期相關指令")

    @role.command(description="查詢加身分組的數量")
    async def count(
        self, ctx, user_list: discord.Option(str, required=False, name="要查詢的用戶", description="多個用戶請用空格隔開，或可輸入default查詢常用人選")
    ):
        await ctx.defer()
        if not user_list:
            user_list = [ctx.author.id]
        elif "default" in user_list:
            user_list = [419131103836635136, 528935362199027716, 465831362168094730, 539405949681795073, 723435216244572160, 490136735557222402]
        else:
            user_list = user_list.split()

        embed = BotEmbed.simple("身分組計算結果")
        for i in user_list:
            user = await find.user(ctx, i)
            if user:
                id = user.id
                record = sclient.sqldb.get_role_save_count(id)
                embed.add_field(name=user.name, value=record, inline=False)
        await ctx.respond(embed=embed)

    @role.command(description="加身分組")
    @commands.bot_has_permissions(manage_roles=True)
    @commands.cooldown(rate=1, per=5)
    async def add(
        self,
        ctx: discord.ApplicationContext,
        name: discord.Option(str, name="身分組名", description="新身分組名稱"),
        user_list: discord.Option(str, required=False, name="要加身份組的用戶", description="多個用戶請用空格隔開"),
    ):
        await ctx.defer()
        permission = discord.Permissions.none()
        r, g, b = random_color(200)
        color = discord.Colour.from_rgb(r, g, b)
        new_role = await ctx.guild.create_role(name=name, permissions=permission, color=color)
        added_user = []

        if user_list:
            for user in user_list.split():
                user = await find.user(ctx, user)
                if user and user != self.bot.user:
                    try:
                        main_account = sclient.sqldb.get_main_account(user.id)
                        if main_account:
                            user = ctx.guild.get_member(main_account)
                    except Exception as e:
                        log.warning("查詢主帳號時發生錯誤", exc_info=e)

                    await user.add_roles(new_role, reason="指令:加身分組")
                    added_user.append(user.mention)
                    if ctx.guild.id == happycamp_guild[0] and not user.get_role(877934319249797120):
                        divider_role = ctx.guild.get_role(877934319249797120)
                        await user.add_roles(divider_role, reason="指令:加身分組")

                elif user == self.bot.user:
                    await ctx.respond("請不要加我身分組好嗎")
                elif user and user.bot:
                    await ctx.respond("請不要加機器人身分組好嗎")

        view = DeleteAddRoleView(new_role, ctx.author)
        if added_user:
            view.message = await ctx.respond(f"已添加 {new_role.name} 給{' '.join(added_user)}", view=view)
        else:
            view.message = await ctx.respond(f"已創建 {new_role.name} 身分組", view=view)

    @role.command(description="儲存身分組")
    @commands.cooldown(rate=1, per=5)
    @commands.is_owner()
    @commands.bot_has_permissions(manage_roles=True)
    async def save(self, ctx: discord.ApplicationContext):
        await ctx.defer()
        guild = self.bot.get_guild(happycamp_guild[0])

        for role in guild.roles:
            if role.id == 877934319249797120 or role.is_default():
                break

            for user in role.members:
                try:
                    # 1062
                    sclient.sqldb.add_role_save(user.id, role)
                    log.info(f"新增:{role.name}")
                except Exception as e:
                    log.warning(f"儲存身分組時發生錯誤", role.name, exc_info=e)

        await ctx.respond("身分組儲存完成", delete_after=5)

    @role.command(description="清除身分組")
    @commands.is_owner()
    async def rsmove(self, ctx):
        await ctx.defer()
        guild = self.bot.get_guild(happycamp_guild[0])
        if not guild.get_role(877934319249797120):
            await ctx.respond('錯誤：找不到"加身分組"', delete_after=5)
            return

        for role in guild.roles:
            if role.id == 877934319249797120:
                break
            if role.is_default():
                continue
            log.info(f"已移除:{role.name}")
            await role.delete()
            await asyncio.sleep(0.5)

        await ctx.respond("身分組清理完成", delete_after=5)

    @role.command(description="查詢加身分組紀錄")
    async def record(
        self, ctx: discord.ApplicationContext, user: discord.Option(discord.Member, name="欲查詢的成員", description="留空以查詢自己", default=None)
    ):
        await ctx.defer()
        user = user or ctx.author
        record = sclient.sqldb.get_role_save(user.id)
        if not record:
            raise commands.errors.ArgumentParsingError("沒有此用戶的紀錄")

        page = [BotEmbed.simple(f"{user.name} 加身分組紀錄") for _ in range(math.ceil(len(record) / 10))]
        for i, data in enumerate(record):
            role_name = data.role_name
            time = data.time
            page[int(i / 10)].add_field(name=role_name, value=time, inline=False)

        paginator = pages.Paginator(pages=page, use_default_buttons=True, loop_pages=True)
        await paginator.respond(ctx.interaction, ephemeral=False)

    @role.command(description="加身分組排行榜")
    async def ranking(self, ctx, ranking_count: discord.Option(int, name="排行榜人數", default=5, min_value=1, max_value=30)):
        await ctx.defer()
        dbdata = sclient.sqldb.get_role_save_count_list()
        embed = BotEmbed.simple("加身分組排行榜")
        i = 1
        for id in dbdata:
            try:
                count = dbdata[id]
                user = self.bot.get_user(id)
                username = user.mention if user else id
                embed.add_field(name=f"第{i}名", value=f"{username} {count}個", inline=False)
                i += 1
                if i > ranking_count:
                    break
            except IndexError:
                break
        await ctx.respond(embed=embed)

    @role.command(description="查詢特殊身分組")
    async def special(self, ctx):
        await ctx.defer()
        lst = sclient.sqldb.get_all_backup_roles()
        if not lst:
            await ctx.respond("查詢失敗")
            return

        page = [list() for _ in range(math.ceil(len(lst) / 3))]
        for i, role in enumerate(lst):
            page[int(i / 3)].append(role.embed(self.bot))

        paginator = pages.Paginator(pages=page, use_default_buttons=True, loop_pages=True)
        await paginator.respond(ctx.interaction, ephemeral=False)

    @commands.slash_command(description="抽抽試手氣")
    @commands.cooldown(rate=1, per=2)
    async def draw(self, ctx, times: discord.Option(int, name="抽卡次數", description="可輸入1~1000的整數", default=1, min_value=1, max_value=1000)):
        result = {"six": 0, "five": 0, "four": 0, "three": 0}
        user_id = str(ctx.author.id)
        six_list = []
        six_list_100 = []
        guaranteed = 100

        dbuser = sclient.sqldb.get_dcuser(user_id)
        if dbuser.guaranteed is None:
            dbuser.guaranteed = 0

        for i in range(1, times + 1):
            choice = random.randint(1, 100)
            if choice == 1:
                result["six"] += 1
                six_list.append(str(i))
                dbuser.guaranteed = 0
            elif dbuser.guaranteed >= guaranteed - 1:
                result["six"] += 1
                six_list_100.append(str(i))
                dbuser.guaranteed = 0

            elif choice >= 2 and choice <= 11:
                result["five"] += 1
                dbuser.guaranteed += 1
            elif choice >= 12 and choice <= 41:
                result["four"] += 1
                dbuser.guaranteed += 1
            else:
                result["three"] += 1
                dbuser.guaranteed += 1

        sclient.sqldb.merge(dbuser)
        embed = BotEmbed.lottery()
        embed.add_field(name="抽卡結果", value=f"六星x{result['six']} 五星x{result['five']} 四星x{result['four']} 三星x{result['three']}", inline=False)
        embed.add_field(name="保底累積", value=dbuser.guaranteed, inline=False)
        if six_list:
            embed.add_field(name="六星出現", value=",".join(six_list), inline=False)
        if six_list_100:
            embed.add_field(name="保底六星", value=",".join(six_list_100), inline=False)
        await ctx.respond(embed=embed)

    @commands.slash_command(description="TRPG擲骰")
    async def dice(
        self,
        ctx,
        dice_n: discord.Option(int, name="骰子數", description="總共擲幾顆骰子，預設為1", default=1, min_value=1),
        dice: discord.Option(int, name="面骰", description="骰子為幾面骰，預設為100", default=100, min_value=1),
    ):
        sum = 0
        for _ in range(dice_n):
            sum += random.randint(1, dice)
        await ctx.respond(f"{dice_n}顆{dice}面骰（{dice_n}d{dice}）結果：{sum}")

    @bet.command(description="賭盤下注")
    async def place(
        self,
        ctx,
        bet_id_str: discord.Option(str, name="賭盤", description="", required=True),
        choice: discord.Option(int, name="下注顏色", description="", required=True, choices=bet_option),
        money: discord.Option(int, name="下注點數", description="", required=True, min_value=1),
    ):
        bet_id = int(bet_id_str)
        if bet_id == ctx.author.id:
            await ctx.respond("錯誤：你不可以下注自己的賭盤", ephemeral=True)
            return

        bet = sclient.sqldb.get_bet(bet_id)
        if not bet:
            await ctx.respond("編號錯誤：沒有此編號的賭盤喔", ephemeral=True)
            return
        elif not bet.is_on:
            await ctx.respond("錯誤：此賭盤已經關閉了喔", ephemeral=True)
            return

        user_coin = sclient.sqldb.get_coin(ctx.author.id)

        if user_coin.stardust < money:
            await ctx.respond("點數錯誤：你沒有那麼多點數", ephemeral=True)
            return

        user_bet = sclient.sqldb.place_bet(bet_id, choice, money)
        if user_bet:
            user_coin.stardust -= money
            sclient.sqldb.merge(user_coin)
            await ctx.respond("下注完成!")

    @bet.command(name="create", description="創建賭盤")
    async def create_bet(
        self,
        ctx,
        title: discord.Option(str, name="賭盤標題", description="", required=True),
        pink: discord.Option(str, name="粉紅幫標題", description="", required=True),
        blue: discord.Option(str, name="藍藍幫標題", description="", required=True),
        time: discord.Option(int, name="賭盤開放時間", description="", required=True, min_value=10, max_value=600),
    ):
        bet_id: int = ctx.author.id
        bet = sclient.sqldb.get_bet_data(bet_id)
        if bet:
            await ctx.respond("錯誤：你已經創建一個賭盤了喔", ephemeral=True)
            return

        sclient.sqldb.create_bet(bet_id, title, pink, blue)

        embed = BotEmbed.simple(title="賭盤", description=f"編號: {bet_id}")
        embed.add_field(name="賭盤內容", value=title, inline=False)
        embed.add_field(name="粉紅幫", value=pink, inline=False)
        embed.add_field(name="藍藍幫", value=blue, inline=False)
        await ctx.respond(embed=embed)
        await asyncio.sleep(delay=time)

        await ctx.send(f"編號{bet_id}：下注時間結束")
        sclient.sqldb.update_bet(bet_id)

    @bet.command(description="結束賭盤")
    async def end(self, ctx, end: discord.Option(str, name="獲勝下注顏色", description="", required=True, choices=bet_option)):
        bet_id = str(ctx.author.id)
        # 錯誤檢測
        bet = sclient.sqldb.get_bet_data(bet_id)
        if bet["IsOn"]:
            await ctx.respond("錯誤：此賭盤的開放下注時間尚未結束", ephemeral=True)
            return

        # 計算雙方總點數
        total = sclient.sqldb.get_bet_total(bet_id)

        # 偵測是否兩邊皆有人下注
        if total[0] and total[1]:
            # 獲勝者設定
            winners = sclient.sqldb.get_bet_winner(bet_id, end)
            # 前置準備
            pink_total = total[0]
            blue_total = total[1]
            if pink_total > blue_total:
                mag = pink_total / blue_total
            else:
                mag = blue_total / pink_total
            # 結果公布
            if end == "pink":
                await ctx.respond(f"編號{bet_id}：恭喜粉紅幫獲勝!")
            elif end == "blue":
                await ctx.respond(f"編號{bet_id}：恭喜藍藍幫獲勝!")
            # 點數計算
            for i in winners:
                pt_add = i["money"] * (mag + 1)
                sclient.sqldb.update_coins(i["user_id"], "add", Coins.Point, pt_add)

        else:
            users = sclient.sqldb.get_bet_winner(bet_id, "blue")
            for i in users:
                sclient.sqldb.update_coins(i["user_id"], "add", Coins.Point, i["money"])

            users = sclient.sqldb.get_bet_winner(bet_id, "pink")
            for i in users:
                sclient.sqldb.update_coins(i["user_id"], "add", Coins.Point, i["money"])
            await ctx.respond(f"編號{bet_id}：因為有一方沒有人選擇，所以此局平手，點數將歸還給所有人")

        # 更新資料庫
        sclient.sqldb.remove_bet(bet_id)

    @commands.user_command(name="你是誰")
    async def whois(self, ctx, member: discord.Member):
        user = sclient.sqldb.get_dcuser(member.id) or DiscordUser(discord_id=member.id)
        user_embed = BotEmbed.general(name="Discord資料", icon_url=member.avatar.url if member.avatar else None)
        main_account_id = sclient.sqldb.get_main_account(member.id)
        if main_account_id:
            main_account = self.bot.get_user(main_account_id).mention or main_account_id
            user_embed.description = f"{main_account} 的小帳"

        coins = sclient.sqldb.get_coin(member.id)
        user_embed.add_field(name="⭐星塵", value=coins.stardust)
        user_embed.add_field(name="PT點數", value=coins.point)
        user_embed.add_field(name="Rcoin", value=coins.rcoin)

        if user.max_sign_consecutive_days:
            user_embed.add_field(name="連續簽到最高天數", value=user.max_sign_consecutive_days)
        if user.meatball_times:
            user_embed.add_field(name="貢丸次數", value=user.meatball_times)
        if user.registration:
            guild = self.bot.get_guild(user.registration.guild_id)
            user_embed.add_field(name="戶籍", value=guild.name if guild else user.registration.guild_id)

        cuser = sclient.sqldb.get_cloud_user(member.id)
        cloud_user_embed = BotEmbed.general("使用者資料", icon_url=member.avatar.url if member.avatar else None)
        if cuser:
            cloud_user_embed.add_field(name="雲端共用資料夾", value="已共用" if cuser.drive_share_id else "未共用")
            cloud_user_embed.add_field(name="Twitch ID", value=cuser.twitch_id or "未設定")

        await ctx.respond(embeds=[user_embed, cloud_user_embed], ephemeral=True)

    @commands.user_command(name="禁言10秒")
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def timeout_10s(self, ctx, member: discord.Member):
        time = timedelta(seconds=10)
        await member.timeout_for(time, reason="指令：禁言10秒")
        await ctx.respond(f"已禁言{member.mention} 10秒", ephemeral=True)

    # @commands.user_command(name="不想理你生態區",guild_ids=main_guilds)
    @commands.user_command(name="懲戒集中營", guild_ids=happycamp_guild)
    # @commands.has_permissions(moderate_members=True)
    async def user_command2(self, ctx, member: discord.Member):
        await ctx.respond("開始執行", ephemeral=True)

        role = ctx.guild.get_role(1195407446315892888)
        await member.add_roles(role, reason="指令：懲戒集中營 開始")

        last_time = timedelta(seconds=20)
        embed = BotEmbed.simple_warn_sheet(member, ctx.author, datetime.now(), last=last_time, reason="懲戒集中營", title="已被懲戒")
        await self.bot.get_channel(1195406858056368189).send(embed=embed)

        channel = self.bot.get_channel(613760923668185121)
        for _ in range(int(last_time.total_seconds()) * 2):
            if member.voice and member.voice.channel != channel:
                await member.move_to(channel)
            await asyncio.sleep(0.5)
        await member.remove_roles(role, reason="指令：懲戒集中營 結束")

    @commands.slash_command(description="傳送訊息給機器人擁有者")
    @commands.cooldown(rate=1, per=10)
    async def feedback(self, ctx: discord.ApplicationContext, text: discord.Option(str, name="訊息", description="要傳送的訊息內容，歡迎提供各項建議")):
        await ctx.defer()
        await self.bot.feedback(self.bot, ctx, text)
        await ctx.respond("訊息已發送!", ephemeral=True, delete_after=3)

    @staticmethod
    def Autocomplete(ctx: discord.AutocompleteContext):
        return ["test"]

    @commands.slash_command(description="讓機器人選擇一樣東西")
    async def choice(
        self,
        ctx,
        args_str: discord.Option(str, name="選項", description="多個選項請用空格隔開"),
        times: discord.Option(int, name="次數", description="預設為1，可輸入1~10", default=1, min_value=1, max_value=10),
    ):
        args: list[str] = args_str.split()
        result = random.choices(args, k=times)
        await ctx.respond(f"我選擇：{', '.join(result)}")

    @poll.command(name="create", description="創建投票")
    async def create_poll(
        self,
        ctx: discord.ApplicationContext,
        title: discord.Option(str, name="標題", description="投票標題，限45字內"),
        options: discord.Option(str, name="選項", description="投票選項，最多輸入20項，每個選項請用英文,隔開"),
        show_name: discord.Option(bool, name="顯示投票人", description="預設為false，若投票人數多建議關閉", default=False),
        check_results_in_advance: discord.Option(bool, name="預先查看結果", description="預設為true", default=True),
        results_only_initiator: discord.Option(bool, name="僅限發起人能查看結果", description="預設為false", default=False),
        ban_alternate_account_voting: discord.Option(bool, name="是否禁止小帳投票", description="僅供特定群組使用，預設為false", default=False),
        number_of_user_votes: discord.Option(int, name="一人最多可投票數", description="預設為1", default=1, min_value=1, max_value=20),
        only_role: discord.Option(
            str, name="限制身分組", description="若提供。則只有擁有身分組才能投票，多個身分組以英文,隔開，身分組可輸入id、提及、名稱等", default=None
        ),
        role_magnification: discord.Option(
            str,
            name="身分組權重",
            description="若提供，擁有身分組的用戶票數將乘指定倍數，取最高，格式為：身分組1,權重,身分組2,權重...，身分組可輸入id、提及、名稱等",
            default=None,
        ),
    ):
        options = options.split(",")
        if len(options) > 20 or len(options) < 1:
            await ctx.respond("錯誤：投票選項超過20項或小於1項", ephemeral=True)
            return
        only_role_list = await create_only_role_list(only_role, ctx) if only_role else []
        role_magnification_dict = await create_role_magification_dict(role_magnification, ctx) if role_magnification else {}

        view = PollView.create(
            title,
            options,
            ctx.author.id,
            ctx.guild.id,
            ban_alternate_account_voting,
            show_name,
            check_results_in_advance,
            results_only_initiator,
            number_of_user_votes,
            only_role_list=only_role_list,
            role_magnification_dict=role_magnification_dict,
        )
        embed = view.embed(ctx.guild)
        message = await ctx.respond(embed=embed, view=view)
        view.poll.message_id = message.id
        sclient.sqldb.merge(view.poll)

    @commands.is_owner()
    @poll.command(description="重新創建投票介面")
    async def view(self, ctx, poll_id: discord.Option(int, name="投票id", description="")):
        dbdata = sclient.sqldb.get_poll(poll_id)
        if dbdata:
            view = PollView(dbdata, sqldb=sclient.sqldb, bot=self.bot)
            await ctx.respond(view=view, embed=view.embed(ctx.guild))
        else:
            await ctx.respond("錯誤：查無此ID")

    @poll.command(description="取得投票結果")
    async def result(
        self,
        ctx: discord.ApplicationContext,
        poll_id: discord.Option(int, name="投票id", description=""),
        show_name: discord.Option(bool, name="是否顯示投票人", description="非開發者使用無效", default=False),
    ):
        await ctx.defer()
        poll = sclient.sqldb.get_poll(poll_id)
        is_owner = self.bot.is_owner(ctx.author)
        if not poll:
            await ctx.respond("錯誤：查無此ID")
            return
        elif poll.creator_id != ctx.author.id and not is_owner:
            await ctx.respond("錯誤：你不是此投票的發起人")
            return

        if is_owner:
            poll.show_name = show_name
        view = PollView(poll, sclient.sqldb, self.bot)
        embed, image_buffer = view.results_embed(ctx.interaction, True)  # type: ignore
        await ctx.respond(embed=embed, file=discord.File(image_buffer, filename="pie.png"))

    @commands.slash_command(description="共用「94共用啦」雲端資料夾", guild_ids=main_guilds)
    async def drive(
        self, ctx: discord.ApplicationContext, email: discord.Option(str, name="gmail帳戶", description="要使用的Gmail帳戶，留空以移除資料", required=False)
    ):
        await ctx.defer()
        cuser = sclient.sqldb.get_cloud_user(ctx.author.id)
        fileId = "1bDtsLbOi5crIOkWUZbQmPq3dXUbwWEan"
        if not email:
            if cuser and cuser.email:
                GoogleCloud().remove_file_permissions(fileId, cuser.drive_share_id)
                cuser.drive_share_id = None
                cuser.email = None
                sclient.sqldb.merge(cuser)
                await ctx.respond(f"{ctx.author.mention}：google帳戶移除完成")
            else:
                await ctx.respond(f"{ctx.author.mention}：此帳號沒有設定過google帳戶")

            return

        if cuser and cuser.drive_share_id:
            await ctx.respond(f"{ctx.author.mention}：此帳號已經共用雲端資料夾了")
            return

        r = re.compile(r"@gmail.com")
        if not r.search(email):
            email += "@gmail.com"

        google_data = GoogleCloud().add_file_permissions(fileId, email)
        cuser.email = email
        cuser.drive_share_id = google_data["id"]
        sclient.sqldb.merge(cuser)
        msg = await ctx.respond(f"{ctx.author.mention}：已與 {email} 共用雲端資料夾")
        await self.bot.report(f"{ctx.author.mention} 已使用 {email} 共用雲端資料夾", msg)

    @party.command(description="加入政黨")
    async def join(self, ctx: discord.ApplicationContext, party_id: discord.Option(int, name="政黨", description="要參加的政黨", choices=party_option)):
        sclient.sqldb.join_party(ctx.author.id, party_id)
        dbdata = sclient.sqldb.get_party(party_id)
        role_id = dbdata.role_id
        try:
            role = ctx.guild.get_role(role_id)
            if role:
                await ctx.author.add_roles(role)
        except Exception:
            pass

        await ctx.respond(f"{ctx.author.mention} 已加入政黨 {dbdata.party_name}")

    @party.command(description="離開政黨")
    async def leave(self, ctx: discord.ApplicationContext, party_id: discord.Option(int, name="政黨", description="要離開的政黨", choices=party_option)):
        sclient.sqldb.leave_party(ctx.author.id, party_id)
        dbdata = sclient.sqldb.get_party(party_id)
        role_id = dbdata.role_id
        try:
            role = ctx.author.get_role(role_id)
            if role:
                await ctx.author.remove_roles(role)
        except Exception:
            pass

        await ctx.respond(f"{ctx.author.mention} 已退出政黨 {dbdata.party_name}")

    @party.command(description="政黨列表")
    async def list(self, ctx: discord.ApplicationContext):
        dbdata = sclient.sqldb.get_all_party_data()
        embed = BotEmbed.simple("政黨統計")
        for party, member_count in dbdata:
            creator = self.bot.get_user(party.creator_id)
            creator_mention = creator.mention if creator else f"<@{party.creator_id}>"
            embed.add_field(
                name=party.party_name,
                value=f"政黨ID：{party.party_id}\n政黨人數：{member_count}\n創黨人：{creator_mention}\n創黨日期：{party.created_at.strftime('%Y/%m/%d')}",
            )
        await ctx.respond(embed=embed)

    @registration.command(description="確認/更新戶籍")
    @commands.cooldown(rate=1, per=10)
    async def update(self, ctx):
        user = sclient.sqldb.get_dcuser(ctx.author.id)
        if user.registrations_id:
            guild = self.bot.get_guild(user.registration.guild_id)
            await ctx.respond(f"你已經註冊戶籍至 {guild.name if guild else user.registration.guild_id} 了")
            return

        guild_id = check_registration(ctx.author)
        if guild_id:
            guild = self.bot.get_guild(guild_id)
            resgistration = sclient.sqldb.get_resgistration_by_guildid(guild_id)
            role_guild = self.bot.get_guild(happycamp_guild[0])
            role = role_guild.get_role(resgistration.role_id)

            if role:
                await role_guild.get_member(ctx.author.id).add_roles(role)
            from starlib.models.mysql import DiscordUser

            duser = DiscordUser(discord_id=ctx.author.id, registrations_id=resgistration.registrations_id)
            sclient.sqldb.merge(duser)

            await ctx.respond(f"已註冊戶籍至 {guild.name}")
        else:
            await ctx.respond("你沒有可註冊的戶籍")

    @registration.command(description="設定戶籍")
    @commands.is_owner()
    @commands.cooldown(rate=1, per=10)
    async def set(self, ctx, user: discord.Option(discord.Member, name="用戶"), registrations_id: discord.Option(int, name="戶籍id")):
        resgistration = sclient.sqldb.get_resgistration(registrations_id)
        guild = self.bot.get_guild(resgistration.guild_id)

        role_guild = self.bot.get_guild(happycamp_guild[0])
        role = role_guild.get_role(resgistration.role_id)

        if role:
            await role_guild.get_member(user.id).add_roles(role)
        from starlib.models.mysql import DiscordUser

        duser = DiscordUser(discord_id=user.id, registrations_id=resgistration.registrations_id)
        sclient.sqldb.add(duser)

        await ctx.respond(f"已註冊戶籍至 {guild.name}")

    @registration.command(description="批量設定戶籍")
    @commands.cooldown(rate=1, per=10)
    async def batchset(self, ctx, role: discord.Option(discord.Role, name="要批量驗證的身分組")):
        await ctx.defer()
        results_text = []
        role_guild = self.bot.get_guild(happycamp_guild[0])
        from starlib.models.mysql import DiscordUser

        for member in role.members:
            member: discord.Member
            user = sclient.sqldb.get_dcuser(member.id)
            if user and user.registrations_id:
                guild = self.bot.get_guild(user.registration.guild_id)
                results_text.append(f"{member.display_name}：已經註冊戶籍至 {guild.name if guild else user.registration.guild_id}")
                continue

            guild_id = check_registration(member)
            if guild_id:
                guild = self.bot.get_guild(guild_id)
                resgistration = sclient.sqldb.get_resgistration_by_guildid(guild_id)
                role = role_guild.get_role(resgistration.role_id)

                if role:
                    await role_guild.get_member(member.id).add_roles(role)

                duser = DiscordUser(discord_id=member.id, registrations_id=resgistration.registrations_id)
                sclient.sqldb.merge(duser)

            results_text.append(f"{member.display_name}：已註冊戶籍至 {guild.name}")
        else:
            results_text.append(f"{member.display_name}：沒有可註冊的戶籍")

        await ctx.respond("\n".join(results_text))

    @commands.is_owner()
    @registration.command(description="確認戶籍")
    async def check(self, ctx: discord.ApplicationContext, member: discord.Option(discord.Member, required=True, name="成員")):
        await ctx.defer()
        from .bot_event import check_registration

        embed = BotEmbed.simple("戶籍確認")
        guild_id = check_registration(member)
        guild = self.bot.get_guild(guild_id)
        if guild_id:
            embed.add_field(name="戶籍資格", value=f"{guild.name if guild else '伺服器'}（{guild_id}）", inline=False)
        else:
            embed.add_field(name="戶籍資格", value=f"目前尚無法取得", inline=False)

        dcuser = sclient.sqldb.get_dcuser(member.id)
        if dcuser.registrations_id:
            guild = self.bot.get_guild(dcuser.registration.guild_id)
            embed.add_field(name="已註冊戶籍", value=f"{guild.name}（{guild.id}）" if guild else dcuser.registration.guild_id, inline=False)
        else:
            embed.add_field(name="已註冊戶籍", value="沒有註冊戶籍", inline=False)
        await ctx.respond(embed=embed, ephemeral=True)

    @register.command(name="role", description="將身分組保存至資料庫")
    @commands.is_owner()
    async def register_role(
        self,
        ctx: discord.ApplicationContext,
        role: discord.Option(discord.Role, name="保存的身分組"),
        description: discord.Option(str, name="描述", description="保存的身分組描述"),
        delete_role: discord.Option(bool, name="保存後是否刪除身分組", default=False),
        remove_member: discord.Option(bool, name="保存後是否清空身分組成員", default=False),
    ):
        sclient.sqldb.backup_role(role, description)
        await ctx.respond(f"已將 {role.name} 身分組儲存")

        # 身分組儲存後執行確保資料完整
        if delete_role:
            await role.delete()
            await ctx.send(f"已將 {role.name} 刪除")
        elif remove_member:
            for member in role.members:
                await member.remove_roles(role)
                await asyncio.sleep(1)
            await ctx.send(f"已將 {role.name} 成員清空")

    @register.command(name="category", description="將頻道分類保存至資料庫")
    @commands.is_owner()
    async def register_category(
        self,
        ctx: discord.ApplicationContext,
        category: discord.Option(discord.CategoryChannel, name="保存的頻道分類"),
        description: discord.Option(str, name="描述", description="保存的頻道分類描述"),
        delete_category: discord.Option(bool, name="保存後是否刪除頻道分類", default=False),
    ):
        assert isinstance(category, discord.CategoryChannel), "必須提供一個頻道分類"
        sclient.sqldb.backup_category(category, description)
        await ctx.respond(f"已將 {category.name} 頻道分類儲存")

        # 頻道分類儲存後執行確保資料完整
        if delete_category:
            await category.delete()
            await ctx.send(f"已將 {category.name} 刪除")

    @register.command(name="channel", description="將頻道保存至資料庫")
    @commands.is_owner()
    async def register_channel(
        self,
        ctx: discord.ApplicationContext,
        channel: discord.Option(discord.abc.GuildChannel, name="保存的頻道"),
        description: discord.Option(str, name="描述", description="保存的頻道描述"),
        register_message: discord.Option(bool, name="是否將頻道的訊息儲存至資料庫", default=False),
        delete_channel: discord.Option(bool, name="保存後是否刪除頻道", default=False),
    ):
        assert isinstance(channel, discord.abc.GuildChannel), "必須提供一個頻道"
        sclient.sqldb.backup_channel(channel, description)
        await ctx.respond(f"已將 {channel.name} 頻道儲存")

        if register_message:
            assert isinstance(channel, discord.abc.Messageable), "必須提供一個頻道"
            messages = await channel.history(limit=None, oldest_first=True).flatten()
            sclient.sqldb.backup_messages(messages)
            await ctx.send(f"已將 {channel.name} 頻道的訊息儲存至資料庫")

        # 頻道儲存後執行確保資料完整
        if delete_channel:
            await channel.delete()
            await ctx.send(f"已將 {channel.name} 刪除")

    @register.command(name="message", description="將訊息保存至資料庫")
    @commands.is_owner()
    async def register_message(
        self,
        ctx: discord.ApplicationContext,
        message_str: discord.Option(str, name="保存的訊息id"),
        description: discord.Option(str, name="描述", description="保存的訊息描述", default=None),
    ):
        message = self.bot.get_message(int(message_str)) or await ctx.channel.fetch_message(int(message_str))
        if not message:
            await ctx.respond("錯誤：無法找到指定的訊息", ephemeral=True)
            return
        assert isinstance(message, discord.Message), "必須提供一個訊息"
        sclient.sqldb.backup_message(message, description)
        await ctx.respond(f"已將{message.jump_url}儲存")

    @commands.slash_command(description="取得邀請連結")
    async def getinvite(self, ctx, invite_url: discord.Option(str, name="邀請連結網址")):
        invite = await self.bot.fetch_invite(invite_url)
        guild = self.bot.get_guild(invite.guild.id)
        embed = BotEmbed.simple("邀請連結")
        embed.add_field(name="伺服器名稱", value=invite.guild.name)

        if guild:
            invite = next((i for i in await guild.invites() if i.code == invite.code), invite)
            embed.add_field(name="伺服器人數", value=invite.guild.member_count)
            embed.add_field(name="邀請人", value=invite.inviter.mention)
            embed.add_field(name="邀請頻道", value=invite.channel.name)
            embed.add_field(name="邀請次數", value=f"{invite.uses}/{invite.max_uses if invite.max_uses else '無限制'}")
            embed.add_field(name="臨時成員", value=invite.temporary)
            created_str = format_dt(invite.created_at, style="T") if invite.created_at else "未知"
            embed.add_field(name="創建於", value=created_str)
        else:
            embed.add_field(name="伺服器人數", value=invite.approximate_member_count)
            embed.add_field(name="邀請人", value=invite.inviter.mention)
            embed.add_field(name="邀請頻道", value=invite.channel.name)
            embed.add_field(name="邀請次數", value=f"未知/{invite.max_uses if invite.max_uses else '無限制'}")
            embed.add_field(name="臨時成員", value="未知")
            embed.add_field(name="創建於", value="未知")
            embed.set_footer(text="邀請機器人加入獲取完整資訊")

        expires_str = format_dt(invite.expires_at, style="T") if invite.expires_at else "無"
        embed.add_field(name="過期於", value=expires_str)
        embed.add_field(name="伺服器邀請連結", value=invite.url, inline=False)
        if invite.guild.icon:
            embed.set_thumbnail(url=invite.guild.icon.url)
        await ctx.respond(embed=embed)

    @commands.slash_command(description="TRPG故事")
    async def trpgstory(self, ctx, plot_id: discord.Option(int, name="故事id", description="故事id", autocomplete=trpg_plot_autocomplete)):
        plot = sclient.sqldb.get_trpg_plot(plot_id)
        view = TRPGPlotView(plot, sclient.sqldb)
        await ctx.respond(embed=view.embed(), view=view)

    @giveaway.command(description="創建抽獎")
    async def create(
        self,
        ctx: discord.ApplicationContext,
        prize_name: discord.Option(str, name="獎品", description="抽獎獎品"),
        winner_count: discord.Option(int, name="中獎人數", description="預設為1", default=1, min_value=1, max_value=100),
        end_time: discord.Option(str, name="結束時間", description="格式為YYYY-MM-DD hh:mm:ss", required=False),
        description: discord.Option(str, name="描述", description="關於抽獎的描述", required=False, default=None),
    ):
        await ctx.defer()
        now = datetime.now(tz)
        if end_time:
            end_at = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S").astimezone(tz)
            if end_at < now:
                await ctx.respond("錯誤：結束時間必須大於現在時間")
                return
        else:
            end_at = None

        giveaway = Giveaway(
            guild_id=ctx.guild.id,
            channel_id=ctx.channel.id,
            prize_name=prize_name,
            winner_count=winner_count,
            created_at=datetime.now(tz),
            creator_id=ctx.author.id,
            end_at=end_at,
            description=description,
        )
        sclient.sqldb.add(giveaway)

        view = GiveawayView(giveaway, sclient.sqldb, self.bot, timeout=int((end_at - now).total_seconds()) if end_at else None)
        message = await ctx.respond(embed=view.embed(), view=view)
        view.giveaway.message_id = message.id
        sclient.sqldb.merge(view.giveaway)

    @giveaway.command(description="重新抽出中獎者，未指定中獎者為全部重抽，不會保留原本的中獎者")
    async def redraw(
        self,
        ctx,
        giveaway_id: discord.Option(int, name="抽獎id", description="抽獎id"),
        winner: discord.Option(discord.Member, name="中獎者", description="此中獎者的中獎資格將被取消並另行抽出替補者", required=False),
    ):
        await ctx.defer()
        giveaway = sclient.sqldb.get_giveaway(giveaway_id)
        if not giveaway:
            await ctx.respond("錯誤：查無此ID")
            return
        elif giveaway.is_on:
            await ctx.respond("錯誤：此抽獎尚未結束")
            return
        elif giveaway.creator_id != ctx.author.id and not self.bot.is_owner(ctx.author):
            await ctx.respond("錯誤：你不是此抽獎的發起人")
            return

        if winner:
            old_winner = sclient.sqldb.get_user_in_giveaway(giveaway_id, winner.id)
            if not old_winner:
                await ctx.respond("錯誤：用戶沒有參加此抽獎")
                return
            elif not old_winner.is_winner:
                await ctx.respond("錯誤：此用戶不是中獎者")
                return
        else:
            old_winner = None

        view = GiveawayView(giveaway, sclient.sqldb, self.bot)
        embed = view.redraw_winner_giveaway(old_winner)
        await ctx.respond(embed=embed)

    @date_cmd.command(name="add", description="新增紀念日")
    async def date_add(
        self,
        ctx: discord.ApplicationContext,
        date_str: discord.Option(str, name="日期", description="紀念日的日期，格式為YYYY-MM-DD"),
        name: discord.Option(str, name="名稱", description="紀念日的名稱"),
    ):
        target_date = date.fromisoformat(date_str)
        sclient.sqldb.add_date(ctx.author.id, target_date, name)
        await ctx.respond(f"新增紀念日：{target_date} - {name}")

def setup(bot):
    bot.add_cog(command(bot))
