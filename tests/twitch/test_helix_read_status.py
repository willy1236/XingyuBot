import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from twitchAPI.type import AuthType

from starServer.twitch_bot import speech, state, stream_info
from starServer.twitch_bot.helix import BotTwitch, TwitchStatusError


@pytest.mark.parametrize(
    ("method", "endpoint"),
    [
        ("GET", "users"),
        ("GET", "streams"),
        ("GET", "search/categories"),
        ("GET", "channels"),
        ("GET", "moderation/banned"),
        ("PATCH", "channels"),
    ],
)
def test_helix_errors_precede_sdk_parsing(method, endpoint):
    client = BotTwitch("test-client", authenticate_app=False)
    with pytest.raises(TwitchStatusError, match="HTTP 429"):
        asyncio.run(
            client._check_request_return(
                None, SimpleNamespace(status=429), method, f"https://api.twitch.tv/helix/{endpoint}", AuthType.NONE, []
            )
        )


def test_uptime_retries_after_lookup_failure(monkeypatch):
    attempts = 0

    async def streams(**_):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise TwitchStatusError("GET", "streams", 429)
        for item in ():
            yield item

    monkeypatch.setattr(speech, "_live", {})
    monkeypatch.setattr(state, "twitch", SimpleNamespace(get_streams=streams), raising=False)
    cmd = SimpleNamespace(room=SimpleNamespace(room_id="123", name="host"), reply=AsyncMock())

    asyncio.run(stream_info.uptime(cmd))
    cmd.reply.assert_awaited_once_with("查詢開台狀態失敗，請稍後再試")
    assert 123 not in speech._live

    cmd.reply.reset_mock()
    asyncio.run(stream_info.uptime(cmd))
    cmd.reply.assert_awaited_once_with("未開台")


def test_category_lookup_failure_on_second_page_does_not_patch(monkeypatch):
    async def categories(*_, **__):
        yield SimpleNamespace(id="1", name="Only on first page")
        raise TwitchStatusError("GET", "search/categories", 429)

    patch = AsyncMock()
    monkeypatch.setattr(state, "twitch", SimpleNamespace(search_categories=categories), raising=False)
    monkeypatch.setattr(stream_info, "_authorize", AsyncMock(return_value="token"))
    monkeypatch.setattr(stream_info, "_patch", patch)
    cmd = SimpleNamespace(room=SimpleNamespace(room_id="123"), parameter="query", reply=AsyncMock())

    asyncio.run(stream_info.game(cmd))

    cmd.reply.assert_awaited_once_with(stream_info._FAILED)
    patch.assert_not_awaited()
