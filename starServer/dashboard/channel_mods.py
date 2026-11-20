"""頻道 mod 協作：這個人在哪些頻道是 mod，依據是 Twitch 上該頻道的 mod 名單。

候選頻道：state 是 enabled／disabled 或已停權（`banned_at` 不為 null），而且 `mod_collab_enabled` 為 true；
未啟用的不列。候選清單每次都查 DB、不快取，實況主關閉協作後下一次計算就不再列。

每個候選頻道的 mod 名單用實況主 token 打 Helix Get Moderators，結果存在 web process 記憶體 60 秒，所有 session 共用；
同一頻道同時到的查詢共用同一次。快取過期時同步等待（所有頻道並行，總時限 5 秒），不做背景更新。
查詢結果分三種：
- 拿到名單：更新快取。
- 無法確認（token missing／revoked，或 Helix 回 401／403）：清空名單，所有 mod 都擋下。
- 暫時無法回應（token unavailable、逾時、網路錯誤、429 與其他回應）：沿用上次名單；沒有上次名單就當作空的。
名單排除 bot 帳號與實況主本人。

token 讀取與續期會佔住 DB 連線等 Twitch 回應，走自己的 executor，不排在後台共用的 `run_db` 後面。
"""

import asyncio
import logging
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from time import monotonic

import httpx
from sqlmodel import col, or_, select

from starlib import sqldb, twitch_speech_check, twitch_tokens
from starlib.database import TwitchBotJoinChannel
from starlib.twitch_tokens import MODERATORS_URL, TokenInvalid

from .db import run_db
from .session import TwitchIdentity

log = logging.getLogger(__name__)

#: 名單的有效時間（秒）：拿掉或新增 mod、關閉後重新開啟協作，最遲這麼久生效
CACHE_TTL = 60.0
#: 一次計算等 Twitch 的總時限（秒），逾時的頻道視為暫時無法回應
QUERY_TIMEOUT = 5.0
REQUEST_TIMEOUT = 5.0
#: 每頁 100 筆，超過這個頁數視為暫時無法回應（不拿不完整的名單去擋人）
MAX_PAGES = 20


@dataclass(frozen=True, slots=True)
class Moderator:
    """擔任 mod 的 Twitch 帳號；name 取自 Helix 名單的顯示名稱。"""

    id: str
    name: str


@dataclass(frozen=True, slots=True)
class ModChannel:
    channel: TwitchIdentity
    moderator: Moderator


@dataclass(frozen=True, slots=True)
class _Entry:
    checked_at: float
    #: mod 的 Twitch user ID -> 顯示名稱
    mods: dict[str, str]


class _Unconfirmable:
    """實況主授權失效，無法確認誰是 mod。"""


class _Unavailable:
    """Twitch 暫時無法回應。"""


type _Result = dict[str, str] | _Unconfirmable | _Unavailable

_cache: dict[int, _Entry] = {}
_inflight: dict[int, asyncio.Task[_Entry]] = {}
_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="dashboard-mods")


async def _run_token_db[T](fn: Callable[[], T]) -> T:
    def run() -> T:
        try:
            return fn()
        finally:
            sqldb.release_session()

    return await asyncio.get_running_loop().run_in_executor(_executor, run)


# ====== 候選頻道 ======
def _candidates(only: int | None = None) -> list[TwitchBotJoinChannel]:
    stmt = select(TwitchBotJoinChannel).where(
        col(TwitchBotJoinChannel.mod_collab_enabled),
        or_(
            col(TwitchBotJoinChannel.state).in_(("enabled", "disabled")),
            col(TwitchBotJoinChannel.banned_at).is_not(None),
        ),
    )
    if only is not None:
        stmt = stmt.where(TwitchBotJoinChannel.twitch_id == only)
    return list(sqldb.session.exec(stmt).all())


def _identity(row: TwitchBotJoinChannel) -> TwitchIdentity:
    return TwitchIdentity(
        str(row.twitch_id), row.login or "", row.display_name or row.login or str(row.twitch_id), row.avatar_url
    )


# ====== Helix ======
async def _fetch(twitch_id: int) -> _Result:
    token = await _run_token_db(lambda: twitch_tokens.broadcaster_token_blocking(twitch_id))
    if isinstance(token, TokenInvalid):
        return _Unavailable() if token.reason == "unavailable" else _Unconfirmable()
    client_id = await _run_token_db(twitch_speech_check.broadcaster_client_id_blocking)
    headers = {"Authorization": f"Bearer {token}", "Client-Id": client_id}
    mods: dict[str, str] = {}
    cursor: str | None = None
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        for _ in range(MAX_PAGES):
            params: dict[str, str | int] = {"broadcaster_id": str(twitch_id), "first": 100}
            if cursor:
                params["after"] = cursor
            try:
                response = await client.get(MODERATORS_URL, params=params, headers=headers)
            except httpx.HTTPError as exc:
                log.warning("查詢頻道 %s 的 mod 名單失敗：%r", twitch_id, exc)
                return _Unavailable()
            if response.status_code in (401, 403):
                log.warning("頻道 %s 的實況主授權無法查詢 mod 名單：%s", twitch_id, response.status_code)
                return _Unconfirmable()
            if response.status_code != 200:
                log.warning("查詢頻道 %s 的 mod 名單失敗：%s %s", twitch_id, response.status_code, response.text)
                return _Unavailable()
            try:
                body = response.json()
                data = body["data"]
                for entry in data:
                    mods[str(entry["user_id"])] = str(entry.get("user_name") or entry.get("user_login") or "")
                pagination = body.get("pagination")
                cursor = pagination.get("cursor") if isinstance(pagination, dict) else None
            except ValueError, KeyError, TypeError, AttributeError:
                log.warning("頻道 %s 的 mod 名單回應格式不符：%s", twitch_id, response.text)
                return _Unavailable()
            if not cursor:
                return mods
    log.warning("頻道 %s 的 mod 名單超過 %s 頁", twitch_id, MAX_PAGES)
    return _Unavailable()


async def _refresh(twitch_id: int) -> _Entry:
    previous = _cache.get(twitch_id)
    try:
        result = await _fetch(twitch_id)
        bot_id = await _run_token_db(twitch_tokens.bot_user_id_blocking)
    except Exception:
        log.exception("查詢頻道 %s 的 mod 名單失敗", twitch_id)
        result, bot_id = _Unavailable(), None
    now = monotonic()
    if isinstance(result, _Unconfirmable):
        mods: dict[str, str] = {}
    elif isinstance(result, _Unavailable):
        mods = {} if previous is None else previous.mods
    else:
        mods = {k: v for k, v in result.items() if k not in (bot_id, str(twitch_id))}
    entry = _Entry(now, mods)
    if _inflight.get(twitch_id) is asyncio.current_task():
        _cache[twitch_id] = entry
    return entry


def _refresh_once(twitch_id: int) -> asyncio.Task[_Entry]:
    task = _inflight.get(twitch_id)
    if task is None:
        task = asyncio.ensure_future(_refresh(twitch_id))
        _inflight[twitch_id] = task
        task.add_done_callback(lambda t: _inflight.pop(twitch_id) if _inflight.get(twitch_id) is t else None)
    return task


async def _mod_lists(twitch_ids: Iterable[int]) -> dict[int, dict[str, str]]:
    """各頻道目前的 mod 名單；過期的並行重查，總時限內沒查完的沿用上次結果（沒有就是空的）。"""
    now = monotonic()
    result: dict[int, dict[str, str]] = {}
    pending: dict[int, asyncio.Task[_Entry]] = {}
    for twitch_id in twitch_ids:
        entry = _cache.get(twitch_id)
        if entry is not None and now - entry.checked_at < CACHE_TTL:
            result[twitch_id] = entry.mods
        else:
            pending[twitch_id] = _refresh_once(twitch_id)
    if pending:
        # asyncio.wait 逾時或請求被取消都不會取消查詢本身，其他請求共用的查詢照常跑完並寫回快取
        await asyncio.wait(pending.values(), timeout=QUERY_TIMEOUT)
        for twitch_id, task in pending.items():
            if task.done() and not task.cancelled():
                result[twitch_id] = task.result().mods
            else:
                previous = _cache.get(twitch_id)
                result[twitch_id] = {} if previous is None else previous.mods
    return result


def _pick(mods: dict[str, str], twitch_ids: Iterable[str]) -> Moderator | None:
    """多個連結帳號都是 mod 時，取 ID 依數值排序的第一個。"""
    for twitch_id in sorted(twitch_ids, key=int):
        if twitch_id in mods:
            return Moderator(twitch_id, mods[twitch_id])
    return None


# ====== 對外入口 ======
async def mod_channels(twitch_ids: Iterable[str]) -> list[ModChannel]:
    """這組 Twitch 帳號擔任 mod 的頻道，依頻道名稱排序；`twitch_ids` 自己的頻道不列。"""
    ids = tuple(twitch_ids)
    if not ids:
        return []
    rows = [row for row in await run_db(_candidates) if str(row.twitch_id) not in ids]
    lists = await _mod_lists(row.twitch_id for row in rows)
    found = []
    for row in rows:
        moderator = _pick(lists[row.twitch_id], ids)
        if moderator is not None:
            found.append(ModChannel(_identity(row), moderator))
    return sorted(found, key=lambda m: (m.channel.name.casefold(), m.channel.id))


async def mod_channel(twitch_id: int, twitch_ids: Iterable[str]) -> ModChannel | None:
    """只查單一頻道：這組 Twitch 帳號在這個頻道是 mod 時回傳，否則（含不是候選頻道）回 None。"""
    ids = tuple(twitch_ids)
    if not ids or str(twitch_id) in ids:
        return None
    rows = await run_db(lambda: _candidates(twitch_id))
    if not rows:
        return None
    moderator = _pick((await _mod_lists([twitch_id]))[twitch_id], ids)
    return None if moderator is None else ModChannel(_identity(rows[0]), moderator)
