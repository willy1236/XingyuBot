"""NetBird 綁定與節點查詢，供 /game netbird_setup、/game netbird 與網站個人區共用。

函式都是同步的（NetBirdAPI 與 sqldb 皆同步）；網站端要用 run_db 呼叫。網路失敗拋 APINetworkError。
"""

from dataclasses import dataclass
from uuid import UUID

from starlib.database import NetBirdBinding
from starlib.providers import NetBirdAPI
from starlib.utils import nowtz

from . import sqldb

DOWNLOAD_URL = "https://netbird.io/downloads"


@dataclass(frozen=True)
class NetBirdSetup:
    command: str
    #: 安裝腳本內容（.bat）
    bat: str


def create_setup(user_id: UUID) -> NetBirdSetup:
    """建立（或沿用）使用者的群組與一次性 setup key，寫入綁定。key 只存在於回傳值。"""
    group_name = f"user-{user_id}"
    api = NetBirdAPI()
    binding = sqldb.get_netbird_binding(user_id)
    group = None
    if binding:
        group = api.get_group(binding.group_id)
    if not group:
        group = api.find_group_by_name(group_name) or api.create_group(group_name)

    setup_key = api.create_setup_key(group_name, auto_groups=[group["id"]])
    sqldb.merge(NetBirdBinding(user_id=user_id, group_id=group["id"], group_name=group_name, last_setup_key_id=setup_key["id"], updated_at=nowtz()))

    command = f"netbird up --setup-key {setup_key['key']}"
    bat = f"@echo off\r\nwhere netbird >nul 2>nul\r\nif errorlevel 1 (\r\n    echo 尚未安裝NetBird，請先至 {DOWNLOAD_URL} 下載安裝\r\n    pause\r\n    exit /b 1\r\n)\r\n{command}\r\npause\r\n"
    return NetBirdSetup(command, bat)


def list_peers(user_id: UUID) -> list[dict] | None:
    """綁定群組內的節點；沒有綁定回 None，已綁定但沒有節點回空 list。"""
    binding = sqldb.get_netbird_binding(user_id)
    if not binding:
        return None
    return NetBirdAPI().get_peers_in_group(binding.group_id)
