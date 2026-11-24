import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from starServer.dashboard import channel_enforcement, twitch_control
from starServer.dashboard.errors import DashboardError
from tests.dashboard.test_channel_moderation import channel_id, host, start_chat  # noqa: F401
from tests.twitch.test_moderation_enforcement_rpc import (
    call,
    handlers,  # noqa: F401
    helix,  # noqa: F401
    helix_punishment,
    helix_response,
    lift_payload,
)


@pytest.mark.parametrize("difference", ["missing", "moderator", "new_ban", "timeout", "new_expiry"])
def test_unban_skips_different_current_punishment(helix, handlers, start_chat, channel_id, difference):
    start_chat()
    helix.install()
    payload = lift_payload(channel_id)
    started = datetime.fromisoformat(payload["at"])
    future = (started + timedelta(minutes=10)).isoformat()
    match difference:
        case "missing":
            helix.return_value = helix_response(200, {"data": [], "pagination": {}})
        case "moderator":
            helix.return_value = helix_punishment(payload, moderator_id="100")
        case "new_ban":
            helix.return_value = helix_punishment(payload, created_at=future)
        case "timeout":
            helix.return_value = helix_punishment(payload, expires_at=future)
        case "new_expiry":
            payload.update(action="timeout", duration=300)
            helix.return_value = helix_punishment(payload, expires_at=future)

    assert call(handlers, "moderation.lift", payload) == {"result": "not_punished"}
    assert [request.args[0] for request in helix.await_args_list] == ["GET"]


def test_unban_lifts_matching_current_timeout(helix, handlers, start_chat, channel_id):
    start_chat()
    helix.install()
    payload = lift_payload(channel_id)
    payload.update(action="timeout", duration=600)
    expires_at = (datetime.fromisoformat(payload["at"]) + timedelta(seconds=600)).isoformat()
    helix.side_effect = [helix_punishment(payload, expires_at=expires_at), helix_response(204)]

    assert call(handlers, "moderation.lift", payload) == {"result": "lifted"}
    assert [request.args[0] for request in helix.await_args_list] == ["GET", "DELETE"]


def test_failed_enforcement_row_cannot_reach_bot(monkeypatch):
    monkeypatch.setattr(
        channel_enforcement, "_find", AsyncMock(return_value=SimpleNamespace(status="failed", action="ban"))
    )
    call_bot = AsyncMock()
    monkeypatch.setattr(twitch_control, "call_channel", call_bot)
    with pytest.raises(DashboardError, match="not_liftable"):
        asyncio.run(channel_enforcement.lift(1, 2))
    call_bot.assert_not_awaited()
