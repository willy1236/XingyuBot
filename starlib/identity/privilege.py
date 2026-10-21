"""由 auth server 的身分組換算 bot 的權限等級。"""

from starlib.database.postgresql.enums import PrivilegeLevel
from starlib.settings import get_settings

from .resolver import BotIdentity


def privilege_of(identity: BotIdentity | None) -> PrivilegeLevel:
    """
    臨時使用者、停權中、沒有身分資料或沒有對應身分組的人都是一般使用者；
    有多個對應身分組時取最高等級。對照表由設定 PRIVILEGE_ROLES 提供。
    """
    if identity is None or not identity.is_formal or identity.suspended:
        return PrivilegeLevel.User
    mapping = get_settings().PRIVILEGE_ROLES
    levels = [mapping[role] for role in identity.roles if role in mapping]
    return PrivilegeLevel(max(levels, default=PrivilegeLevel.User))
