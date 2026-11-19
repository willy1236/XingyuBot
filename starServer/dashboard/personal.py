"""個人區：可見範圍的共用判斷（T-06～T-11 共用）與 GET /dashboard/personal/overview。

可見範圍只讀 session 帶的析域帳號（session.py 的帳號跟隨結果），不另外向 auth server 查詢：
有析域帳號時涵蓋該域民連結的所有 Discord，沒有時只有 session 的 Discord。
"""

import asyncio
from dataclasses import dataclass
from uuid import UUID

from fastapi import APIRouter, Depends

from starlib import sqldb
from starlib.fileDatabase import Jsondb
from starlib.identity import IdentityUnavailable, resolve_identity

from .auth import avatar_url
from .db import run_db
from .discord_users import fetch_discord_user
from .errors import DashboardError
from .session import DiscordSessionInfo, require_session

router = APIRouter(prefix="/dashboard")


@dataclass(frozen=True)
class PersonalScope:
    account_id: UUID | None
    account_username: str | None
    #: 個人區涵蓋的 Discord，依 Discord ID 由小到大
    discord_ids: list[int]
    #: 有析域帳號，但 auth server 暫時查不到連結了哪些 Discord，只涵蓋 session 的 Discord
    partial: bool
    #: 工具類資料（歌單、雲端資料夾共用、NetBird）讀寫用的 user_id；沒有紀錄或查不到時為 None
    tool_user_id: UUID | None
    #: 工具類資料可以寫入（有析域帳號）
    tools_writable: bool
    #: 查不到工具類資料的 user_id（身分服務暫時不可用）
    tool_unavailable: bool


async def personal_scope(info: DiscordSessionInfo) -> PersonalScope:
    own = int(info.discord_user_id)
    if info.account_id is not None:
        discord_ids = list(info.discord_ids) if info.discord_ids else [own]
        return PersonalScope(
            account_id=info.account_id,
            account_username=info.account_username,
            discord_ids=discord_ids,
            partial=info.stale and discord_ids == [own],
            tool_user_id=info.account_id,
            tools_writable=True,
            tool_unavailable=False,
        )

    # 沒有析域帳號：工具類資料唯讀，沿用 bot 已發的臨時 ID，不替沒用過 bot 的人發新的
    tool_user_id, tool_unavailable = None, False
    try:
        identity = await resolve_identity(own, create=False)
        tool_user_id = None if identity is None else identity.user_id
    except IdentityUnavailable:
        tool_unavailable = True
    return PersonalScope(
        account_id=None,
        account_username=None,
        discord_ids=[own],
        partial=False,
        tool_user_id=tool_user_id,
        tools_writable=False,
        tool_unavailable=tool_unavailable,
    )


def require_personal(write: bool = False):
    """個人區端點的 dependency：回傳可見範圍；write=True 時沒有析域帳號回 403 domalyze_required。"""

    async def dependency(info: DiscordSessionInfo = Depends(require_session)) -> PersonalScope:
        scope = await personal_scope(info)
        if write and not scope.tools_writable:
            raise DashboardError(403, "domalyze_required")
        return scope

    return dependency


# ====== GET /dashboard/personal/overview ======
def _assets(discord_ids: list[int]) -> list[tuple[dict, dict | None]]:
    """積分與寵物，欄位同 /user 與 /pet。"""
    result = []
    for discord_id in discord_ids:
        coin = sqldb.get_coin(discord_id)
        pet = sqldb.get_pet(discord_id)
        points = {"stardust": coin.stardust, "point": coin.point, "rcoin": coin.rcoin}
        pet_json = (
            None
            if pet is None
            else {"name": pet.pet_name, "species": Jsondb.get_tw(pet.pet_species, "pet_option"), "food": pet.food}
        )
        result.append((points, pet_json))
    return result


@router.get("/personal/overview")
async def personal_overview(
    info: DiscordSessionInfo = Depends(require_session), scope: PersonalScope = Depends(require_personal())
):
    profiles = await asyncio.gather(*(fetch_discord_user(i) for i in scope.discord_ids))
    assets = await run_db(lambda: _assets(scope.discord_ids))

    discords = []
    for discord_id, profile, (points, pet) in zip(scope.discord_ids, profiles, assets, strict=True):
        if profile is not None:
            name, avatar = profile.name, profile.avatar
        elif discord_id == int(info.discord_user_id):
            name, avatar = info.name, info.avatar
        else:
            name, avatar = str(discord_id), None
        discords.append(
            {
                "id": str(discord_id),
                "name": name,
                "avatar_url": avatar_url(str(discord_id), avatar),
                "current": discord_id == int(info.discord_user_id),
                "points": points,
                "pet": pet,
            }
        )
    return {
        "account": None if scope.account_id is None else {"username": scope.account_username},
        "partial": scope.partial,
        "discords": discords,
    }
