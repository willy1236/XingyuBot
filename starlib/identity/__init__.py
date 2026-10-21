"""
### 模組：身分解析
由 Discord ID 取得使用者 ID，權威來源是 auth server。
"""

from .client import Account, AccountDirectory, DirectoryUnavailable, DomalyzeIdentityClient, LinkedPassport, ResolvedAccount
from .privilege import privilege_of
from .resolver import BotIdentity, IdentityResolver, IdentityUnavailable, resolve_identity

__all__ = [
    "Account",
    "AccountDirectory",
    "BotIdentity",
    "DirectoryUnavailable",
    "DomalyzeIdentityClient",
    "IdentityResolver",
    "IdentityUnavailable",
    "LinkedPassport",
    "ResolvedAccount",
    "privilege_of",
    "resolve_identity",
]
