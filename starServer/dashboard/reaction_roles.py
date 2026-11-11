"""反應身分組區塊：
GET /dashboard/guilds/{id}/reaction-roles   一覽：每則訊息的頻道、內容摘要、按鈕、失效標示與 bot 權限警告
GET /dashboard/guilds/{id}/reaction-roles/options        編輯器用：頻道、身分組（含停用原因與危險權限）、自訂 emoji
GET /dashboard/guilds/{id}/reaction-roles/{message_id}   編輯用：內容、衝突比對的原值、按鈕
GET /dashboard/guilds/{id}/reaction-roles/candidates?channel_id=  掛到既有訊息：頻道最近 bot 發的訊息
GET /dashboard/guilds/{id}/reaction-roles/resolve?link=           掛到既有訊息：解析訊息連結
POST /dashboard/guilds/{id}/reaction-roles               發新訊息，或掛到 bot 既有的訊息（target.kind）
PUT /dashboard/guilds/{id}/reaction-roles/{message_id}   修改內容與按鈕，立即更新 Discord

權限一律經 `require_section(Section.REACTION_ROLES)`。紀錄以資料庫為準，Discord 只用來判斷失效與補名稱。
"""

import json
import logging
import re
from dataclasses import asdict, dataclass

import discord
from fastapi import APIRouter, Depends
from typing import Literal

from pydantic import BaseModel, ValidationError

from starDiscord.uiElement.view import ReactionRoleView
from starlib import sclient, sqldb
from starlib.database import ReactionRoleOption
from starlib.message_content import MessageContent, from_json, from_message, to_json, to_send_kwargs
from starlib.reaction_roles import (
    bot_permission_issues,
    dangerous_permissions,
    emoji_valid,
    operator_rank_issue,
    role_issue,
)

from .access import Section, on_guild, on_guild_async, require_section
from .conflict import Conflict, check_conflict
from .db import run_db
from .errors import DashboardError
from .message_input import ensure_valid_message
from .session import SessionInfo, require_session

log = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard")

SUMMARY_LENGTH = 100
MAX_BUTTONS = 25
MAX_TITLE = 80  # Discord 按鈕 label 上限
MAX_EMOJI = 64
BUTTON_STYLES = (1, 2, 3, 4)  # 主要、次要、成功、危險；5 是連結按鈕，不適用
#: content_locked 在沒有可讀的內容時的原因代碼（訊息或頻道讀不到）
REASON_MESSAGE_UNAVAILABLE = "message_unavailable"


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
    except discord.Forbidden, discord.HTTPException:
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
        "role": {
            "id": str(b.role_id),
            "name": role.name if role is not None else None,
            "invalid": role_issue(guild, role) is not None,
        },
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
            "channel": {
                "id": str(m.channel_id),
                "name": channel.name if channel is not None else None,
                "invalid": channel is None,
            },
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


# ====== 編輯 ======
@dataclass(frozen=True)
class _Btn:
    role_id: int
    title: str
    emoji: str | None
    style: int | None

    def key(self) -> tuple[str, str | None, int | None]:
        return (self.title, self.emoji, self.style)


class ButtonIn(BaseModel):
    role_id: int | str
    title: str
    emoji: str | None = None
    style: int | None = None


class OriginalIn(BaseModel):
    content_json: str | None = None
    buttons: list[ButtonIn]


class NewTarget(BaseModel):
    kind: Literal["new"]
    channel_id: int | str


class ExistingTarget(BaseModel):
    kind: Literal["existing"]
    channel_id: int | str
    message_id: int | str


class CreateBody(BaseModel):
    target: NewTarget | ExistingTarget
    #: 新訊息必填；掛到既有訊息時，內容不能改（content_locked）必須為 null
    message: MessageContent | None = None
    buttons: list[ButtonIn]


class UpdateBody(BaseModel):
    #: 內容不能改（content_locked）時必須為 null
    message: MessageContent | None = None
    buttons: list[ButtonIn]
    original: OriginalIn


def _field(path: str, reason: str) -> dict:
    return {"path": path, "reason": reason}


def _to_int(value: int | str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None


def _parse_buttons(buttons: list[ButtonIn]) -> list[_Btn]:
    """欄位格式與數量、同身分組不重複；不合規則丟 400 invalid_request 並附 fields。"""
    errors: list[dict] = []
    if not buttons:
        errors.append(_field("buttons", "至少要有一顆按鈕"))
    if len(buttons) > MAX_BUTTONS:
        errors.append(_field("buttons", f"按鈕不能超過 {MAX_BUTTONS} 顆"))
    result: list[_Btn] = []
    seen: set[int] = set()
    for i, b in enumerate(buttons):
        role_id = _to_int(b.role_id)
        if role_id is None:
            errors.append(_field(f"buttons.{i}.role_id", "必須是 Discord ID"))
            continue
        if role_id in seen:
            errors.append(_field(f"buttons.{i}.role_id", "同一個身分組只能出現一次"))
        seen.add(role_id)
        title = b.title.strip()
        if not title:
            errors.append(_field(f"buttons.{i}.title", "標題不能空白"))
        elif len(title) > MAX_TITLE:
            errors.append(_field(f"buttons.{i}.title", f"標題不能超過 {MAX_TITLE} 字"))
        emoji = (b.emoji or "").strip() or None
        if emoji is not None and len(emoji) > MAX_EMOJI:
            errors.append(_field(f"buttons.{i}.emoji", "emoji 格式不正確"))
        if b.style is not None and b.style not in BUTTON_STYLES:
            errors.append(_field(f"buttons.{i}.style", "不是有效的樣式"))
        result.append(_Btn(role_id, title, emoji, b.style))
    if errors:
        raise DashboardError(400, "invalid_request", fields=errors)
    return result


def _canon(buttons: list[dict]) -> str:
    """按鈕快照的正規化字串（順序保留），衝突比對用；Discord ID 一律轉成字串。"""
    items = [
        {"role_id": str(b["role_id"]), "title": b["title"], "emoji": b.get("emoji") or None, "style": b.get("style")}
        for b in buttons
    ]
    return json.dumps(items, sort_keys=True, ensure_ascii=False)


def _snapshot_current(snap: dict) -> dict:
    return {"content_json": snap["content_json"], "buttons": _canon(snap["buttons"])}


def _actor(guild: discord.Guild, info: SessionInfo) -> discord.Member:
    member = guild.get_member(int(info.discord_user_id))
    if member is None:
        raise DashboardError(403, "no_permission")
    return member


def _role_state(guild: discord.Guild, actor: discord.Member, role_id: int) -> tuple[discord.Role | None, str | None]:
    """(身分組, 停用原因)。原因依序為：bot 不能發放、操作者位階不足。"""
    role = guild.get_role(role_id)
    reason = role_issue(guild, role)
    if reason is None and role is not None:
        reason = operator_rank_issue(guild, actor, role)
    return role, reason


def _options_payload(guild: discord.Guild, actor: discord.Member) -> dict:
    roles = []
    for role in sorted(guild.roles, key=lambda r: r.position, reverse=True):
        _, reason = _role_state(guild, actor, role.id)
        dangerous = dangerous_permissions(role)
        roles.append(
            {
                "id": str(role.id),
                "name": role.name,
                "color": role.color.value,
                "disabled_reason": reason,
                "dangerous": bool(dangerous),
                "dangerous_permissions": dangerous,
            }
        )
    return {
        "channels": [
            {
                "id": str(c.id),
                "name": c.name,
                "category": c.category.name if c.category is not None else None,
                "permission_issues": [asdict(i) for i in bot_permission_issues(guild, c)],
            }
            for c in sorted(
                guild.text_channels, key=lambda c: (c.category.position if c.category else -1, c.position, c.id)
            )
        ],
        "roles": roles,
        "emojis": [{"id": str(e.id), "name": e.name, "animated": e.animated, "value": str(e)} for e in guild.emojis],
    }


def _stored_content(content_json: str | None) -> MessageContent | None:
    if content_json is None:
        return None
    try:
        return from_json(content_json)
    except ValidationError, ValueError:
        return None


async def _load_message(guild: discord.Guild, channel_id: int, message_id: int) -> discord.Message | None:
    """訊息讀不到（頻道或訊息已刪除、缺權限）回 None。"""
    channel = guild.get_channel(channel_id)
    if channel is None:
        return None
    try:
        return await channel.fetch_message(message_id)  # pyright: ignore[reportAttributeAccessIssue]
    except discord.HTTPException:
        return None


async def _content_state(
    guild: discord.Guild, snap: dict, message_id: int, message: discord.Message | None = None
) -> tuple[MessageContent | None, str | None]:
    """(內容, content_locked 原因)。存下的內容優先；沒有就從 Discord 訊息讀回。"""
    stored = _stored_content(snap["content_json"])
    if stored is not None:
        return stored, None
    message = message or await _load_message(guild, snap["channel_id"], message_id)
    if message is None:
        return None, REASON_MESSAGE_UNAVAILABLE
    return from_message(message)


async def _detail(guild: discord.Guild, actor: discord.Member, snap: dict, message_id: int) -> dict:
    channel = guild.get_channel(snap["channel_id"])
    content, locked = await _content_state(guild, snap, message_id)
    buttons = []
    for b in snap["buttons"]:
        role, reason = _role_state(guild, actor, b["role_id"])
        rank_locked = role is not None and operator_rank_issue(guild, actor, role) is not None
        buttons.append(
            {
                "role_id": str(b["role_id"]),
                "role": {
                    "id": str(b["role_id"]),
                    "name": role.name if role is not None else None,
                    "invalid": role_issue(guild, role) is not None,
                },
                "title": b["title"],
                "emoji": b["emoji"],
                "emoji_invalid": not emoji_valid(guild, b["emoji"]),
                "style": b["style"],
                "locked": rank_locked,
                "locked_reason": reason if rank_locked else None,
            }
        )
    return {
        "message_id": str(message_id),
        "channel": {
            "id": str(snap["channel_id"]),
            "name": channel.name if channel is not None else None,
            "invalid": channel is None,
        },
        "content": content.model_dump() if content is not None else None,
        "content_json": snap["content_json"],
        "content_locked": locked,
        "buttons": buttons,
    }


def _check_buttons(guild: discord.Guild, actor: discord.Member, buttons: list[_Btn], existing: dict[int, _Btn]) -> None:
    """只檢查新增或有變動的按鈕：身分組可發放、操作者位階、自訂 emoji 屬於本伺服器。

    既有按鈕位階不低於操作者時被修改，回 400 locked_button；沒變動的按鈕（含失效的）一律放行。
    """
    errors: list[dict] = []
    locked: list[dict] = []
    for i, b in enumerate(buttons):
        old = existing.get(b.role_id)
        if old is not None and old.key() == b.key():
            continue
        role = guild.get_role(b.role_id)
        if old is not None and role is not None and (reason := operator_rank_issue(guild, actor, role)) is not None:
            locked.append(_field(f"buttons.{i}.role_id", f"位階不低於你的按鈕只能刪除，不能修改（{reason}）"))
            continue
        _, reason = _role_state(guild, actor, b.role_id)
        if reason is not None:
            errors.append(_field(f"buttons.{i}.role_id", reason))
        if not emoji_valid(guild, b.emoji):
            errors.append(_field(f"buttons.{i}.emoji", "只能使用 Unicode emoji 或這個伺服器的自訂 emoji"))
    if locked:
        raise DashboardError(400, "locked_button", fields=locked)
    if errors:
        raise DashboardError(400, "invalid_request", fields=errors)


def _db_options(message_id: int, buttons: list[_Btn]) -> list[ReactionRoleOption]:
    return [
        ReactionRoleOption(
            message_id=message_id,
            role_id=b.role_id,
            title=b.title,
            description=None,
            emoji=b.emoji,
            style=b.style,
            position=i,
        )
        for i, b in enumerate(buttons)
    ]


def _discord_error(e: discord.HTTPException) -> DashboardError:
    return DashboardError(502, "discord_error", message=e.text or str(e))


async def _delete_quietly(message: discord.Message) -> None:
    try:
        await message.delete()
    except discord.HTTPException:
        log.exception("Reaction role: failed to delete message", extra={"message_id": message.id})


@router.get("/guilds/{guild_id}/reaction-roles/options")
async def get_options(
    guild_id: int = Depends(require_section(Section.REACTION_ROLES)), info: SessionInfo = Depends(require_session)
):
    return await on_guild(guild_id, lambda guild: _options_payload(guild, _actor(guild, info)))


CANDIDATE_HISTORY = 100
MAX_CANDIDATES = 25
_LINK = re.compile(
    r"^\s*<?https?://(?:(?:ptb|canary)\.)?discord(?:app)?\.com/channels/(\d+)/(\d+)/(\d+)/?>?\s*$"
)

_TARGET_REASONS = {
    "wrong_guild": "這則訊息不屬於這個伺服器",
    "not_bot_message": "只能掛在我發的訊息上",
    "has_components": "這則訊息已經帶有其他按鈕或互動元件，不能掛反應身分組",
    "message_not_found": "找不到這則訊息",
    "bot_missing_permission": "我看不到這個頻道的訊息，請確認我有 View Channel 與 Read Message History",
}


def _target_error(code: str, **extra) -> DashboardError:
    return DashboardError(400 if code != "message_not_found" else 404, code, message=_TARGET_REASONS[code], **extra)


async def _fetch_target(guild: discord.Guild, channel_id: int, message_id: int) -> tuple[object, discord.Message]:
    """取得要掛的既有訊息；頻道不屬於本伺服器、訊息不存在、讀不到都丟對應的錯誤。"""
    channel = guild.get_channel(channel_id)
    if channel is None or channel not in guild.text_channels:
        raise _target_error("wrong_guild")
    try:
        return channel, await channel.fetch_message(message_id)
    except discord.NotFound:
        raise _target_error("message_not_found") from None
    except discord.Forbidden:
        raise _target_error("bot_missing_permission") from None
    except discord.HTTPException as e:
        raise _discord_error(e) from None


def _ensure_attachable(guild: discord.Guild, message: discord.Message) -> None:
    """bot 發的、沒有其他互動元件（已是反應身分組的由呼叫端先處理）。"""
    if message.author.id != guild.me.id:
        raise _target_error("not_bot_message")
    if message.components:
        raise _target_error("has_components")


def _candidate_summary(message: discord.Message) -> str:
    return _summarize(message) or "（沒有文字內容）"


@router.get("/guilds/{guild_id}/reaction-roles/candidates")
async def list_candidates(channel_id: int, guild_id: int = Depends(require_section(Section.REACTION_ROLES))):
    registered = {m.message_id for m in await run_db(lambda: _load(guild_id))}

    async def _read_candidates(guild: discord.Guild) -> dict:
        channel = guild.get_channel(channel_id)
        if channel is None or channel not in guild.text_channels:
            raise DashboardError(400, "invalid_request", fields=[_field("channel_id", "找不到這個文字頻道")])
        items: list[dict] = []
        free = 0
        try:
            async for m in channel.history(limit=CANDIDATE_HISTORY):
                if m.author.id != guild.me.id:
                    continue
                if m.id in registered:
                    status = "reaction_role"
                elif m.components:
                    continue
                else:
                    if free >= MAX_CANDIDATES:
                        continue
                    free += 1
                    status = "free"
                items.append(
                    {
                        "message_id": str(m.id),
                        "summary": _candidate_summary(m),
                        "created_at": m.created_at.isoformat(),
                        "status": status,
                    }
                )
        except discord.Forbidden:
            raise _target_error("bot_missing_permission") from None
        except discord.HTTPException as e:
            raise _discord_error(e) from None
        return {"messages": items}

    return await on_guild_async(guild_id, _read_candidates)


@router.get("/guilds/{guild_id}/reaction-roles/resolve")
async def resolve_link(link: str, guild_id: int = Depends(require_section(Section.REACTION_ROLES))):
    found = _LINK.match(link)
    if found is None:
        raise DashboardError(400, "invalid_link", message="不是 Discord 訊息連結")
    link_guild, channel_id, message_id = (int(x) for x in found.groups())
    if link_guild != guild_id:
        raise _target_error("wrong_guild")
    registered = await run_db(lambda: sqldb.get_reaction_role_snapshot(message_id)) is not None

    async def _resolve(guild: discord.Guild) -> dict:
        channel, message = await _fetch_target(guild, channel_id, message_id)
        if message.author.id != guild.me.id:
            raise _target_error("not_bot_message")
        base = {
            "message_id": str(message_id),
            "channel": {"id": str(channel_id), "name": channel.name},  # pyright: ignore[reportAttributeAccessIssue]
            "jump_url": message.jump_url,
            "summary": _candidate_summary(message),
        }
        if registered:
            return {**base, "status": "reaction_role"}
        if message.components:
            raise _target_error("has_components")
        content, locked = from_message(message)
        return {
            **base,
            "status": "free",
            "content": content.model_dump() if content is not None else None,
            "content_locked": locked,
        }

    return await on_guild_async(guild_id, _resolve)


@router.get("/guilds/{guild_id}/reaction-roles/{message_id}")
async def get_reaction_role(
    message_id: int,
    guild_id: int = Depends(require_section(Section.REACTION_ROLES)),
    info: SessionInfo = Depends(require_session),
):
    snap = await run_db(lambda: sqldb.get_reaction_role_snapshot(message_id))
    if snap is None or snap["guild_id"] != guild_id:
        raise DashboardError(404, "not_found")
    return await on_guild_async(guild_id, lambda guild: _detail(guild, _actor(guild, info), snap, message_id))


@router.post("/guilds/{guild_id}/reaction-roles")
async def create_reaction_role(
    body: CreateBody,
    guild_id: int = Depends(require_section(Section.REACTION_ROLES)),
    info: SessionInfo = Depends(require_session),
):
    if body.message is not None:
        ensure_valid_message(body.message)
    buttons = _parse_buttons(body.buttons)
    channel_id = _to_int(body.target.channel_id)
    if channel_id is None:
        raise DashboardError(400, "invalid_request", fields=[_field("target.channel_id", "必須是 Discord ID")])
    if isinstance(body.target, ExistingTarget):
        target_message_id = _to_int(body.target.message_id)
        if target_message_id is None:
            raise DashboardError(400, "invalid_request", fields=[_field("target.message_id", "必須是 Discord ID")])
        return await on_guild_async(
            guild_id, lambda guild: _attach(guild, info, guild_id, channel_id, target_message_id, body.message, buttons)
        )
    if body.message is None:
        raise DashboardError(400, "invalid_request", fields=[_field("message", "新訊息必須有內容")])
    message_content = body.message

    async def _create(guild: discord.Guild) -> dict:
        actor = _actor(guild, info)
        channel = guild.get_channel(channel_id)
        if channel is None or channel not in guild.text_channels:
            raise DashboardError(400, "invalid_request", fields=[_field("target.channel_id", "找不到這個文字頻道")])
        missing = [
            i for i in bot_permission_issues(guild, channel) if i.permission in ("View Channel", "Send Messages")
        ]
        if missing:
            raise DashboardError(
                400,
                "bot_missing_permission",
                fields=[_field("target.channel_id", f"我在這個頻道缺少 {missing[0].permission}")],
            )
        _check_buttons(guild, actor, buttons, {})

        try:
            sent = await channel.send(**to_send_kwargs(message_content), allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException as e:
            raise _discord_error(e) from None
        view = ReactionRoleView(sent.id, _db_options(sent.id, buttons))
        try:
            await sent.edit(view=view)
        except discord.HTTPException as e:
            await _delete_quietly(sent)
            raise _discord_error(e) from None
        sclient.bot.add_view(view, message_id=sent.id)  # pyright: ignore[reportOptionalMemberAccess]
        content_json = to_json(message_content)
        try:
            await run_db(
                lambda: sqldb.replace_reaction_role_message(
                    guild_id, channel_id, sent.id, content_json, _db_options(sent.id, buttons)
                )
            )
        except Exception:
            log.exception("Reaction role create: DB write failed, deleting message", extra={"message_id": sent.id})
            view.stop()
            await _delete_quietly(sent)
            raise DashboardError(500, "save_failed") from None
        return {"message_id": str(sent.id), "jump_url": sent.jump_url}

    return await on_guild_async(guild_id, _create)


async def _attach(
    guild: discord.Guild,
    info: SessionInfo,
    guild_id: int,
    channel_id: int,
    message_id: int,
    content: MessageContent | None,
    buttons: list[_Btn],
) -> dict:
    """掛到 bot 既有的訊息：編輯原訊息加上按鈕。內容不能改時 content 必須為 null，content_json 記 null。"""
    actor = _actor(guild, info)
    _, message = await _fetch_target(guild, channel_id, message_id)
    if message.author.id != guild.me.id:
        raise _target_error("not_bot_message")
    if await run_db(lambda: sqldb.get_reaction_role_snapshot(message_id)) is not None:
        raise DashboardError(
            400, "already_reaction_role", message="這則訊息已經是反應身分組，請改用編輯", message_id=str(message_id)
        )
    if message.components:
        raise _target_error("has_components")
    current, locked = from_message(message)
    if locked is not None and content is not None:
        raise DashboardError(400, "content_locked", reason=locked)
    if locked is None and content is None:
        content = current
    _check_buttons(guild, actor, buttons, {})

    old_edit = {"content": message.content or None, "embeds": list(message.embeds)} if content is not None else {}
    view = ReactionRoleView(message_id, _db_options(message_id, buttons))
    try:
        await message.edit(**(to_send_kwargs(content) if content is not None else {}), view=view)
    except discord.HTTPException as e:
        raise _discord_error(e) from None
    sclient.bot.add_view(view, message_id=message_id)  # pyright: ignore[reportOptionalMemberAccess]
    content_json = to_json(content) if content is not None else None
    try:
        await run_db(
            lambda: sqldb.replace_reaction_role_message(
                guild_id, channel_id, message_id, content_json, _db_options(message_id, buttons)
            )
        )
    except Exception:
        log.exception("Reaction role attach: DB write failed, restoring message", extra={"message_id": message_id})
        view.stop()
        try:
            await message.edit(**old_edit, view=None)
        except discord.HTTPException:
            log.exception("Reaction role attach: restore failed", extra={"message_id": message_id})
        raise DashboardError(500, "save_failed") from None
    return {"message_id": str(message_id), "jump_url": message.jump_url}


@router.put("/guilds/{guild_id}/reaction-roles/{message_id}")
async def update_reaction_role(
    message_id: int,
    body: UpdateBody,
    guild_id: int = Depends(require_section(Section.REACTION_ROLES)),
    info: SessionInfo = Depends(require_session),
):
    if body.message is not None:
        ensure_valid_message(body.message)
    buttons = _parse_buttons(body.buttons)
    original = {
        "content_json": body.original.content_json,
        "buttons": _canon([b.model_dump() for b in body.original.buttons]),
    }

    async def _update(guild: discord.Guild) -> dict:
        actor = _actor(guild, info)
        snap = await run_db(lambda: sqldb.get_reaction_role_snapshot(message_id))
        if snap is None or snap["guild_id"] != guild_id:
            raise Conflict(None).to_error()
        if check_conflict(_snapshot_current(snap), original) is not None:
            raise DashboardError(409, "conflict", deleted=False, current=await _detail(guild, actor, snap, message_id))

        message = await _load_message(guild, snap["channel_id"], message_id)
        if message is None:
            raise DashboardError(404, "message_not_found")
        _, locked = await _content_state(guild, snap, message_id, message)
        if body.message is not None and locked is not None:
            raise DashboardError(400, "content_locked", reason=locked)
        existing = {
            b["role_id"]: _Btn(b["role_id"], b["title"], b["emoji"] or None, b["style"]) for b in snap["buttons"]
        }
        _check_buttons(guild, actor, buttons, existing)

        old_view = ReactionRoleView(message_id, _db_options(message_id, list(existing.values())))
        old_edit = (
            {"content": message.content or None, "embeds": list(message.embeds)} if body.message is not None else {}
        )
        new_edit = to_send_kwargs(body.message) if body.message is not None else {}
        view = ReactionRoleView(message_id, _db_options(message_id, buttons))
        try:
            await message.edit(**new_edit, view=view)
        except discord.HTTPException as e:
            raise _discord_error(e) from None
        sclient.bot.add_view(view, message_id=message_id)  # pyright: ignore[reportOptionalMemberAccess]

        content_json = to_json(body.message) if body.message is not None else None
        try:
            await run_db(
                lambda: sqldb.replace_reaction_role_message(
                    guild_id, snap["channel_id"], message_id, content_json, _db_options(message_id, buttons)
                )
            )
        except Exception:
            log.exception("Reaction role update: DB write failed, restoring message", extra={"message_id": message_id})
            try:
                await message.edit(**old_edit, view=old_view)
                sclient.bot.add_view(old_view, message_id=message_id)  # pyright: ignore[reportOptionalMemberAccess]
            except discord.HTTPException:
                log.exception("Reaction role update: restore failed", extra={"message_id": message_id})
            raise DashboardError(500, "save_failed") from None

        fresh = await run_db(lambda: sqldb.get_reaction_role_snapshot(message_id))
        return await _detail(guild, actor, fresh, message_id)

    return await on_guild_async(guild_id, _update)
