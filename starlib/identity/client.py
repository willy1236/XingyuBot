"""auth server 內部 API：bot 用 Discord ID 查域民。"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

import aiohttp

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Account:
    account_id: UUID
    username: str | None
    roles: tuple[str, ...]
    suspended: bool


class DirectoryUnavailable(Exception):
    """auth server 沒給出明確答案：連不上、逾時、5xx、401 等，不能當成查無此人"""


class AccountDirectory(Protocol):
    async def find_by_discord(self, discord_id: int) -> Account | None:
        """查無此人回 None；沒得到明確答案時 raise DirectoryUnavailable"""
        ...


class DomalyzeIdentityClient:
    """以 `Authorization: Bearer <金鑰>` 呼叫 auth server 內部 API"""

    def __init__(self, base_url: str, service_key: str, timeout: float = 2.5):
        # 逾時要短於 Discord 互動的 3 秒回應期限，連不上時才來得及回「稍後再試」
        self._base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {service_key}"}
        self._timeout = aiohttp.ClientTimeout(total=timeout)

    async def find_by_discord(self, discord_id: int) -> Account | None:
        url = f"{self._base_url}/v1/passports/discord/{discord_id}"
        try:
            async with aiohttp.ClientSession(timeout=self._timeout, headers=self._headers) as session:
                async with session.get(url) as resp:
                    if resp.status == 404:
                        return None
                    if resp.status != 200:
                        # 401 代表金鑰設錯，當成查無此人會替所有人發臨時 ID
                        log.error("auth server: unexpected status", extra={"status": resp.status, "discord_id": discord_id})
                        raise DirectoryUnavailable(f"auth server returned {resp.status}")
                    data = await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            log.warning("auth server: unreachable", extra={"error": repr(e), "discord_id": discord_id})
            raise DirectoryUnavailable(str(e)) from e

        try:
            return Account(
                account_id=UUID(data["accountId"]),
                username=data.get("username"),
                roles=tuple(data.get("roles") or ()),
                suspended=bool(data.get("suspended", False)),
            )
        except (KeyError, TypeError, ValueError) as e:
            log.error("auth server: malformed response", extra={"discord_id": discord_id})
            raise DirectoryUnavailable("malformed response") from e
