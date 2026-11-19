"""GET /dashboard/guilds/{id}/sections：使用者在該伺服器可進入的區塊與動作，供前端導覽與權限提示。"""

from fastapi import APIRouter, Depends

from .access import Section, section_actions
from .errors import DashboardError
from .guilds import can_enter, guild_perms
from .session import DiscordSessionInfo, require_session

router = APIRouter(prefix="/dashboard")


@router.get("/guilds/{guild_id}/sections")
async def list_sections(guild_id: int, info: DiscordSessionInfo = Depends(require_session)):
    """依 Section 宣告順序列出有權限的區塊；不符合進入條件回 403 no_permission。"""
    perms = await guild_perms(info.discord_user_id, guild_id)
    if not can_enter(perms):
        raise DashboardError(403, "no_permission")
    sections = [
        {"key": section.value, "actions": actions}
        for section in Section
        if (actions := section_actions(perms, section))
    ]
    return {"sections": sections}
