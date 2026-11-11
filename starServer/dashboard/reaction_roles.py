"""反應身分組區塊：
GET /dashboard/guilds/{id}/reaction-roles   一覽：每則訊息的頻道、內容摘要、按鈕、失效標示與 bot 權限警告

權限一律經 `require_section(Section.REACTION_ROLES)`。紀錄以資料庫為準，Discord 只用來判斷失效與補名稱。
"""

from dataclasses import asdict, dataclass

import discord
from fastapi import APIRouter, Depends

from starlib import sqldb
from starlib.reaction_roles import bot_permission_issues, emoji_valid, role_issue

from .access import Section, on_guild_async, require_section
from .db import run_db

router = APIRouter(prefix="/dashboard")

SUMMARY_LENGTH = 100


@dataclass(frozen=True)
class _Button:
    role_id: int
    title: str
    emoji: str | None
    style: int | None
    position: int


@dataclass(frozen=True)
class _Message:
    channel_id: int
    message_id: int
    buttons: list[_Button]


def _load(guild_id: int) -> list[_Message]:
    return [
        _Message(
            m.channel_id,
            m.message_id,
            [_Button(o.role_id, o.title, o.emoji, o.style, o.position) for o in options],
        )
        for m, options in sqldb.list_guild_reaction_roles(guild_id)
    ]


def _summarize(message: discord.Message) -> str:
    text = message.content.strip()
    if not text and message.embeds:
        embed = message.embeds[0]
        text = (embed.title or embed.description or "").strip()
    return text if len(text) <= SUMMARY_LENGTH else text[:SUMMARY_LENGTH] + "…"


async def _fetch(channel, message_id: int) -> tuple[bool, str | None]:
    """(訊息是否已不存在, 內容摘要)。讀不到（缺權限等）不能判斷為失效，摘要回 None。"""
    try:
        message = await channel.fetch_message(message_id)
    except discord.NotFound:
        return True, None
    except (discord.Forbidden, discord.HTTPException):
        return False, None
    return False, _summarize(message)


def _channel_sort_key(channel) -> tuple[int, int, int]:
    if channel is None:
        return (1, 0, 0)
    category = getattr(channel, "category", None)
    return (0, category.position if category is not None else -1, channel.position)


def _button(guild: discord.Guild, b: _Button) -> dict:
    role = guild.get_role(b.role_id)
    return {
        "role": {"id": str(b.role_id), "name": role.name if role is not None else None, "invalid": role_issue(guild, role) is not None},
        "title": b.title,
        "emoji": b.emoji,
        "emoji_invalid": not emoji_valid(guild, b.emoji),
        "style": b.style,
    }


async def _read(guild: discord.Guild, messages: list[_Message]) -> list[dict]:
    items: list[tuple[tuple, dict]] = []
    for m in messages:
        channel = guild.get_channel(m.channel_id)
        message_gone, summary = (True, None) if channel is None else await _fetch(channel, m.message_id)
        item = {
            "message_id": str(m.message_id),
            "channel": {"id": str(m.channel_id), "name": channel.name if channel is not None else None, "invalid": channel is None},
            "invalid": message_gone,
            "summary": summary,
            "jump_url": f"https://discord.com/channels/{guild.id}/{m.channel_id}/{m.message_id}",
            "buttons": [_button(guild, b) for b in m.buttons],
            "permission_issues": [asdict(i) for i in bot_permission_issues(guild, channel)],
        }
        items.append(((*_channel_sort_key(channel), m.message_id), item))
    return [item for _, item in sorted(items, key=lambda x: x[0])]


@router.get("/guilds/{guild_id}/reaction-roles")
async def list_reaction_roles(guild_id: int = Depends(require_section(Section.REACTION_ROLES))):
    messages = await run_db(lambda: _load(guild_id))
    items = await on_guild_async(guild_id, lambda guild: _read(guild, messages))
    return {"messages": items}
