"""twitchAPI 的公開執法方法必須將 Helix 拒絕回報給執法管線。"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from twitchAPI import twitch as sdk
from twitchAPI.type import AuthScope, ForbiddenError, TwitchAPIException, UnauthorizedException

from starServer import twitch_chatbot


@pytest.fixture
def helix(monkeypatch):
    request = AsyncMock()

    class Session:
        def __init__(self, **_options):
            pass

        async def __aenter__(self):
            return SimpleNamespace(request=request)

        async def __aexit__(self, *_exc):
            pass

    monkeypatch.setattr(sdk, "ClientSession", Session)
    client = twitch_chatbot.Twitch("test-client", authenticate_app=False)
    asyncio.run(
        client.set_user_authentication(
            "test-token",
            [AuthScope.MODERATOR_MANAGE_CHAT_MESSAGES, AuthScope.MODERATOR_MANAGE_BANNED_USERS],
            "test-refresh",
            validate=False,
        )
    )
    return client, request


def response(status):
    # 模擬不是 Twitch 正常 JSON 形狀的錯誤本文。
    return SimpleNamespace(status=status, headers={"Ratelimit-Reset": "0"}, json=AsyncMock(return_value=[]))


@pytest.mark.parametrize(
    ("method", "status", "error"),
    [
        ("delete", 429, TwitchAPIException),
        ("timeout", 429, TwitchAPIException),
        ("timeout", 409, TwitchAPIException),
        ("delete", 403, ForbiddenError),
        ("delete", 401, UnauthorizedException),
    ],
)
def test_helix_refusal_raises_an_enforcement_error(helix, method, status, error):
    client, request = helix
    client.auto_refresh_auth = False
    request.return_value = response(status)
    with pytest.raises(error):
        if method == "delete":
            asyncio.run(client.delete_chat_message("123", "234", "message-id"))
        else:
            asyncio.run(client.ban_user("123", "234", "345", "reason", duration=600))


def test_delete_retries_with_the_refreshed_token_after_401(helix, monkeypatch):
    client, request = helix
    request.side_effect = [response(401), response(204)]

    async def refresh():
        await client.set_user_authentication(
            "refreshed-token", [AuthScope.MODERATOR_MANAGE_CHAT_MESSAGES], "test-refresh", validate=False
        )

    refresh_mock = AsyncMock(side_effect=refresh)
    monkeypatch.setattr(client, "refresh_used_token", refresh_mock)

    asyncio.run(client.delete_chat_message("123", "234", "message-id"))

    refresh_mock.assert_awaited_once()
    assert [call.kwargs["headers"]["Authorization"] for call in request.await_args_list] == [
        "Bearer test-token",
        "Bearer refreshed-token",
    ]
