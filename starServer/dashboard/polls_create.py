"""投票發起（V-03）：
GET  /dashboard/guilds/{id}/polls/options  發起表單用：可選頻道（含停用原因）與身分組
POST /dashboard/guilds/{id}/polls          由星羽在指定頻道發出投票訊息，body 見 `CreateBody`

權限 `require_section(Section.POLLS, "create")`；操作者本人也要能在選定頻道發言。
欄位驗證交給 `starlib.polls.validate_poll_input`，建立與發送交給 `PollView.create_and_send`，發送失敗不留資料。
"""

import discord
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from starDiscord.uiElement.view import MESSAGE_FAILURE_TEXT, PollSendError, PollView
from starlib import sclient
from starlib.polls import validate_poll_input
from starlib.utils import nowtz

from .access import Section, on_guild, on_guild_async, require_section
from .errors import DashboardError
from .session import SessionInfo, require_session

router = APIRouter(prefix="/dashboard")

#: 可發起投票的頻道類型：文字頻道與公告頻道（不含討論串、論壇、語音）
CHANNEL_TYPES = {discord.ChannelType.text: "text", discord.ChannelType.news: "news"}

BOT_CANNOT_SPEAK = "星羽在這個頻道不能發言"
OPERATOR_CANNOT_SPEAK = "你在這個頻道不能發言"


class RoleWeightIn(BaseModel):
    role_id: int | str
    weight: int


class CreateBody(BaseModel):
    #: Discord ID，數字或數字字串都可以
    channel_id: int | str
    title: str
    options: list[str]
    show_name: bool = False
    check_results_in_advance: bool = True
    results_only_initiator: bool = False
    number_of_user_votes: int = 1
    only_roles: list[int | str] = []
    role_weights: list[RoleWeightIn] = []


def _field(path: str, reason: str) -> dict:
    return {"path": path, "reason": reason}


def _form_path(path: str, weight_index: dict[int, int]) -> str:
    """validate_poll_input 的 path 轉成表單用的命名：options[N] -> options.N、role_weights[role_id] -> role_weights.N.weight"""
    if path.startswith("options["):
        return "options." + path[len("options[") : -1]
    if path.startswith("role_weights["):
        return f"role_weights.{weight_index[int(path[len('role_weights[') : -1])]}.weight"
    return path


def _to_int(value: int | str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None


def _actor(guild: discord.Guild, info: SessionInfo) -> discord.Member:
    member = guild.get_member(int(info.discord_user_id))
    if member is None:
        raise DashboardError(403, "no_permission")
    return member


def _can_speak(channel, member) -> bool:
    perms = channel.permissions_for(member)
    return perms.view_channel and perms.send_messages


def _disabled_reason(guild: discord.Guild, channel, actor: discord.Member) -> str | None:
    if not _can_speak(channel, guild.me):
        return BOT_CANNOT_SPEAK
    if not _can_speak(channel, actor):
        return OPERATOR_CANNOT_SPEAK
    return None


def _options_payload(guild: discord.Guild, actor: discord.Member) -> dict:
    channels = [c for c in guild.text_channels if c.type in CHANNEL_TYPES]
    channels.sort(key=lambda c: (c.category.position if c.category else -1, c.position, c.id))
    roles = sorted(
        (r for r in guild.roles if not r.is_default() and not r.managed), key=lambda r: r.position, reverse=True
    )
    return {
        "channels": [
            {
                "id": str(c.id),
                "name": c.name,
                "type": CHANNEL_TYPES[c.type],
                "category": c.category.name if c.category is not None else None,
                "disabled_reason": _disabled_reason(guild, c, actor),
            }
            for c in channels
        ],
        "roles": [{"id": str(r.id), "name": r.name, "color": r.color.value} for r in roles],
    }


@router.get("/guilds/{guild_id}/polls/options")
async def get_options(
    guild_id: int = Depends(require_section(Section.POLLS, "create")), info: SessionInfo = Depends(require_session)
):
    return await on_guild(guild_id, lambda guild: _options_payload(guild, _actor(guild, info)))


def _role_errors(guild: discord.Guild, path: str, role_id: int | None) -> list[dict]:
    if role_id is None:
        return [_field(path, "必須是 Discord ID")]
    role = guild.get_role(role_id)
    if role is None or role.is_default() or role.managed:
        return [_field(path, "找不到這個身分組")]
    return []


@router.post("/guilds/{guild_id}/polls")
async def create_poll(
    body: CreateBody,
    guild_id: int = Depends(require_section(Section.POLLS, "create")),
    info: SessionInfo = Depends(require_session),
):
    title = body.title.strip()
    options = [o.strip() for o in body.options]

    only_roles: list[int] = []
    weight_ids: dict[int, int] = {}
    weight_index: dict[int, int] = {}
    id_errors: list[dict] = []
    for raw in body.only_roles:
        role_id = _to_int(raw)
        if role_id is None:
            id_errors.append(_field("only_roles", "必須是 Discord ID"))
        elif role_id not in only_roles:
            only_roles.append(role_id)
    for i, item in enumerate(body.role_weights):
        role_id = _to_int(item.role_id)
        if role_id is None:
            id_errors.append(_field("role_weights", "身分組必須是 Discord ID"))
        elif role_id in weight_ids:
            id_errors.append(_field("role_weights", "同一個身分組只能設定一次權重"))
        else:
            weight_ids[role_id] = item.weight
            weight_index[role_id] = i
    channel_id = _to_int(body.channel_id)

    async def _create(guild: discord.Guild) -> dict:
        actor = _actor(guild, info)
        validated = validate_poll_input(title, options, body.number_of_user_votes, weight_ids, None, nowtz())
        errors = [{**e, "path": _form_path(e["path"], weight_index)} for e in validated] + id_errors
        for role_id in only_roles:
            errors += _role_errors(guild, "only_roles", role_id)
        for role_id in weight_ids:
            errors += _role_errors(guild, "role_weights", role_id)

        channel = guild.get_channel(channel_id) if channel_id is not None else None
        bot_blocked = False
        if channel_id is None:
            errors.append(_field("channel_id", "必須是 Discord ID"))
        elif channel is None or channel.type not in CHANNEL_TYPES:
            errors.append(_field("channel_id", "找不到這個文字頻道"))
        elif not _can_speak(channel, guild.me):
            bot_blocked = True
        elif not _can_speak(channel, actor):
            errors.append(_field("channel_id", OPERATOR_CANNOT_SPEAK))
        if errors:
            raise DashboardError(400, "invalid_request", fields=errors)
        if bot_blocked:
            raise DashboardError(400, "bot_missing_permission", fields=[_field("channel_id", BOT_CANNOT_SPEAK)])
        assert channel is not None and channel_id is not None

        try:
            poll = await PollView.create_and_send(
                lambda embed, view: channel.send(embed=embed, view=view),  # pyright: ignore[reportAttributeAccessIssue]
                channel_id,
                bot=sclient.bot,
                creator_id=actor.id,
                guild_id=guild_id,
                title=title,
                options=options,
                show_name=body.show_name,
                check_results_in_advance=body.check_results_in_advance,
                results_only_initiator=body.results_only_initiator,
                number_of_user_votes=body.number_of_user_votes,
                ban_alternate_account_voting=False,
                only_roles=only_roles,
                role_weights=weight_ids,
            )
        except PollSendError as e:
            raise DashboardError(
                400,
                "poll_send_failed",
                message_failure=e.code,
                message_failure_text=MESSAGE_FAILURE_TEXT.get(e.code),
            ) from None
        return {
            "poll_id": poll.poll_id,
            "message_url": f"https://discord.com/channels/{guild_id}/{channel_id}/{poll.message_id}",
        }

    return await on_guild_async(guild_id, _create)
