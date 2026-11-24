"""C-04：透過後台 API 與聊天室事件驗收處罰設定。"""

import pytest

from starlib.database import TwitchModerationSetting
from tests.dashboard.test_channel_moderation import (
    ALICE,
    BOT,
    EDITABLE,
    channel_id,  # noqa: F401 (fixture)
    configure,  # noqa: F401 (fixture)
    host,  # noqa: F401 (fixture)
    settings,
    start_chat,  # noqa: F401 (fixture)
)

DELETE = {"action": "delete", "duration": None}
BAN = {"action": "ban", "duration": None}
THREE_STAGES = [DELETE, {"action": "timeout", "duration": 10}, {"action": "timeout", "duration": 120}]
SETTINGS_FIELDS = ("stages", "strike_reset_minutes", "permit_seconds")


def channel_fields(client):
    current = settings(client)["settings"]
    return {key: current[key] for key in SETTINGS_FIELDS}


def filter_fields(client, kind):
    (row,) = (row for row in settings(client)["filters"] if row["kind"] == kind)
    return {key: row[key] for key in (*EDITABLE, "stages")}


def save(client, endpoint, original, changes):
    return client.put(endpoint, json={"original": original, "values": {**original, **changes}})


@pytest.fixture
def seed_penalties(host, repo, channel_id):
    def seed(**changes):
        current = settings(host)["settings"]
        del current["updated_at"]
        repo.add(TwitchModerationSetting(twitch_id=int(channel_id), **{**current, **changes}))

    return seed


def test_禁字首次直接封禁且連結仍使用頻道預設(host, configure, start_chat, channel_id):
    configure()
    before = filter_fields(host, "blocked_word")
    changes = {"enabled": True, "params": {**before["params"], "words": ["禁字"]}, "stages": [BAN]}
    response = save(host, "moderation/filters/blocked_word", before, changes)
    assert response.is_success, response.text
    assert filter_fields(host, "blocked_word")["stages"] == [BAN]

    chat = start_chat()
    chat.send("這則訊息包含禁字")
    link = chat.send(uid="2000000965", login="bob")

    assert chat.timeouts == [(channel_id, BOT, ALICE, None)]
    assert chat.deletions == [(channel_id, BOT, link.id)]


def test_第三次起一律使用第三段(seed_penalties, configure, start_chat, channel_id):
    seed_penalties(stages=THREE_STAGES)
    configure()
    chat = start_chat()
    first = chat.send()
    for _ in range(4):
        chat.now += 11
        chat.send()

    assert chat.deletions == [(channel_id, BOT, first.id)]
    assert chat.timeouts == [(channel_id, BOT, ALICE, seconds) for seconds in (10, 120, 120, 120)]


@pytest.mark.parametrize(
    "changes",
    [
        {"stages": []},
        {"stages": [DELETE] * 6},
        {"stages": [{"action": "timeout", "duration": 14 * 24 * 60 * 60 + 1}]},
        {"strike_reset_minutes": 0},
        {"strike_reset_minutes": 24 * 60 + 1},
    ],
    ids=["zero-stages", "six-stages", "timeout-over-two-weeks", "reset-below-minimum", "reset-over-one-day"],
)
def test_無法儲存超出範圍的頻道處罰設定(host, changes):
    before = channel_fields(host)
    response = save(host, "moderation/settings", before, changes)
    assert response.status_code in (400, 422), response.text
    assert channel_fields(host) == before


@pytest.mark.parametrize(
    "stages",
    [[], [DELETE] * 6, [{"action": "timeout", "duration": 14 * 24 * 60 * 60 + 1}]],
    ids=["zero-stages", "six-stages", "timeout-over-two-weeks"],
)
def test_無法儲存超出範圍的個別過濾器階段(host, stages):
    before = filter_fields(host, "blocked_word")
    response = save(host, "moderation/filters/blocked_word", before, {"stages": stages})
    assert response.status_code in (400, 422), response.text
    assert filter_fields(host, "blocked_word") == before


def test_距上次犯規超過五分鐘回到第一段(seed_penalties, configure, start_chat, channel_id):
    seed_penalties(strike_reset_minutes=5)
    configure()
    chat = start_chat()
    first = chat.send()
    chat.now += 299
    chat.send()
    chat.now += 301
    after_reset = chat.send()

    assert chat.deletions == [(channel_id, BOT, message.id) for message in (first, after_reset)]
    assert chat.timeouts == [(channel_id, BOT, ALICE, 600)]


def test_放行一百二十秒後才恢復連結過濾(seed_penalties, configure, start_chat, channel_id):
    seed_penalties(permit_seconds=120)
    configure()
    chat = start_chat()
    chat.invoke("permit", "alice")
    chat.now += 119
    chat.send()
    assert chat.deletions == chat.timeouts == []

    chat.now += 2
    blocked = chat.send()
    assert chat.deletions == [(channel_id, BOT, blocked.id)]
    assert chat.timeouts == []


def assert_change_recorded(client, before, after):
    result = client.get("audit")
    assert result.is_success, result.text
    entries = result.json()["entries"]
    assert any(
        entry["source"] == "dashboard"
        and all((entry["before"] or {}).get(key) == value for key, value in before.items())
        and all((entry["after"] or {}).get(key) == value for key, value in after.items())
        for entry in entries
    ), entries


def test_頻道階段與時間可儲存且修改紀錄保留前後值(host):
    before = channel_fields(host)
    after = {"stages": THREE_STAGES, "strike_reset_minutes": 5, "permit_seconds": 120}
    response = save(host, "moderation/settings", before, after)
    assert response.is_success, response.text
    assert channel_fields(host) == after
    assert_change_recorded(host, before, after)


def test_個別過濾器階段的修改紀錄保留前後值(host):
    endpoint = "moderation/filters/blocked_word"
    before = filter_fields(host, "blocked_word")
    response = save(host, endpoint, before, {"stages": [DELETE]})
    assert response.is_success, response.text
    before = filter_fields(host, "blocked_word")
    assert before["stages"] == [DELETE]

    response = save(host, endpoint, before, {"stages": [BAN]})
    assert response.is_success, response.text
    assert filter_fields(host, "blocked_word")["stages"] == [BAN]
    assert_change_recorded(host, {"stages": [DELETE]}, {"stages": [BAN]})
