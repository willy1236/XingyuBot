import platform
import re
import socket
import subprocess

import psutil


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
    if platform.system() == "Windows":
        output = subprocess.check_output("arp -a", shell=True, text=True)
        pattern = r"((?:26\.\d+\.\d+\.\d+|10\.242\.\d+\.\d+))\s+([\da-f\-]{17})"
    else:
        # Ubuntu/Debian 預設不裝 net-tools，arp 指令可能不存在，改用 iproute2 的 ip neigh
        output = subprocess.check_output("ip neigh show", shell=True, text=True)
        pattern = r"((?:26\.\d+\.\d+\.\d+|10\.242\.\d+\.\d+))\s+dev\s+\S+\s+lladdr\s+([\da-f:]{17})"

    radmin_ips = []
    for line in output.splitlines():
        match = re.search(pattern, line, re.IGNORECASE)
        if match:
            ip = match.group(1)
            mac = match.group(2)
            if ip not in EXCLUDED_IPS:
                radmin_ips.append((ip, mac))

    return radmin_ips


def find_radmin_vpn_network():
    # Windows 上 Radmin VPN 的介面名稱固定包含 "Radmin VPN"，
    # 但 Linux（Ubuntu）上介面名稱不受此限（可能是 radmin0、tun0 等），
    # 因此改以 Radmin VPN 固定使用的 26.0.0.0/8 網段判斷，兩個平台皆適用。
    interfaces = psutil.net_if_addrs()
    for iface_name, addrs in interfaces.items():
        for addr in addrs:
            if addr.family.name == "AF_INET":  # IPv4
                ip = addr.address
                if "Radmin VPN" in iface_name or ip.startswith("26."):
                    return ip
    return None
