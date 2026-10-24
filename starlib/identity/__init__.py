"""
### 模組：身分解析
由 Discord ID 取得使用者 ID、由 Twitch ID 查域民，權威來源是 auth server。
"""

from .client import (
    Account,
    AccountDirectory,
    DirectoryUnavailable,
    DomalyzeIdentityClient,
    LinkedPassport,
    ResolvedAccount,
)
from .privilege import privilege_of
from .resolver import BotIdentity, IdentityResolver, IdentityUnavailable, LinkedPassports, fetch_linked_passports, resolve_identity
from .twitch import MemberUnknown, NotMember, TwitchLookup, TwitchMember, lookup_twitch_member

__all__ = [
    "Account",
    "AccountDirectory",
    "BotIdentity",
    "DirectoryUnavailable",
    "DomalyzeIdentityClient",
    "IdentityResolver",
    "IdentityUnavailable",
    "LinkedPassport",
    "LinkedPassports",
    "MemberUnknown",
    "NotMember",
    "ResolvedAccount",
    "TwitchLookup",
    "TwitchMember",
    "fetch_linked_passports",
    "lookup_twitch_member",
    "privilege_of",
    "resolve_identity",
]
