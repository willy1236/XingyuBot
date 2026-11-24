import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from starlib import twitch_regulars
from starServer.dashboard import channel_regulars, twitch_control
from starServer.dashboard.errors import DashboardError
from starServer.twitch_bot import commands, moderation, state, viewers


@pytest.mark.parametrize("login", ["主播", "a b", "abc!"])
def test_dashboard_rejects_invalid_login_before_helix(monkeypatch, login):
    credentials = AsyncMock()
    monkeypatch.setattr(twitch_control, "broadcaster_credentials", credentials)
    with pytest.raises(DashboardError, match="user_not_found") as error:
        asyncio.run(channel_regulars._find_user(123, login))
    assert error.value.status == 404
    credentials.assert_not_awaited()


@pytest.mark.parametrize(
    ("command", "parameter", "reply"),
    [
        (moderation.permit, "a b", "用法：!permit <使用者>"),
        (moderation.permit, "a\tb", "用法：!permit <使用者>"),
        (viewers.regular_command, "add a b", "用法：!regular add|remove <使用者>"),
        (viewers.regular_command, "remove a\tb", "用法：!regular add|remove <使用者>"),
        (moderation.permit, " @主播 ", "找不到 Twitch 帳號 主播"),
        (viewers.regular_command, "add @主播", "找不到 Twitch 帳號 主播"),
    ],
)
def test_chat_distinguishes_extra_arguments_from_invalid_login(monkeypatch, command, parameter, reply):
    lookup = Mock()
    monkeypatch.setattr(commands, "may_manage", AsyncMock(return_value=True))
    monkeypatch.setattr(moderation, "_channels", {})
    monkeypatch.setattr(state, "twitch", SimpleNamespace(get_users=lookup), raising=False)
    cmd = SimpleNamespace(parameter=parameter, room=SimpleNamespace(room_id="123"), reply=AsyncMock())

    asyncio.run(command(cmd))

    cmd.reply.assert_awaited_once_with(reply)
    lookup.assert_not_called()
    assert twitch_regulars.valid_login("valid_login123")
