"""auth server 內部 API：bot 用 Discord ID 或其他平台的通行證查域民。"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import quote
from uuid import UUID

import aiohttp

log = logging.getLogger(__name__)

# auth server 查無此人時回的 detail，見 domalyze-identity internal.py
NOT_FOUND_DETAIL = "account not found"


@dataclass(frozen=True)
class Account:
    account_id: UUID
    username: str | None
    roles: tuple[str, ...]
    suspended: bool


@dataclass(frozen=True)
class ResolvedAccount:
    """以 account_id 查詢的結果；查的是被併掉的舊 ID 時，account 是存續者，merged_from 是查詢用的舊 ID"""

    account: Account
    merged_from: UUID | None = None


class DirectoryUnavailable(Exception):
    """auth server 沒給出明確答案：連不上、逾時、5xx、401 等，不能當成查無此人"""


class AccountDirectory(Protocol):
    async def find_by_passport(self, provider: str, subject: str) -> Account | None:
        """provider 是 auth server 的登入方式代號；查無此人回 None，停權的域民照樣回傳；沒得到明確答案時 raise DirectoryUnavailable"""
        ...

    async def find_by_discord(self, discord_id: int) -> Account | None:
        """查無此人回 None；沒得到明確答案時 raise DirectoryUnavailable"""
        ...

    async def find_by_account_id(self, account_id: UUID) -> ResolvedAccount | None:
        """被併掉的 ID 回存續者並帶 merged_from；查無此人（含已刪除）回 None；沒得到明確答案時 raise DirectoryUnavailable"""
        ...


class DomalyzeIdentityClient:
    """以 `Authorization: Bearer <金鑰>` 呼叫 auth server 內部 API"""

    def __init__(self, base_url: str, service_key: str, timeout: float = 1.5):
        # 逾時要短於 Discord 互動的 3 秒回應期限，連不上時才來得及回「稍後再試」
        self._base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {service_key}"}
        self._timeout = aiohttp.ClientTimeout(total=timeout)

    async def find_by_passport(self, provider: str, subject: str) -> Account | None:
        extra = {"provider": provider, "subject": subject}
        data = await self._get(f"/v1/passports/{quote(provider, safe='')}/{quote(subject, safe='')}", extra)
        return None if data is None else self._parse_account(data, extra)

    async def find_by_discord(self, discord_id: int) -> Account | None:
        return await self.find_by_passport("discord", str(discord_id))

    async def find_by_account_id(self, account_id: UUID) -> ResolvedAccount | None:
        data = await self._get(f"/v1/accounts/{account_id}", {"account_id": str(account_id)})
        if data is None:
            return None
        extra = {"account_id": str(account_id)}
        account = self._parse_account(data, extra)
        merged_from = data.get("mergedFrom")
        if merged_from is None:
            return ResolvedAccount(account)
        try:
            return ResolvedAccount(account, merged_from=UUID(merged_from))
        except (TypeError, ValueError) as e:
            log.error("auth server: malformed response", extra=extra)
            raise DirectoryUnavailable("malformed response") from e

    async def _get(self, path: str, extra: dict) -> dict | None:
        """200 回 JSON；auth server 自己的查無此人回 None；其餘一律 raise DirectoryUnavailable"""
        url = f"{self._base_url}{path}"
        try:
            async with aiohttp.ClientSession(timeout=self._timeout, headers=self._headers) as session:
                async with session.get(url) as resp:
                    if resp.status == 404:
                        # 路徑錯、URL 指到別的服務也會 404，只有 auth server 自己的查無此人才算明確答案
                        body = await resp.json(content_type=None)
                        if isinstance(body, dict) and body.get("detail") == NOT_FOUND_DETAIL:
                            return None
                        log.error("auth server: unexpected 404", extra=extra)
                        raise DirectoryUnavailable("unexpected 404")
                    if resp.status != 200:
                        # 401 代表金鑰設錯，當成查無此人會替所有人發臨時 ID
                        log.error("auth server: unexpected status", extra={"status": resp.status, **extra})
                        raise DirectoryUnavailable(f"auth server returned {resp.status}")
                    data = await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as e:
            log.warning("auth server: unreachable", extra={"error": repr(e), **extra})
            raise DirectoryUnavailable(str(e)) from e
        if not isinstance(data, dict):
            log.error("auth server: malformed response", extra=extra)
            raise DirectoryUnavailable("malformed response")
        return data

    @staticmethod
    def _parse_account(data: dict, extra: dict) -> Account:
        try:
            return Account(
                account_id=UUID(data["accountId"]),
                username=data.get("username"),
                roles=tuple(data.get("roles") or ()),
                suspended=bool(data.get("suspended", False)),
            )
        except (KeyError, TypeError, ValueError) as e:
            log.error("auth server: malformed response", extra=extra)
            raise DirectoryUnavailable("malformed response") from e
