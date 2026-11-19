"""網站帳號測試共用：假 bot、`account()` 與另一位使用者的 ID。"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from uuid import UUID

from starlib.identity import Account, LinkedPassport
from tests.helpers.dashboard_auth import USER_ID

OTHER_ID = "222222222222222222"


class FakeBot:
    """users：Discord ID -> (名稱, 頭像 hash)；不在裡面的 fetch_user 失敗。"""

    def __init__(self, users: dict[int, tuple[str, str | None]]):
        self.users = users
        self._pool = ThreadPoolExecutor(max_workers=1)

    def _user(self, uid: int):
        name, avatar = self.users[uid]
        return SimpleNamespace(global_name=name, name="x", avatar=SimpleNamespace(key=avatar) if avatar else None)

    def get_user(self, uid: int):
        return None

    async def fetch_user(self, uid: int):
        if uid not in self.users:
            raise RuntimeError("Unknown User")
        return self._user(uid)

    def submit(self, coro):
        return self._pool.submit(asyncio.run, coro)


def account(account_id: UUID, discord_ids=(int(USER_ID),), suspended=False, username="willy") -> Account:
    return Account(
        account_id=account_id,
        username=username,
        roles=(),
        suspended=suspended,
        discord_passports=tuple(LinkedPassport(str(i), None) for i in discord_ids),
    )
