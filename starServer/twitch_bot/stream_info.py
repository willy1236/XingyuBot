"""聊天室的 `!title`、`!game`、`!uptime`：查看實況資訊，mod 與實況主能修改標題與分類。

查看用 bot 自己的 Helix client；修改要實況主的 `channel:manage:broadcast`，用實況主 token 開臨時 client 打 `PATCH /channels`。
既有頻道沒有重新授權時 token 沒有這項權限，修改會回覆請實況主到後台重新授權，查看照常。
"""

import asyncio
import logging
from collections.abc import Callable

from twitchAPI.chat import ChatCommand
from twitchAPI.type import AuthScope

from starlib import twitch_speech_check, twitch_tokens
from starlib.database import APIType, sqldb
from starlib.twitch_audit import AuditActor, record_change
from starlib.twitch_tokens import TokenInvalid
from starServer.twitch_bot import commands, speech, state
from starServer.twitch_bot.helix import BotTwitch

log = logging.getLogger(__name__)

#: Helix `PATCH /channels` 的標題長度上限
TITLE_MAX = 140
#: 分類搜尋最多看幾筆（只用第一筆與完全相同的名稱）
CATEGORY_SEARCH_LIMIT = 20

_WHAT = "修改實況資訊"
_NEED_REAUTH = "無法修改：需要實況主到後台重新授權（啟用 bot）才能改標題與分類"
_FAILED = "修改失敗，請稍後再試"


async def title(cmd: ChatCommand) -> None:
    """`!title`：沒參數回覆目前標題；有參數且是實況主或 mod 就改標題。"""
    twitch_id = int(cmd.room.room_id)
    new = cmd.parameter.strip()
    if not new:
        info = await _current(twitch_id)
        await cmd.reply(f"目前標題：{info.title}" if info else "查詢標題失敗，請稍後再試")
        return
    token = await _authorize(cmd, twitch_id)
    if token is None:
        return
    if len(new) > TITLE_MAX:
        await cmd.reply(f"標題過長：最多 {TITLE_MAX} 字（目前 {len(new)} 字）")
        return
    before = await _current(twitch_id)
    if before is None or not await _patch(twitch_id, token, title=new):
        await cmd.reply(_FAILED)
        return
    await _record(cmd, twitch_id, "title", {"title": before.title}, {"title": new})
    # 回覆含觀眾輸入的標題，發言前先過頻道的 AutoMod；被擋或查不到就不帶標題
    message = f"標題已更新：{new}"
    if await speech.check(twitch_id, message) != "ok":
        message = "標題已更新"
    await cmd.reply(message)


async def game(cmd: ChatCommand) -> None:
    """`!game`：沒參數回覆目前分類；有參數且是實況主或 mod 就改分類（名稱完全相同優先，否則搜尋第一筆）。"""
    twitch_id = int(cmd.room.room_id)
    query = cmd.parameter.strip()
    if not query:
        info = await _current(twitch_id)
        await cmd.reply(f"目前分類：{info.game_name}" if info else "查詢分類失敗，請稍後再試")
        return
    token = await _authorize(cmd, twitch_id)
    if token is None:
        return
    try:
        found = [c async for c in state.twitch.search_categories(query, first=CATEGORY_SEARCH_LIMIT)]
    except Exception:
        log.warning("搜尋分類 %r 失敗", query, exc_info=True)
        await cmd.reply(_FAILED)
        return
    if not found:
        await cmd.reply(f"找不到分類：{query}")
        return
    chosen = next((c for c in found if c.name.casefold() == query.casefold()), found[0])
    before = await _current(twitch_id)
    if before is None or not await _patch(twitch_id, token, game_id=chosen.id):
        await cmd.reply(_FAILED)
        return
    await _record(
        cmd,
        twitch_id,
        "game",
        {"game": before.game_name, "game_id": before.game_id},
        {"game": chosen.name, "game_id": chosen.id},
    )
    await cmd.reply(f"分類已改成：{chosen.name}")


async def uptime(cmd: ChatCommand) -> None:
    """`!uptime`：開台中回覆已開台時長，沒開台回覆「未開台」。"""
    twitch_id = int(cmd.room.room_id)
    ctx = await speech.prepare("{uptime}", speech.SpeechContext(twitch_id, cmd.room.name))
    if ctx.stream is None:
        await cmd.reply(speech.NOT_LIVE)
    else:
        await cmd.reply(f"已開台 {speech.render('{uptime}', ctx)}")


async def _current(twitch_id: int):
    """頻道目前的標題與分類（每次向 Helix 查，不用 speech 的快取）；失敗回 None。"""
    try:
        [info, *_] = await state.twitch.get_channel_information(str(twitch_id))
    except Exception:
        log.warning("查詢 %s 的頻道資訊失敗", twitch_id, exc_info=True)
        return None
    return info


async def _authorize(cmd: ChatCommand, twitch_id: int) -> str | None:
    """修改前的檢查：實況主或 mod、頻道已啟用、token 有改標題的權限。通過回實況主 token，否則已回覆原因、回 None。"""
    if not await commands.may_manage(cmd, _WHAT, reply_viewer=True):
        return None
    if not await _db(_granted, twitch_id):
        await cmd.reply(_NEED_REAUTH)
        return None
    token = await twitch_tokens.broadcaster_token(twitch_id)
    if isinstance(token, TokenInvalid):
        await cmd.reply(_FAILED if token.reason == "unavailable" else _NEED_REAUTH)
        return None
    return token


def _granted(twitch_id: int) -> bool:
    client = sqldb.get_oauth_client(APIType.Twitch, twitch_tokens.BROADCASTER_CLIENT_SEQ)
    token = sqldb.get_oauth_token(str(twitch_id), client.credential_id)
    return twitch_tokens.has_stream_info_scope(token)


async def _patch(twitch_id: int, token: str, **fields: str) -> bool:
    """用實況主 token 修改標題或分類。client id 必須是發這個 token 的 OAuth client，否則 Helix 回 401。不 raise。"""
    client = None
    try:
        client_id = await asyncio.to_thread(twitch_speech_check.broadcaster_client_id_blocking)
        client = BotTwitch(client_id, authenticate_app=False)
        client.auto_refresh_auth = False  # 續期由 twitch_tokens 負責，這個 client 只用一次
        await client.set_user_authentication(token, [AuthScope.CHANNEL_MANAGE_BROADCAST], validate=False)
        ok = await client.modify_channel_information(str(twitch_id), **fields)
    except Exception:
        log.warning("修改 %s 的實況資訊失敗", twitch_id, exc_info=True)
        return False
    finally:
        if client is not None:
            await client.close()
    speech.forget_channel_info(twitch_id)
    return bool(ok)


async def _record(cmd: ChatCommand, twitch_id: int, key: str, before: dict, after: dict) -> None:
    actor = AuditActor("twitch", str(cmd.user.id), cmd.user.display_name or cmd.user.name)

    def write() -> None:
        record_change(twitch_id, actor, "chat", "stream_info", key, "update", before, after)
        sqldb.session.commit()

    try:
        await _db(write)
    except Exception:
        log.exception("%s 的實況資訊修改紀錄寫入失敗", twitch_id)


async def _db[T](func: Callable[..., T], *args) -> T:
    """DB 工作放到 worker thread，並在該 thread 釋放 session。"""

    def run() -> T:
        try:
            return func(*args)
        finally:
            sqldb.release_session()

    return await asyncio.to_thread(run)
