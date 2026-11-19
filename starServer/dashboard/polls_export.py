"""投票匯出：
GET /dashboard/guilds/{id}/polls/{poll_id}/export.csv   各選項票數；實名投票接著列出逐票明細

可見範圍與詳細頁相同（`viewer_role`、`visibility`），看不到票數的投票回 403 results_hidden。
權限經 `require_section(Section.POLLS, "export")`。
"""

import csv
import io
import re
from datetime import UTC, datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

import discord
from fastapi import APIRouter, Depends
from fastapi.responses import Response

from starlib import sclient
from starlib.polls import viewer_role, visibility

from .access import Section, on_guild_async, require_section
from .db import run_db
from .errors import DashboardError
from .polls import _load_detail, _member_name
from .session import DiscordSessionInfo, require_session

router = APIRouter(prefix="/dashboard")

TAIPEI = ZoneInfo("Asia/Taipei")
LEFT_MEMBER = "已離開的成員"
#: 試算表會把這些開頭的儲存格當公式執行
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
_FILENAME_FORBIDDEN = re.compile(r'[\\/:*?"<>|\x00-\x1f\x7f]')


def _text(value: str) -> str:
    """文字欄位防公式注入：以公式字元開頭時前面補單引號。"""
    return "'" + value if value.startswith(_FORMULA_PREFIXES) else value


def _taipei(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(TAIPEI).strftime("%Y-%m-%d %H:%M:%S")


def _filename(poll_id: int, title: str) -> str:
    safe = _FILENAME_FORBIDDEN.sub("", title).strip().strip(".")
    return f"poll-{poll_id}-{safe}.csv" if safe else f"poll-{poll_id}.csv"


def _content_disposition(filename: str) -> str:
    ascii_name = re.sub(r"[^\x20-\x7e]", "_", filename)
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename, safe='')}"


@router.get("/guilds/{guild_id}/polls/{poll_id:int}/export.csv")
async def export_poll(
    poll_id: int,
    guild_id: int = Depends(require_section(Section.POLLS, "export")),
    info: DiscordSessionInfo = Depends(require_session),
):
    loaded = await run_db(lambda: _load_detail(guild_id, poll_id))
    if loaded is None:
        raise DashboardError(404, "poll_not_found")
    row, poll, results, _ = loaded
    user_id = int(info.discord_user_id)

    async def _build(guild: discord.Guild) -> str:
        is_owner = await sclient.bot.is_owner(discord.Object(user_id))  # type: ignore[arg-type]
        role = viewer_role(
            poll, user_id, is_owner=is_owner, creator_in_guild=guild.get_member(row.creator_id) is not None
        )
        show_counts, show_names = visibility(poll, role)
        if not show_counts:
            raise DashboardError(403, "results_hidden")

        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(["選項", "票數"])
        for option in results.options:
            writer.writerow([_text(option.name), option.count])
        if show_names:
            names = {o.option_id: o.name for o in results.options}
            writer.writerow([])
            writer.writerow(["成員名稱", "成員 ID", "選項", "權重", "投票時間"])
            for v in results.votes:
                writer.writerow(
                    [
                        _text(_member_name(guild, v.user_id) or LEFT_MEMBER),
                        v.user_id,
                        _text(names.get(v.option_id, "")),
                        v.weight,
                        _taipei(v.voted_at),
                    ]
                )
        return out.getvalue()

    body = await on_guild_async(guild_id, _build)
    return Response(
        content=b"\xef\xbb\xbf" + body.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": _content_disposition(_filename(row.id, row.title))},
    )
