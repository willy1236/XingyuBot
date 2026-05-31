import ipaddress
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
                    return {"interface": iface_name, "ip": ip, "netmask": netmask, "network": network}
    return None
