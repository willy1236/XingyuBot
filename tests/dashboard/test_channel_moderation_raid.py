"""C-05：以 Raid 事件、聊天室及後台 API 驗收暫停過濾。"""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from starServer.twitch_bot import events
from tests.dashboard.test_channel_moderation import (
    BOT,
    LINK,
    channel_id,  # noqa: F401 (fixture)
    host,  # noqa: F401 (fixture)
    settings,
    start_chat,  # noqa: F401 (fixture)
)
from tests.dashboard.test_channel_moderation_filters import enable  # noqa: F401 (fixture)
from tests.dashboard.test_channel_moderation_penalties import assert_change_recorded, save

EMOTE_SPAM = "😀🎉😀🎉"


@pytest.fixture
def raid(monkeypatch, repo, channel_id):
    bus = Mock()
    monkeypatch.setattr(events, "sqldb", repo)
    monkeypatch.setattr(events, "get_bus", lambda: bus)
    payload = SimpleNamespace(
        metadata=SimpleNamespace(message_timestamp=datetime(2026, 11, 24, tzinfo=UTC)),
        event=SimpleNamespace(
            from_broadcaster_user_name="Raider",
            to_broadcaster_user_id=channel_id,
            to_broadcaster_user_login="host",
            to_broadcaster_user_name="Host",
            viewers=42,
        ),
    )

    def receive():
        asyncio.run(events.on_channel_raid(payload))

    return receive


def penalty_settings(client):
    values = settings(client)["settings"]
    return {key: value for key, value in values.items() if key != "updated_at"}


@pytest.mark.parametrize(
    ("kind", "message", "count"),
    [
        ("emote", EMOTE_SPAM, 1),
        ("caps", "HELLO WORLD", 1),
        ("repetition", "哈" * 10, 1),
        ("duplicate", "Hello", 3),
    ],
)
def test_預設暫停兩分鐘且連結照常處罰(enable, start_chat, raid, channel_id, kind, message, count):
    enable(kind)
    enable("link")
    chat = start_chat()
    raid()

    chat.now += 119
    for _ in range(count):
        chat.send(message)
    link = chat.send(LINK)
    assert chat.deletions == [(channel_id, BOT, link.id)]
    assert chat.timeouts == []

    # 跨訊息重複的三則訊息使用另一位觀眾，以免和暫停時的訊息共用記錄。
    chat.now += 2
    for _ in range(count - 1):
        chat.send(message, uid="2000000970", login="bob")
    violation = chat.send(message, uid="2000000970", login="bob")
    assert chat.deletions == [(channel_id, BOT, link.id), (channel_id, BOT, violation.id)]
    assert chat.timeouts == []


def test_第二次_Raid_重新計時兩分鐘(enable, start_chat, raid, channel_id):
    enable("emote")
    chat = start_chat()
    raid()
    chat.now += 90
    raid()

    chat.now += 119
    chat.send(EMOTE_SPAM)
    assert chat.deletions == chat.timeouts == []

    chat.now += 2
    violation = chat.send(EMOTE_SPAM)
    assert chat.deletions == [(channel_id, BOT, violation.id)]
    assert chat.timeouts == []


def test_儲存零秒後被_Raid_仍會處罰(enable, start_chat, raid, host, channel_id):
    enable("emote")
    before = penalty_settings(host)
    response = save(host, "moderation/settings", before, {"raid_pause_seconds": 0})
    assert response.is_success, response.text
    assert penalty_settings(host)["raid_pause_seconds"] == 0

    chat = start_chat()
    raid()
    violation = chat.send(EMOTE_SPAM)
    assert chat.deletions == [(channel_id, BOT, violation.id)]
    assert chat.timeouts == []


@pytest.mark.parametrize("seconds", [-1, 601])
def test_超出零到十分鐘無法儲存(host, seconds):
    before = penalty_settings(host)
    response = save(host, "moderation/settings", before, {"raid_pause_seconds": seconds})
    assert 400 <= response.status_code < 500, response.text
    assert penalty_settings(host) == before


def test_儲存十分鐘後依新時間暫停且修改紀錄記下前後值(host, enable, start_chat, raid, channel_id):
    enable("emote")
    before = penalty_settings(host)
    assert before["raid_pause_seconds"] == 120
    response = save(host, "moderation/settings", before, {"raid_pause_seconds": 600})
    assert response.is_success, response.text
    assert penalty_settings(host)["raid_pause_seconds"] == 600
    assert_change_recorded(host, {"raid_pause_seconds": 120}, {"raid_pause_seconds": 600})

    chat = start_chat()
    raid()
    chat.now += 599
    chat.send(EMOTE_SPAM)
    assert chat.deletions == chat.timeouts == []

    chat.now += 2
    violation = chat.send(EMOTE_SPAM)
    assert chat.deletions == [(channel_id, BOT, violation.id)]
    assert chat.timeouts == []
