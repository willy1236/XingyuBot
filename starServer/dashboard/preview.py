"""POST /dashboard/guilds/{id}/preview：依通知種類與設定值產生範例訊息，給網頁呈現。"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .access import on_guild, require_guild_access
from .errors import DashboardError
from .samples import build_sample

router = APIRouter(prefix="/dashboard")


class PreviewBody(BaseModel):
    notify_type: str
    #: 表單的欄位值（role_id、message）；Discord ID 用字串
    values: dict[str, str | None] = {}


@router.post("/guilds/{guild_id}/preview")
async def preview(body: PreviewBody, guild_id: int = Depends(require_guild_access)):
    def _build(guild):
        sample = build_sample(body.notify_type, body.values, guild=guild)
        role = guild.get_role(sample.mention_role_id) if sample.mention_role_id is not None else None
        return {
            "content": sample.content,
            "embeds": [e.to_dict() for e in sample.embeds],
            "mention_role_id": None if sample.mention_role_id is None else str(sample.mention_role_id),
            "mention_role_name": role.name if role else None,
        }

    try:
        return await on_guild(guild_id, _build)
    except KeyError, ValueError:
        raise DashboardError(400, "invalid_request") from None
