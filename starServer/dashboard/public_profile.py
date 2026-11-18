"""公開頁與公開設定（T-11）。

GET/PUT /dashboard/personal/public       本人的公開設定 {enabled, sections}，PUT 需要析域帳號
GET     /dashboard/public/{username}     公開頁內容，不需要登入

公開頁每次請求都即時查 auth server 與資料庫，不快取：未開啟、查無代號、已停權一律 404 not_found，
auth server 沒給出明確答案回 503 directory_unavailable。回應只含勾選的區塊；
沒勾 discord_names 時不回 Discord ID 與名稱，各 Discord 以「帳號一」「帳號二」區分（依 Discord ID 由小到大）。
"""

import asyncio
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from starlib import sqldb
from starlib.database import PUBLIC_PROFILE_SECTIONS
from starlib.identity import DirectoryUnavailable
from starlib.identity.resolver import get_directory

from .auth import avatar_url
from .db import run_db
from .discord_users import fetch_discord_user
from .errors import DashboardError
from .personal import PersonalScope, _assets, require_personal

router = APIRouter(prefix="/dashboard")

_MAX_USERNAME_LENGTH = 64
_NUMERALS = "一二三四五六七八九十"
Section = Literal["points", "pets", "voice", "participation", "playlists", "discord_names"]


def _label(index: int) -> str:
    return f"帳號{_NUMERALS[index] if index < len(_NUMERALS) else index + 1}"


def _canonical(sections: list[str]) -> list[str]:
    """去重並依固定順序排列。"""
    return [s for s in PUBLIC_PROFILE_SECTIONS if s in sections]


# ====== 公開設定 ======
class PublicSettings(BaseModel):
    enabled: bool
    sections: list[Section]


def _settings_json(scope: PersonalScope, enabled: bool, sections: list[str]) -> dict:
    return {
        "available": True,
        "enabled": enabled,
        "sections": _canonical(sections),
        "username": scope.account_username,
    }


@router.get("/personal/public")
async def get_public_settings(scope: PersonalScope = Depends(require_personal())):
    if scope.account_id is None:
        return {"available": False}
    profile = await run_db(lambda: sqldb.get_public_profile(scope.account_id))
    if profile is None:
        return _settings_json(scope, False, [])
    return _settings_json(scope, profile.enabled, list(profile.sections))


@router.put("/personal/public")
async def put_public_settings(body: PublicSettings, scope: PersonalScope = Depends(require_personal(write=True))):
    sections = _canonical(body.sections)
    profile = await run_db(lambda: sqldb.save_public_profile(scope.account_id, body.enabled, sections))
    return _settings_json(scope, profile.enabled, list(profile.sections))


# ====== 公開頁 ======
def _discord_data(discord_ids: list[int], sections: set[str]) -> list[dict]:
    """各 Discord 勾選的資料（同步，在 DB thread 執行）；不含名稱。"""
    assets = _assets(discord_ids) if sections & {"points", "pets"} else None
    result = []
    for index, discord_id in enumerate(discord_ids):
        item: dict = {"label": _label(index)}
        if assets is not None:
            points, pet = assets[index]
            if "points" in sections:
                item["points"] = points
            if "pets" in sections:
                item["pet"] = None if pet is None else {"name": pet["name"], "species": pet["species"]}
        if "voice" in sections:
            item["voice_minutes"] = sqldb.get_voice_total_minutes(discord_id)
        if "participation" in sections:
            item["participation"] = sqldb.count_user_participation(discord_id)
        result.append(item)
    return result


def _playlists_data(user_id) -> list[dict]:
    return [
        {"name": p.name, "songs": [{"title": s.title, "url": s.url} for s in sqldb.get_music_playlist_songs(p.id)]}
        for p in sqldb.get_music_playlists(user_id)
    ]


@router.get("/public/{username}")
async def public_profile(username: str):
    if not username or len(username) > _MAX_USERNAME_LENGTH:
        raise DashboardError(404, "not_found")
    try:
        account = await get_directory().find_by_username(username)
    except DirectoryUnavailable as e:
        raise DashboardError(503, "directory_unavailable") from e
    if account is None or account.suspended or account.username is None:
        raise DashboardError(404, "not_found")
    profile = await run_db(lambda: sqldb.get_public_profile(account.account_id))
    if profile is None or not profile.enabled:
        raise DashboardError(404, "not_found")

    sections = set(profile.sections) & set(PUBLIC_PROFILE_SECTIONS)
    discord_ids = list(account.discord_ids)
    per_discord = sections & {"points", "pets", "voice", "participation", "discord_names"}

    discords: list[dict] = []
    if per_discord:
        discords = await run_db(lambda: _discord_data(discord_ids, sections))
        if "discord_names" in sections:
            profiles = await asyncio.gather(*(fetch_discord_user(i) for i in discord_ids))
            for item, discord_id, discord in zip(discords, discord_ids, profiles, strict=True):
                item["name"] = None if discord is None else discord.name
                item["avatar_url"] = None if discord is None else avatar_url(str(discord_id), discord.avatar)

    return {
        "username": account.username,
        "sections": _canonical(list(sections)),
        "discords": discords,
        "playlists": await run_db(lambda: _playlists_data(account.account_id)) if "playlists" in sections else None,
    }
