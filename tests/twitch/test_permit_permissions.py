from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from starServer.twitch_bot import moderation, state


async def test_viewer_permit_silently_returns_before_lookup(monkeypatch):
    lookup = Mock()
    monkeypatch.setattr(state, "twitch", SimpleNamespace(get_users=lookup), raising=False)
    cmd = SimpleNamespace(
        parameter="alice",
        room=SimpleNamespace(room_id="123"),
        user=SimpleNamespace(id="456", mod=False),
        reply=AsyncMock(),
    )

    await moderation.permit(cmd)

    cmd.reply.assert_not_awaited()
    lookup.assert_not_called()
