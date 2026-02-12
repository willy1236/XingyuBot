import base64
import ipaddress
import re
import socket
import subprocess
from datetime import datetime, timedelta
from io import BytesIO

import discord
import psutil

from ..fileDatabase import Jsondb
from .functions import find


class BotEmbed:
    @staticmethod
    def bot(bot: discord.Bot, title: str | None = None, description: str | None = None, url: str | None = None):
        """機器人 格式"""
        assert bot.user is not None, "Bot user must be set before creating an embed."
        embed = discord.Embed(title=title, description=description, color=0xc4e9ff, url=url)
        embed.set_author(name=bot.user.name, icon_url=bot.user.display_avatar.url)
        return embed

    @staticmethod
    def user(user: discord.User, title: str | None = None, description: str | None = None, url: str | None = None):
        """使用者 格式"""
        embed = discord.Embed(title=title, description=description, color=0x00FFFF, url=url)
        embed.set_author(name=user.name, icon_url=user.display_avatar.url)
        return embed

    @staticmethod
    def simple(title: str | None = None, description: str | None = None, url: str | None = None):
        """簡易:不帶作者"""
        embed = discord.Embed(title=title, description=description, color=0xC4E9FF, url=url)
        return embed

    @staticmethod
    def general(
        name: str | None = None,
        icon_url: str | None = None,
        url: str | None = None,
        title: str | None = None,
        description: str | None = None,
        title_url: str | None = None,
    ):
        """普通:自訂作者"""
        embed = discord.Embed(title=title, description=description, color=0xc4e9ff, url=title_url)
        embed.set_author(name=name, icon_url=icon_url, url=url)
        return embed

    @staticmethod
    def deprecated():
        """棄用:展示棄用訊息"""
        embed = discord.Embed(title="此功能目前為棄用狀態", description="此功能目前不開放使用，請洽機器人管理員或支援伺服器", color=0xC4E9FF)
        return embed

    @staticmethod
    def rpg(title: str | None = None, description: str | None = None):
        """RPG系統 格式"""
        embed = discord.Embed(title=title, description=description, color=0xc4e9ff)
        embed.set_footer(text="RPG系統 | 開發時期所有東西皆有可能重置")
        return embed

    @staticmethod
    def brs():
        """Bot Radio System 格式"""
        embed = discord.Embed(color=0xc4e9ff)
        embed.set_author(name="Bot Radio System", icon_url=Jsondb.get_picture("radio_001"))
        return embed

    @staticmethod
    def lottery():
        """Lottery System格式"""
        embed = discord.Embed(color=0xc4e9ff)
        embed.set_author(name="Lottery System", icon_url=Jsondb.get_picture("lottery_001"))
        return embed

    @staticmethod
    def star_radio():
        """星系電台 格式"""
        embed = discord.Embed(color=0xC4E9FF)
        embed.set_author(name="Star Rd.", icon_url=Jsondb.get_picture("radio_001"))
        return embed

    @staticmethod
    def sts():
        """星光終端系統 格式"""
        embed = discord.Embed(color=0xc4e9ff)
        embed.set_author(name="「星光」終端系統", icon_url=Jsondb.get_picture("radio_001"))
        return embed

    @staticmethod
    def info(title: str | None = None, description: str | None = None, url: str | None = None):
        """一般資訊 格式"""
        embed = discord.Embed(title=title, description=description, color=0xC4E9FF, url=url)
        return embed

    @staticmethod
    def simple_warn_sheet(
        warn_user: discord.User | discord.Member,
        moderate_user: discord.abc.User | discord.Member | discord.ClientUser,
        create_at: datetime | None = None,
        last: timedelta = timedelta(seconds=15),
        reason: str = "未提供原因",
        title: str = "已被禁言",
    ):
        """簡易警告表格"""
        if create_at is None:
            create_at = datetime.now()
        timestamp = create_at + last
        embed = discord.Embed(description=f"{warn_user.mention}：{reason}", color=0xc4e9ff)
        embed.set_author(name=f"{warn_user.name} {title}",icon_url=warn_user.display_avatar.url)
        embed.add_field(name="執行人員",value=moderate_user.mention)
        embed.add_field(name="結束時間", value=f"{discord.utils.format_dt(timestamp, style='t')}（{last.total_seconds():0f}s）")
        embed.timestamp = create_at
        return embed

class ChoiceList():
    @staticmethod
    def set(option_name: str):
        return [
            discord.OptionChoice(name=name_loc.get("en-US", name_loc.get("zh-TW")), value=value, name_localizations=name_loc)
            for value, name_loc in Jsondb.options[option_name].items()
        ]

    @staticmethod
    def name(cmd_name: str):
        """name_localizations 格式化"""
        return Jsondb.cmd_names[cmd_name]


class converter():
    @staticmethod
    def time_to_sec(arg:str):
        """10s->1,0用str相加 s則轉換後用int相乘"""
        dict = {"s": 1, "m": 60, "h": 3600}
        n=0
        m = ""
        for i in arg:
            try:
                int(i)
                m+=i
            except ValueError:
                try:
                    m=int(m)
                    n=n+(m*dict[i])
                    m = ""
                except KeyError:
                    raise KeyError
        return n

    @staticmethod
    def time_to_datetime(arg: str):
        m = ""
        days = 0
        hours = 0
        minutes = 0
        seconds = 0
        for i in arg:
            try:
                int(i)
                m += i
            except ValueError:
                m = int(m)
                if i == "d":
                    days = m
                elif i == "h":
                    hours = m
                elif i == "m":
                    minutes = m
                elif i == "s":
                    seconds = m
                m = ""
        return timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)


async def create_only_role_list(text_input:str,ctx):
    """投票系統：建立限制投票身分組清單"""
    only_role_list = []
    for i in text_input.split(","):
        if i.endswith(" "):
            i = i[:-1]
        role = await find.role(ctx,i)
        if role:
            only_role_list.append(role.id)
    return only_role_list

async def create_role_magification_dict(text_input:str,ctx) -> dict[int, int]:
    """投票系統：建立身分組權重列表"""
    role_magnification_dict = {}
    text = text_input.split(",")
    for i in range(0,len(text),2):
        if text[i].endswith(" "):
            text[i] = text[i][:-1]
        role = await find.role(ctx, text[i])
        if role:
            role_magnification_dict[role.id] = int(text[i+1])
    return role_magnification_dict

def calculate_eletion_session(current_date:datetime) -> int:
    """選舉屆數計算器"""
    start_date = datetime(2023, 10, 11)
    return (current_date.year - start_date.year) * 12 + current_date.month - start_date.month + 1

def base64_to_buffer(base64_string: str) -> BytesIO:
    """
    將 Base64 字串轉換為 BufferedIO 物件

    Args:
        base64_string (str): Base64 編碼的字串

    Returns:
        BufferedIO: 包含解碼資料的 BufferedIO 物件

    Raises:
        ValueError: 當 Base64 解碼失敗時
    """
    try:
        # 移除可能的 Base64 前綴 (如 "data:image/png;base64,")
        if "," in base64_string:
            base64_string = base64_string.split(",")[1]

        # 解碼 Base64 字串
        binary_data = base64.b64decode(base64_string)

        # 創建 BytesIO 物件並返回
        buffer = BytesIO(binary_data)
        return buffer
    except Exception as e:
        raise ValueError(f"Base64 解碼失敗: {str(e)}")


def is_server_running_by_process():
    for process in psutil.process_iter(["pid", "name"]):
        if "java" in process.info["name"]:  # Minecraft伺服器通常是以Java運行
            return True
    return False

def is_server_running_by_connect(host="localhost", port=25565):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((host, port))
            return True
    except ConnectionRefusedError:
        return False


EXCLUDED_IPS = {"26.0.0.1", "26.255.255.255", "10.242.255.255"}


def get_arp_list() -> list[tuple[str, str]]:
    # print("[*] 讀取 ARP 快取...")
    output = subprocess.check_output("arp -a", shell=True, text=True)
    radmin_ips = []

    for line in output.splitlines():
        match = re.search(r"((?:26\.\d+\.\d+\.\d+|10\.242\.\d+\.\d+))\s+([\da-f\-]{17})", line, re.IGNORECASE)
        if match:
            ip = match.group(1)
            mac = match.group(2)
            if ip not in EXCLUDED_IPS:
                radmin_ips.append((ip, mac))

    return radmin_ips

def find_radmin_vpn_network():
    interfaces = psutil.net_if_addrs()
    for iface_name, addrs in interfaces.items():
        if "Radmin VPN" in iface_name:  # 名稱內含 Radmin VPN
            for addr in addrs:
                if addr.family.name == "AF_INET":  # IPv4
                    ip = addr.address
                    netmask = addr.netmask
                    network = ipaddress.IPv4Network(f"{ip}/{netmask}", strict=False)

                    return ip
                    return {
                        "interface": iface_name,
                        "ip": ip,
                        "netmask": netmask,
                        "network": network
                    }
    return None
