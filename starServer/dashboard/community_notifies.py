"""社群推播的新增、修改、刪除：
POST   /dashboard/guilds/{id}/community-notifies/resolve                          名稱或網址 → 平台帳號
POST   /dashboard/guilds/{id}/community-notifies                                  新增（Twitch 可一次多種）
PUT    /dashboard/guilds/{id}/community-notifies/{notify_type}/{account_id}       修改頻道、身分組、自訂文字
DELETE /dashboard/guilds/{id}/community-notifies/{notify_type}/{account_id}       刪除

設定邏輯在 starlib.notify_settings，與 Discord 指令共用。修改與刪除用條件式寫入，後到的一定被擋下並回 409 conflict；
新增有任一種類已存在回 409 already_exists 並列出全部已存在的種類，一筆都不寫入。
"""

import asyncio
import time

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from starlib import notify_settings, sqldb
from starlib.database import NotifyCommunityType, PlatformType
from starlib.exceptions import NotifyCommunityExistsError
from starlib.notify_settings import AccountInfo, LookupFailure

from .access import require_guild_access
from .conflict import Conflict
from .db import run_db
from .errors import DashboardError
from .notify_fields import NotifySpec, parse_key
from .notify_input import field_names, parse_fields, validate_fields

router = APIRouter(prefix="/dashboard")

PLATFORMS: dict[str, PlatformType] = {"twitch": PlatformType.Twitch, "youtube": PlatformType.Google, "twitter": PlatformType.Twitter}

#: resolve 的結果在伺服器記憶體保留的秒數，新增時不信任前端傳來的名稱
RESOLVE_TTL = 600
_resolved: dict[tuple[PlatformType, str], tuple[float, AccountInfo]] = {}


def _remember(account: AccountInfo) -> None:
    now = time.monotonic()
    for key in [k for k, (expire, _) in _resolved.items() if expire < now]:
        del _resolved[key]
    _resolved[(account.platform, account.id)] = (now + RESOLVE_TTL, account)


async def _in_executor(fn, *args):
    """網路查詢最長數十秒，放預設 executor，不佔 run_db 的小 executor。"""
    return await asyncio.get_running_loop().run_in_executor(None, fn, *args)


def _lookup_error(e: LookupFailure) -> DashboardError:
    return DashboardError(400, "resolve_failed", reason=e.reason)


async def _account(platform: PlatformType, account_id: str) -> AccountInfo:
    """resolve 過的帳號；快取過期時依 ID 重查平台。"""
    cached = _resolved.get((platform, account_id))
    if cached is not None and cached[0] >= time.monotonic():
        return cached[1]
    try:
        account = await _in_executor(notify_settings.fetch_account, platform, account_id)
    except LookupFailure as e:
        raise _lookup_error(e) from None
    _remember(account)
    return account


def _spec(notify_type: str) -> NotifySpec:
    try:
        spec = parse_key(notify_type)
    except KeyError:
        raise DashboardError(400, "invalid_request") from None
    if spec.kind != "community":
        raise DashboardError(400, "invalid_request")
    return spec


def _platform(name: str) -> PlatformType:
    try:
        return PLATFORMS[name]
    except KeyError:
        raise DashboardError(400, "invalid_request") from None


async def _ensure_youtube_push(account_id: str) -> notify_settings.PushResult:
    """YouTube 推播訂閱：DB 步驟走 run_db，最長約 70 秒的網路步驟走預設 executor。"""
    config = await run_db(lambda: notify_settings.youtube_push_config(account_id))
    if config is None:
        return "ok"
    result, times = await _in_executor(notify_settings.subscribe_youtube_push, account_id, config)
    if times is not None:
        await run_db(lambda: notify_settings.save_push_record(account_id, *times))
    return result


def _response(push: notify_settings.PushResult | None) -> dict:
    return {"ok": True, **({"push": push} if push is not None else {})}


def _conflict(spec: NotifySpec, account_id: str, guild_id: int) -> DashboardError:
    row = sqldb.get_notify_community_fresh(spec.community_type, account_id, guild_id)
    if row is None:
        return Conflict(None).to_error()
    return Conflict({name: None if (v := getattr(row, name)) is None else str(v) for name in field_names(spec)}).to_error()


class ResolveBody(BaseModel):
    platform: str
    input: str


@router.post("/guilds/{guild_id}/community-notifies/resolve")
async def resolve(body: ResolveBody, guild_id: int = Depends(require_guild_access)):
    platform = _platform(body.platform)
    try:
        account = await _in_executor(notify_settings.resolve_account, platform, body.input)
    except LookupFailure as e:
        raise _lookup_error(e) from None
    _remember(account)
    return {"platform": body.platform, "account_id": account.id, "display_name": account.display_name, "username": account.username}


class CreateBody(BaseModel):
    platform: str
    account_id: str
    #: 字串種類鍵，例如 community:1；Twitch 可勾多種
    notify_types: list[str]
    values: dict[str, str | None]


@router.post("/guilds/{guild_id}/community-notifies")
async def create(body: CreateBody, guild_id: int = Depends(require_guild_access)):
    platform = _platform(body.platform)
    specs = [_spec(k) for k in dict.fromkeys(body.notify_types)]
    if not specs or any(s.platform != platform for s in specs) or not body.account_id:
        raise DashboardError(400, "invalid_request")
    # 同一次新增的種類共用同一組頻道、身分組、自訂文字；自訂文字只在全部種類都用得到時才寫
    values = parse_fields(specs[0], body.values, strict=False, blank_message_is_none=True)
    if not all(s.has_message for s in specs):
        values.pop("message", None)
    await validate_fields(guild_id, specs[0], values)
    account = await _account(platform, body.account_id)

    def _write() -> None:
        notify_settings.add_notifies(
            account,
            [s.community_type for s in specs],
            guild_id,
            values["channel_id"],  # pyright: ignore[reportArgumentType]
            values.get("role_id"),  # pyright: ignore[reportArgumentType]
            values.get("message"),  # pyright: ignore[reportArgumentType]
        )

    try:
        await run_db(_write)
    except NotifyCommunityExistsError as e:
        keys = [f"community:{int(t)}" for t in e.notify_types]
        raise DashboardError(409, "already_exists", existing=keys) from None
    push = await _ensure_youtube_push(account.id) if platform == PlatformType.Google else None
    return _response(push)


class PutBody(BaseModel):
    values: dict[str, str | None]
    original: dict[str, str | None]


class DeleteBody(BaseModel):
    original: dict[str, str | None]


@router.put("/guilds/{guild_id}/community-notifies/{notify_type}/{account_id}")
async def put_community_notify(notify_type: str, account_id: str, body: PutBody, guild_id: int = Depends(require_guild_access)):
    spec = _spec(notify_type)
    values = parse_fields(spec, body.values, strict=False, blank_message_is_none=True)
    original = parse_fields(spec, body.original, strict=True, blank_message_is_none=False)
    await validate_fields(guild_id, spec, values)

    def _write() -> None:
        if sqldb.update_notify_community_if(spec.community_type, account_id, guild_id, original, values) == 0:
            raise _conflict(spec, account_id, guild_id)

    await run_db(_write)
    push = await _ensure_youtube_push(account_id) if spec.community_type == NotifyCommunityType.Youtube else None
    return _response(push)


@router.delete("/guilds/{guild_id}/community-notifies/{notify_type}/{account_id}")
async def delete_community_notify(notify_type: str, account_id: str, body: DeleteBody, guild_id: int = Depends(require_guild_access)):
    spec = _spec(notify_type)
    original = parse_fields(spec, body.original, strict=True, blank_message_is_none=False)

    def _delete() -> None:
        if sqldb.delete_notify_community_if(spec.community_type, account_id, guild_id, original) == 0:
            raise _conflict(spec, account_id, guild_id)

    await run_db(_delete)
    return {"ok": True}
