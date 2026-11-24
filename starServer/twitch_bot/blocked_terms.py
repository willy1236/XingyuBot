"""Twitch Blocked Terms 的 RPC：以 bot 的 mod 身分讀寫頻道的禁字清單。"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any
from weakref import WeakValueDictionary

from starlib.messaging import rpc
from starServer.twitch_bot import channels, state
from starServer.twitch_bot.helix import TwitchStatusError

type Reply = dict[str, Any]

_locks: WeakValueDictionary[int, asyncio.Lock] = WeakValueDictionary()


async def _terms(twitch_id: int) -> list[dict[str, str]]:
    terms = state.twitch.get_blocked_terms(str(twitch_id), state.bot_user_id)
    return [{"id": term.id, "text": term.text} async for term in terms]


def register(loop: asyncio.AbstractEventLoop) -> None:
    """註冊 `blocked_terms.*` RPC，handler 在 `loop` 上執行。"""
    rpc.handle("blocked_terms.list", list_terms, loop)
    rpc.handle("blocked_terms.add", add, loop)
    rpc.handle("blocked_terms.remove", remove, loop)


async def _as_mod(twitch_id: int, call: Callable[[], Awaitable[Reply]]) -> Reply:
    """Twitch 回 403 是 bot 不是頻道 mod，回 `{error: "not_mod"}`；其他失敗照常拋錯。"""
    try:
        return await call()
    except TwitchStatusError as exc:
        if exc.status == 403:
            channels.mark_not_mod(twitch_id)
            return {"error": "not_mod"}
        raise


async def list_terms(payload: dict[str, Any]) -> Reply:
    """RPC `blocked_terms.list`：回 `{terms: [{id, text}]}`。"""
    twitch_id = int(payload["twitch_id"])

    async def call() -> Reply:
        return {"terms": await _terms(twitch_id)}

    return await _as_mod(twitch_id, call)


async def add(payload: dict[str, Any]) -> Reply:
    """RPC `blocked_terms.add`：回 `{term: {id, text}, changed}`。"""
    twitch_id = int(payload["twitch_id"])

    async def call() -> Reply:
        async with _locks.setdefault(twitch_id, asyncio.Lock()):
            terms = await _terms(twitch_id)
            text = payload["text"]
            for existing in terms:
                if existing["text"] == text:
                    return {"term": existing, "changed": False}
            try:
                term = await state.twitch.add_blocked_term(str(twitch_id), state.bot_user_id, text)
            except TwitchStatusError as exc:
                if exc.status == 400:
                    return {"error": "invalid_term"}
                raise
            return {"term": {"id": term.id, "text": term.text}, "changed": all(item["id"] != term.id for item in terms)}

    return await _as_mod(twitch_id, call)


async def remove(payload: dict[str, Any]) -> Reply:
    """RPC `blocked_terms.remove`：回 `{term: {id, text} | null}`。"""
    twitch_id = int(payload["twitch_id"])

    async def call() -> Reply:
        async with _locks.setdefault(twitch_id, asyncio.Lock()):
            term_id = payload["term_id"]
            found = next((term for term in await _terms(twitch_id) if term["id"] == term_id), None)
            if found is not None:
                await state.twitch.remove_blocked_term(str(twitch_id), state.bot_user_id, term_id)
            return {"term": found}

    return await _as_mod(twitch_id, call)
