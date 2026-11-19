"""NetBird 綁定與節點查詢，供 /game netbird_setup、/game netbird 與網站個人區共用。

函式都是同步的（NetBirdAPI 與 sqldb 皆同步），網路失敗拋 APINetworkError。
指令端直接呼叫 create_setup、list_peers；網站端不能讓 NetBird 的 HTTP 佔著 DB 連線，
所以把每個流程拆成「DB 讀」「HTTP」「DB 寫」三段：DB 段放進 run_db，HTTP 段放在 executor 外（asyncio.to_thread）。
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


@dataclass(frozen=True)
class SetupPlan:
    """create_setup 的 DB 讀取結果：已建立的 API client（token 來自 DB）與要用的群組資訊。"""

    api: NetBirdAPI
    group_name: str
    bound_group_id: str | None


@dataclass(frozen=True)
class SetupKey:
    group_id: str
    group_name: str
    key_id: str
    key: str


@dataclass(frozen=True)
class PeerQuery:
    api: NetBirdAPI
    group_id: str


def plan_setup(user_id: UUID) -> SetupPlan:
    """DB 段：讀既有綁定與 API token。"""
    binding = sqldb.get_netbird_binding(user_id)
    return SetupPlan(NetBirdAPI(), f"user-{user_id}", binding.group_id if binding else None)


def request_setup_key(plan: SetupPlan) -> SetupKey:
    """HTTP 段：建立（或沿用）群組並建立一次性 setup key，不碰 DB。"""
    api = plan.api
    group = api.get_group(plan.bound_group_id) if plan.bound_group_id else None
    if not group:
        group = api.find_group_by_name(plan.group_name) or api.create_group(plan.group_name)
    setup_key = api.create_setup_key(plan.group_name, auto_groups=[group["id"]])
    return SetupKey(group["id"], plan.group_name, setup_key["id"], setup_key["key"])


def save_setup(user_id: UUID, key: SetupKey) -> NetBirdSetup:
    """DB 段：HTTP 全部成功後才寫入綁定，失敗不留下綁定。"""
    sqldb.merge(
        NetBirdBinding(
            user_id=user_id,
            group_id=key.group_id,
            group_name=key.group_name,
            last_setup_key_id=key.key_id,
            updated_at=nowtz(),
        )
    )
    command = f"netbird up --setup-key {key.key}"
    bat = f"@echo off\r\nwhere netbird >nul 2>nul\r\nif errorlevel 1 (\r\n    echo 尚未安裝NetBird，請先至 {DOWNLOAD_URL} 下載安裝\r\n    pause\r\n    exit /b 1\r\n)\r\n{command}\r\npause\r\n"
    return NetBirdSetup(command, bat)


def create_setup(user_id: UUID) -> NetBirdSetup:
    """建立（或沿用）使用者的群組與一次性 setup key，寫入綁定。key 只存在於回傳值。"""
    return save_setup(user_id, request_setup_key(plan_setup(user_id)))


def plan_peers(user_id: UUID) -> PeerQuery | None:
    """DB 段：讀綁定與 API token；沒有綁定回 None。"""
    binding = sqldb.get_netbird_binding(user_id)
    return PeerQuery(NetBirdAPI(), binding.group_id) if binding else None


def fetch_peers(query: PeerQuery) -> list[dict]:
    """HTTP 段：綁定群組內的節點，不碰 DB。"""
    return query.api.get_peers_in_group(query.group_id)


def list_peers(user_id: UUID) -> list[dict] | None:
    """綁定群組內的節點；沒有綁定回 None，已綁定但沒有節點回空 list。"""
    query = plan_peers(user_id)
    return None if query is None else fetch_peers(query)
