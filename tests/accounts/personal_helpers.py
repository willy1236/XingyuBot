"""個人區測試共用的 `directory`（後台的假 auth server）與 `identity`（resolve_identity 的回答）fixture。"""

from __future__ import annotations

import pytest

from starServer.dashboard import personal
from tests.helpers.dashboard_auth import USER_ID

OWN = int(USER_ID)


@pytest.fixture
def directory(dashboard_env):
    return dashboard_env.directory


@pytest.fixture
def identity(monkeypatch):
    """resolve_identity(create=False) 的回答：None 表示查無紀錄，例外表示身分服務不可用。"""
    state = {"result": None}

    async def fake(discord_id, *, create=True):
        assert create is False and discord_id == OWN
        if isinstance(state["result"], Exception):
            raise state["result"]
        return state["result"]

    monkeypatch.setattr(personal, "resolve_identity", fake)
    return state
