# pyright: reportArgumentType=true
import platform
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import discord
import mcrcon
import psutil
from discord.commands import SlashCommandGroup
from discord.ext import commands
from mcstatus import JavaServer

from starlib import BotEmbed, Jsondb, log, sclient
from starlib.database import NotifyChannelType
from starlib.instance import *
from starlib.settings import get_required_mc_server_env
from starlib.utils.utility import ChoiceList, base64_to_buffer, converter, find_radmin_vpn_network, get_arp_list

from ..checks import PrivilegeLevel, ensure_registered, has_privilege_level, has_vip, is_vip_admin
from ..command_options import *
from ..extension import Cog_Extension
from ..uiElement.view import McServerPanel, VIPAuditView, VIPView

if TYPE_CHECKING:
    from ..bot import DiscordBot


def server_status(ip, port):
    server = JavaServer.lookup(f"{ip}:{port}")
    status = server.status()
    latency = server.ping()
    embed = BotEmbed.general(f"{server.address.host}:{server.address.port}", title="伺服器已開啟", description=status.description.encode("iso-8859-1").decode("utf-8"))
    embed.add_field(name="伺服器版本", value=status.version.name, inline=True)
    embed.add_field(name="在線玩家數", value=f"{status.players.online}/{status.players.max}", inline=True)
    embed.add_field(name="延遲", value=f"{latency:.2f} ms", inline=True)
    return embed


class SendMessageModal(discord.ui.Modal):
    def __init__(self, channel, bot, is_dm, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_item(discord.ui.InputText(label="要傳送的訊息", style=discord.InputTextStyle.long))
        self.channel = channel
        self.is_dm = is_dm
        self.bot: DiscordBot = bot

    async def callback(self, interaction: discord.Interaction):
        message = await self.channel.send(self.children[0].value)
        await interaction.response.send_message(f"訊息發送成功", delete_after=5, ephemeral=True)
        if self.is_dm:
            await self.bot.dm(message)


class AnnoModal(discord.ui.Modal):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_item(discord.ui.InputText(label="要傳送的公告", style=discord.InputTextStyle.long))

    async def callback(self, interaction: discord.Interaction):
        msg = await interaction.response.send_message(f"訊息發送中..")
        embed = discord.Embed(description=self.children[0].value, color=0xC4E9FF, timestamp=datetime.now())
        embed.set_author(name="機器人全群公告", icon_url=Jsondb.get_picture("radio_001"))
        embed.set_footer(text="Bot Radio System")
        send_success = 0
        channels = sclient.sqldb.get_notify_channel_by_type(NotifyChannelType.AllAnnouncements)

        for i in channels:
            channel = interaction.client.get_channel(i.channel_id)
            if not channel:
                log.warning("anno: %s/%s", i.guild_id, i.channel_id)
                continue

            try:
                role = channel.guild.get_role(i.role_id) if i.role_id else None
                if role:
                    await channel.send(role.mention, embed=embed)
                else:
                    await channel.send(embed=embed)
                send_success += 1
            except Exception:
                log.error("anno: %s/%s", i.guild_id, i.channel_id, exc_info=True)

        await msg.edit_original_response(content=f"已向{send_success}/{len(channels)}個頻道發送公告")


class BotUpdateModal(discord.ui.Modal):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_item(discord.ui.InputText(label="要傳送的更新訊息", style=discord.InputTextStyle.long))

    async def callback(self, interaction: discord.Interaction):
        msg = await interaction.response.send_message(f"訊息發送中..")
        embed = discord.Embed(description=self.children[0].value, color=0xC4E9FF, timestamp=datetime.now())
        embed.set_author(name="機器人更新通知", icon_url=Jsondb.get_picture("radio_001"))
        embed.set_footer(text="Bot Radio System")
        send_success = 0
        channels = sclient.sqldb.get_notify_channel_by_type(NotifyChannelType.BotUpdates)

        for i in channels:
            channel = interaction.client.get_channel(i.channel_id)
            if not channel:
                log.warning("botupdate: %s/%s", i.guild_id, i.channel_id)
                continue

            try:
                role = channel.guild.get_role(i.role_id) if i.role_id else None
                if role:
                    await channel.send(role.mention, embed=embed)
                else:
                    await channel.send(embed=embed)
                send_success += 1
            except Exception:
                log.error("botupdate: %s/%s", i.guild_id, i.channel_id, exc_info=True)

        await msg.edit_original_response(content=f"已向{send_success}/{len(channels)}個頻道發送公告")


class BotPanel(discord.ui.View):
    def __init__(self, bot):
        super().__init__()
        self.bot: DiscordBot = bot

    @discord.ui.button(label="伺服器列表", row=1, style=discord.ButtonStyle.primary)
    async def button_callback1(self, button: discord.ui.Button, interaction: discord.Interaction):
        name_list = [f"{i.name}（{i.id}）: {i.member_count}" for i in self.bot.guilds]
        embed = BotEmbed.simple("伺服器列表", "\n".join(name_list))
        await interaction.response.send_message(content="", ephemeral=False, embed=embed)


class owner(Cog_Extension):
    twitch_chatbot = SlashCommandGroup("twitch_chatbot", "twitch機器人相關指令", guild_ids=debug_guilds)
    mcserver_cmd = SlashCommandGroup("mcserver", "Minecraft伺服器相關指令", guild_ids=mcserver_guilds, name_localizations=ChoiceList.name("mcserver"))
    permission_cmd = SlashCommandGroup("permission", "權限相關指令", guild_ids=debug_guilds)
    vip_cmd = SlashCommandGroup("vip", "VIP相關指令", guild_ids=happycamp_guild + debug_guilds)

    # load
    # @bot.command()
    @commands.slash_command(description="載入extension", guild_ids=debug_guilds)
    @commands.is_owner()
    async def load(self, ctx, extension):
        self.bot.load_extension(f"starDiscord.cmds.{extension}")
        await ctx.respond(f"Loaded {extension} done")

    # unload
    @commands.slash_command(description="關閉extension", guild_ids=debug_guilds)
    @commands.is_owner()
    async def unload(self, ctx, extension):
        self.bot.unload_extension(f"starDiscord.cmds.{extension}")
        await ctx.respond(f"Un - Loaded {extension} done")

    # reload
    @commands.slash_command(description="重載extension", guild_ids=debug_guilds)
    @commands.is_owner()
    async def reload(self, ctx, extension):
        self.bot.reload_extension(f"starDiscord.cmds.{extension}")
        await ctx.respond(f"Re - Loaded {extension} done")

    # ping
    @commands.slash_command(description="查詢延遲")
    async def ping(self, ctx):
        await ctx.respond(f"延遲為：{round(self.bot.latency * 1000)} ms")

    # change_presence
    @commands.slash_command(description="更換bot狀態", guild_ids=debug_guilds)
    @commands.is_owner()
    async def statue(self, ctx, statue):
        config = Jsondb.config
        config.write("activity", statue)
        activity_name = config.activity
        if activity_name is None:
            raise RuntimeError("Missing config key: activity")
        await self.bot.change_presence(activity=discord.CustomActivity(name=activity_name), status=discord.Status.online)
        await ctx.respond(f"狀態更改完成", delete_after=5)

    # shutdown
    @commands.slash_command(description="關閉機器人", guild_ids=debug_guilds)
    @commands.is_owner()
    async def shutdown(self, ctx):
        await ctx.respond(f"機器人關閉中")
        if sclient.twitch_bot_thread:
            sclient.twitch_bot_thread.stop()

        if sclient.website_thread:
            sclient.website_thread.stop()

        if sclient.tunnel_thread:
            sclient.tunnel_thread.stop()

        if sclient.twitchtunnel_thread:
            sclient.twitchtunnel_thread.stop()

        await self.bot.close()
        self.bot.loop.stop()
        exit()

    # send
    @commands.slash_command(description="發送訊息", guild_ids=debug_guilds)
    @commands.is_owner()
    async def sendmesssage(self, ctx: discord.ApplicationContext, id_str: discord.Option(str, required=True, name="頻道id", description="")):
        # modal = SendMessageModal(title="發送訊息")
        # await ctx.send_modal(modal)
        # msg = modal.children[0].value
        # await ctx.defer()
        id = int(id_str)
        channel = self.bot.get_channel(id)
        if channel:
            modal = SendMessageModal(title="發送訊息(頻道)", channel=channel, bot=self.bot, is_dm=False)
        else:
            user = self.bot.get_user(id)
            if user:
                modal = SendMessageModal(title="發送訊息(私訊)", channel=channel, bot=self.bot, is_dm=True)
            else:
                await ctx.respond(f"找不到此ID", ephemeral=True)
                return

        await ctx.send_modal(modal)
        await modal.wait()

    # all_anno
    @commands.slash_command(description="全群公告", guild_ids=debug_guilds)
    @commands.is_owner()
    async def anno(self, ctx: discord.ApplicationContext):
        modal = AnnoModal(title="全群公告")
        await ctx.send_modal(modal)
        await modal.wait()

    # bot_update
    @commands.slash_command(description="機器人更新通知", guild_ids=debug_guilds)
    @commands.is_owner()
    async def botupdate(self, ctx: discord.ApplicationContext):
        modal = BotUpdateModal(title="機器人更新")
        await ctx.send_modal(modal)
        await modal.wait()

    # edit
    @commands.slash_command(description="編輯訊息", guild_ids=debug_guilds)
    @commands.is_owner()
    async def editmessage(self, ctx: discord.ApplicationContext, msgid: str, new_msg: str):
        await ctx.defer()
        message = await ctx.fetch_message(int(msgid))
        await message.edit(content=new_msg)
        await ctx.respond(f"訊息修改成功", delete_after=5, ephemeral=True)

    @commands.is_owner()
    @permission_cmd.command(name="view", description="查看權限", guild_ids=debug_guilds)
    async def permission_view(self, ctx: discord.ApplicationContext, guild_id_str: str | None = None, channel_id_str: str | None = None):
        if guild_id_str:
            guild_id = int(guild_id_str)
            guild = self.bot.get_guild(guild_id)
            assert guild is not None
            member = guild.me
            permission = member.guild_permissions

            embed = discord.Embed(title=guild.name, color=0xC4E9FF)
            embed.add_field(name="管理員", value=str(permission.administrator), inline=True)
            embed.add_field(name="管理頻道", value=str(permission.manage_channels), inline=True)
            embed.add_field(name="管理公會", value=str(permission.manage_guild), inline=True)
            embed.add_field(name="管理訊息", value=str(permission.manage_messages), inline=True)
            embed.add_field(name="管理暱稱", value=str(permission.manage_nicknames), inline=True)
            embed.add_field(name="管理身分組", value=str(permission.manage_roles), inline=True)
            embed.add_field(name="管理webhook", value=str(permission.manage_webhooks), inline=True)
            embed.add_field(name="管理表情符號", value=str(permission.manage_emojis), inline=True)
            embed.add_field(name="管理討論串", value=str(permission.manage_threads), inline=True)
            embed.add_field(name="管理活動", value=str(permission.manage_events), inline=True)
            embed.add_field(name="踢出成員", value=str(permission.kick_members), inline=True)
            embed.add_field(name="封鎖成員", value=str(permission.ban_members), inline=True)
            embed.add_field(name="禁言成員", value=str(permission.moderate_members), inline=True)
            embed.add_field(name="觀看審核日誌", value=str(permission.view_audit_log), inline=True)

        if channel_id_str:
            channel_id = int(channel_id_str)
            channel = self.bot.get_channel(channel_id)
            assert isinstance(channel, discord.abc.GuildChannel)

            embed = discord.Embed(title=channel.name, color=0xC4E9FF)
            embed.add_field(name="頻道", value=str(channel.permissions_for(channel.guild.me).manage_channels), inline=True)
            if channel.category:
                embed.add_field(name="分類", value=str(channel.category.permissions_for(channel.guild.me).manage_channels), inline=True)
            embed.add_field(name="伺服器", value=str(channel.guild.me.guild_permissions.manage_channels), inline=True)
        await ctx.respond(embed=embed)

    @commands.is_owner()
    @permission_cmd.command(name="list", description="列出權限", guild_ids=debug_guilds)
    async def permission_list(self, ctx: discord.ApplicationContext, channel_str: str):
        channel = self.bot.get_channel(int(channel_str))
        if not channel:
            await ctx.respond("找不到頻道")
            return
        assert isinstance(channel, discord.abc.GuildChannel)

        embed = discord.Embed(title="當前權限", color=discord.Color.blurple())
        for target, overwrite in channel.overwrites.items():
            target_name = target.name if isinstance(target, discord.Role) else target.display_name
            texts = [f"{perm}: {'✅' if value else '❌'}" for perm, value in overwrite if value is not None]
            if texts:
                embed.add_field(name=target_name, value="\n".join(texts), inline=False)
        await ctx.respond(embed=embed)

    # @bot.event
    # async def on_message(message):
    #     if message.content.startswith('$thumb'):
    #         channel = message.channel
    #         await channel.send('Send me that 👍 reaction, mate')

    #         def check(reaction, user):
    #             return user == message.author and str(reaction.emoji) == '👍'

    #         try:
    #             reaction, user = await bot.wait_for('reaction_add', timeout=60.0, check=check)
    #         except asyncio.TimeoutError:
    #             await channel.send('👎')
    #         else:
    #             await channel.send('👍')

    @mcserver_cmd.command(description="使用rcon mc伺服器指令", guild_ids=debug_guilds)
    @commands.is_owner()
    async def rcon(self, ctx: discord.ApplicationContext, command: str):
        try:
            settings = get_required_mc_server_env()
        except RuntimeError as exc:
            await ctx.respond(str(exc), ephemeral=True)
            return

        host = str(settings["host"])
        port = int(settings["port"])
        password = str(settings["password"])

        with mcrcon.MCRcon(host, password, port) as rcon:
            response = rcon.command(command)
            await ctx.respond(response if response else "指令已發送")

    @mcserver_cmd.command(description="查詢mc伺服器")
    @commands.cooldown(rate=1, per=3)
    async def quary(self, ctx: discord.ApplicationContext, ip: discord.Option(str, description="伺服器ip", default=None)):
        await ctx.defer()
        if not ip:
            radmin_ip = find_radmin_vpn_network()
            if radmin_ip:
                ip = radmin_ip + ":25565"

        try:
            server = JavaServer.lookup(ip)
        except Exception as e:
            await ctx.respond(f"找不到伺服器：{ip}")
            return

        try:
            status = server.status()
        except Exception as e:
            await ctx.respond(f"無法獲取伺服器狀態")
            return

        try:
            latency = server.ping()
        except Exception as e:
            latency = None
        full_ip = f"{server.address.host}:{server.address.port}" if server.address.port != 25565 else server.address.host

        embed = BotEmbed.general(full_ip, title="伺服器狀態", description=status.description.encode("iso-8859-1").decode("utf-8"))
        embed.add_field(name="伺服器版本", value=status.version.name, inline=True)
        embed.add_field(name="在線玩家數", value=f"{status.players.online}/{status.players.max}", inline=True)
        if latency is not None:
            embed.add_field(name="延遲", value=f"{latency:.2f} ms", inline=True)

        file = discord.File(fp=base64_to_buffer(status.icon), filename="server_icon.png") if status.icon is not None else None
        try:
            await ctx.respond(embed=embed, file=file)
        except AttributeError:
            await ctx.respond(embed=embed)

    @mcserver_cmd.command(description="執行mc伺服器指令", guild_ids=debug_guilds)
    @commands.is_owner()
    async def cmd(self, ctx: discord.ApplicationContext, server_id=mcss_server_option, command=command_option):
        await ctx.defer()
        response = mcss_api.excute_command(server_id, command)
        await ctx.respond(response if response else "指令已發送")


    @mcserver_cmd.command(description="開啟mc伺服器面板", name="panel", name_localizations=ChoiceList.name("mcserver_panel"))
    @ensure_registered()
    @commands.check_any(commands.check(has_privilege_level(PrivilegeLevel.Level2)), commands.has_guild_permissions(manage_channels=True))  # pyright: ignore[reportArgumentType]
    async def mcserver_panel(self, ctx: discord.ApplicationContext):
        await ctx.defer()
        view = McServerPanel()
        await ctx.respond(view=view, ephemeral=True)

    @mcserver_cmd.command(description="列出現在開啟的mc伺服器", guild_ids=debug_guilds)
    async def list(self, ctx: discord.ApplicationContext):
        await ctx.defer()
        arp_lst = get_arp_list()
        text_lst = []
        for i in arp_lst:
            try:
                server = JavaServer(i[0], 25565)
                status = server.status()
                text_lst.append(f"伺服器：`{i[0]}`：版本：{status.version.name}，目前上線人數：{status.players.online}")
                text_lst.append(f"- {status.description.encode('iso-8859-1').decode('utf-8')}")
            except Exception as e:
                pass

        if text_lst:
            text = "\n".join(text_lst)
        else:
            text = "沒有找到任何開啟的伺服器"

        await ctx.respond(text)

    @commands.slash_command(description="機器人面板", guild_ids=debug_guilds)
    @commands.is_owner()
    async def panel(self, ctx: discord.ApplicationContext):
        embed_list = []
        embed = BotEmbed.bot(self.bot, description=f"伺服器總數：{len(self.bot.guilds)}\n成員：{len(self.bot.users)}")
        embed_list.append(embed)

        await ctx.respond(f"", embeds=embed_list, view=BotPanel(self.bot))

    @commands.slash_command(description="獲取指令", guild_ids=debug_guilds)
    @commands.is_owner()
    async def getcommand(self, ctx: discord.ApplicationContext, name: discord.Option(str, name="指令名稱")):
        data = self.bot.get_application_command(name)
        if data:
            await ctx.respond(embed=BotEmbed.simple(data.name, str(data.id)))
        else:
            await ctx.respond(embed=BotEmbed.simple("指令未找到"))

    @commands.slash_command(description="獲取指定伺服器與主伺服器的共通成員", guild_ids=debug_guilds)
    @commands.is_owner()
    async def findmember(self, ctx: discord.ApplicationContext, guildid: discord.Option(str, name="伺服器id")):
        guild = self.bot.get_guild(int(guildid))
        guild_main = self.bot.get_guild(happycamp_guild[0])
        assert isinstance(guild_main, discord.Guild)
        if not guild:
            await ctx.respond("伺服器未找到")
            return
        if guild == guild_main:
            await ctx.respond("伺服器重複")
            return

        common_member_display = [f"{member.mention} ({member.id})" for member in guild.members if member in guild_main.members]
        if common_member_display:
            embed = BotEmbed.simple(f"{guild.name} 的共通成員", "\n".join(common_member_display))
            await ctx.respond(embed=embed)
        else:
            await ctx.respond("沒有找到共通成員")

    @commands.slash_command(description="尋找id對象", guild_ids=debug_guilds + happycamp_guild)
    @commands.cooldown(rate=1, per=3)
    async def find(
        self,
        ctx: discord.ApplicationContext,
        id_str: str,
        guildid: discord.Option(str, name="guildid", required=False),
        channelid: discord.Option(str, name="channelid", required=False),
    ):
        success = 0
        id = int(id_str)
        now_guild: discord.Guild = ctx.guild
        channel_arg = self.bot.get_channel(int(channelid)) if channelid else None

        if channel_arg:
            message = await channel_arg.fetch_message(id)
            assert isinstance(message, discord.Message)
            if message:
                embeds = [BotEmbed.simple(title=f"訊息", description=f"ID：訊息")]
                embeds[0].add_field(name="內容", value=message.content, inline=False)
                embeds[0].add_field(name="發送者", value=message.author.mention, inline=True)
                embeds[0].add_field(name="頻道", value=channel_arg.mention, inline=True)
                embeds[0].add_field(name="發送時間", value=message.created_at.isoformat(sep=" ", timespec="seconds"), inline=True)
                embeds[0].set_footer(text=f"{message.id}")
                if message.embeds:
                    embeds += message.embeds
                await ctx.respond(embeds=embeds)
                return

        user = await self.bot.get_or_fetch_user(id)
        member = now_guild.get_member(id)
        if member:
            embed = BotEmbed.simple(title=f"{member.name}#{member.discriminator}", description="ID：用戶（伺服器成員）")
            embed.add_field(name="暱稱", value=str(member.nick), inline=False)
            embed.add_field(name="最高身分組", value=member.top_role.mention, inline=True)
            embed.add_field(name="目前狀態", value=str(member.raw_status), inline=True)
            if member.activity:
                embed.add_field(name="目前活動", value=str(member.activity.name), inline=True)
            embed.add_field(name="是否為機器人", value=str(member.bot), inline=False)
            embed.add_field(name="是否為Discord官方", value=str(member.system), inline=True)
            embed.add_field(name="是否被禁言", value=str(member.timed_out), inline=True)
            embed.add_field(name="加入群組日期", value=member.joined_at.isoformat(sep=" ", timespec="seconds") if member.joined_at else "未知", inline=False)
            embed.add_field(name="帳號創建日期", value=member.created_at.isoformat(sep=" ", timespec="seconds"), inline=False)
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"id:{member.id}")
            success += 1
        elif user:
            embed = BotEmbed.simple(title=f"{user.name}#{user.discriminator}", description="ID：用戶")
            embed.add_field(name="是否為機器人", value=str(user.bot), inline=False)
            embed.add_field(name="是否為Discord官方", value=str(user.system), inline=False)
            embed.add_field(name="帳號創建日期", value=user.created_at.isoformat(sep=" ", timespec="seconds"), inline=False)
            embed.set_thumbnail(url=user.display_avatar.url)
            success += 1

        channel = self.bot.get_channel(id)
        if channel:
            embed = BotEmbed.simple(title=channel.name, description="ID：頻道")
            embed.add_field(name="所屬類別", value=str(channel.category), inline=False)
            embed.add_field(name="所屬公會", value=str(channel.guild), inline=False)
            embed.add_field(name="創建時間", value=channel.created_at.isoformat(sep=" ", timespec="seconds") if channel.created_at else "未知", inline=False)
            success += 1

        guild = self.bot.get_guild(id)
        if guild:
            embed = BotEmbed.simple(title=guild.name, description="ID：伺服器")
            embed.add_field(name="伺服器擁有者", value=str(guild.owner), inline=False)
            embed.add_field(name="創建時間", value=guild.created_at.isoformat(sep=" ", timespec="seconds"), inline=False)
            embed.add_field(name="驗證等級", value=str(guild.verification_level), inline=False)
            embed.add_field(name="成員數", value=str(guild.member_count), inline=False)
            embed.add_field(name="文字頻道數", value=str(len(guild.text_channels)), inline=False)
            embed.add_field(name="語音頻道數", value=str(len(guild.voice_channels)), inline=False)
            embed.set_footer(text="頻道數可能因權限不足而有少算，敬請特別注意")
            if guild.icon:
                embed.set_thumbnail(url=guild.icon.url)
            success += 1

        if guildid:
            guildid = int(guildid)
            guild = self.bot.get_guild(guildid)
            assert guild is not None, "Guild not found"
            role = guild.get_role(id)
            if role:
                embed = BotEmbed.simple(title=role.name, description="ID：身分組")
                embed.add_field(name="所屬伺服器", value=str(role.guild), inline=False)
                embed.add_field(name="創建時間", value=role.created_at.isoformat(sep=" ", timespec="seconds"), inline=False)
                embed.add_field(name="所屬層級位置", value=str(role.position), inline=False)
                embed.add_field(name="顏色", value=str(role.color), inline=False)
                embed.add_field(name="權限值", value=str(role.permissions.value), inline=False)
                if role.icon:
                    embed.set_thumbnail(url=role.icon.url)
                success += 1

        if success == 1:
            await ctx.respond(embed=embed)
        elif success > 1:
            await ctx.respond(f"find:id重複(出現{success}次)")
        else:
            await ctx.respond("無法辨認此ID")

    @commands.slash_command(description="以機器人禁言用戶", guild_ids=debug_guilds)
    @commands.bot_has_permissions(moderate_members=True)
    @commands.is_owner()
    async def timeout_bot(
        self,
        ctx: discord.ApplicationContext,
        channelid: discord.Option(str, name="頻道", description="要發送警告單的頻道", required=True),
        userid: discord.Option(str, name="用戶", description="要禁言的用戶", required=True),
        time_last: discord.Option(str, name="時長", description="格式為30s、1h20m等，支援天(d)、小時(h)、分鐘(m)、秒(s)", required=True),
        reason: discord.Option(str, name="原因", description="限100字內", required=False),
    ):
        await ctx.defer()
        time = converter.time_to_datetime(time_last)
        channel = self.bot.get_channel(int(channelid))
        if not time or time > timedelta(days=7):
            await ctx.respond(f"錯誤：時間格式錯誤（不得超過7天）")
            return
        assert isinstance(channel, discord.abc.GuildChannel), "頻道必須是伺服器頻道"

        user = channel.guild.get_member(int(userid))
        if not user:
            await ctx.respond(f"錯誤：找不到該用戶")
            return
        await user.timeout_for(time, reason=reason)

        moderate_user = channel.guild.me
        create_time = datetime.now()

        timestamp = int((create_time + time).timestamp())
        embed = BotEmbed.general(f"{user.name} 已被禁言", user.display_avatar.url, description=f"{user.mention}：{reason}")
        embed.add_field(name="執行人員", value=moderate_user.mention)
        embed.add_field(name="結束時間", value=f"<t:{timestamp}>（{time_last}）")
        embed.timestamp = create_time
        msg = await channel.send(embed=embed)
        await ctx.respond(msg.jump_url)

    @commands.slash_command(description="取得伺服器資訊", guild_ids=debug_guilds)
    @commands.is_owner()
    async def serverinfo(self, ctx: discord.ApplicationContext):
        await ctx.defer()
        # 取得 CPU 使用率
        cpu_percent = psutil.cpu_percent(interval=1)
        # 取得記憶體資訊
        memory_info = psutil.virtual_memory()
        # 取得磁碟使用情況
        disk_usage = psutil.disk_usage("/")
        # 取得網路使用情況
        net_io = psutil.net_io_counters()
        # 取得系統啟動時間
        boot_time = psutil.boot_time()
        boot_time_str = datetime.fromtimestamp(boot_time).strftime("%Y-%m-%d %H:%M:%S")
        # 取得感測器溫度資訊（如果系統支援）
        temperatures = psutil.sensors_temperatures() if hasattr(psutil, "sensors_temperatures") else {}

        # 取得硬體和系統資訊
        system_name = platform.system()
        node_name = platform.node()
        # release = platform.release()
        version = platform.version()
        machine = platform.machine()
        processor = platform.processor()

        python_version = platform.python_version()

        # 建立嵌入訊息
        embed = discord.Embed(title="伺服器資訊", color=discord.Color.blue())
        embed.add_field(name="系統版本", value=f"{system_name} {version}", inline=False)
        embed.add_field(name="節點名稱", value=node_name, inline=False)
        embed.add_field(name="機器類型", value=machine, inline=False)
        embed.add_field(name="處理器", value=processor, inline=False)
        embed.add_field(name="Python 版本", value=python_version, inline=False)
        embed.add_field(name="記憶體使用", value=f"{memory_info.percent}%")
        embed.add_field(name="總記憶體", value=f"{memory_info.total / (1024**3):.2f} GB")
        embed.add_field(name="可用記憶體", value=f"{memory_info.available / (1024**3):.2f} GB")
        embed.add_field(name="磁碟使用", value=f"{disk_usage.percent}%")
        embed.add_field(name="總磁碟空間", value=f"{disk_usage.total / (1024**3):.2f} GB")
        embed.add_field(name="可用磁碟空間", value=f"{disk_usage.free / (1024**3):.2f} GB")
        embed.add_field(name="CPU 使用率", value=f"{cpu_percent}%")
        embed.add_field(name="已發送資料", value=f"{net_io.bytes_sent / (1024**3):.2f} GB")
        embed.add_field(name="已接收資料", value=f"{net_io.bytes_recv / (1024**3):.2f} GB")
        embed.add_field(name="系統啟動時間", value=boot_time_str, inline=False)

        # 添加感測器溫度資訊
        if temperatures:
            for name, entries in temperatures.items():
                for entry in entries:
                    embed.add_field(name=f"{name} 溫度 ({entry.label})", value=f"{entry.current}°C", inline=False)

        # 回應嵌入訊息
        await ctx.respond(embed=embed)

    @commands.slash_command(description="重置ai的對話紀錄", guild_ids=debug_guilds)
    @commands.is_owner()
    async def resetaichat(self, ctx: discord.ApplicationContext):
        await ctx.defer()
        sclient.starai.init_history()
        await ctx.respond("已重置ai的對話紀錄")

    @commands.slash_command(description="獲取資料庫緩存", guild_ids=debug_guilds)
    @commands.is_owner()
    async def cache(self, ctx: discord.ApplicationContext):
        await ctx.defer()
        await ctx.respond(f"{sclient.sqldb.cache}")

    @vip_cmd.command(name="panel", description="開啟專用面板")
    @has_vip()
    async def vip_panel(self, ctx: discord.ApplicationContext):
        await ctx.respond("已開啟專用面板", view=VIPView(), ephemeral=True)

    @vip_cmd.command(name="review", description="審核申請")
    @is_vip_admin()
    async def vip_review(self, ctx: discord.ApplicationContext, form_id: discord.Option(str, name="申請表單id", required=True)):
        await ctx.defer()
        form = sclient.sqldb.get_form(form_id)
        if form:
            await ctx.respond("已開啟申請審核面板", view=VIPAuditView(form=form), embed=form.embed(), ephemeral=True)
        else:
            await ctx.respond("找不到此申請表單", ephemeral=True)


def setup(bot):
    bot.add_cog(owner(bot))
