"""C-03：依聊天室事件及後台 API 驗證過濾器。"""

import pytest

from starlib.database import TwitchModerationFilter
from tests.dashboard.test_channel_moderation import (
    BOT,
    EDITABLE,
    LINK,
    channel_id,  # noqa: F401 (fixture)
    enforcement,
    host,  # noqa: F401 (fixture)
    put_filter,
    settings,
    start_chat,  # noqa: F401 (fixture)
)

CAPS = "HELLO WORLD"
LINK_AND_CAPS = "THIS MESSAGE HAS LOTS OF LOUD UPPERCASE LETTERS https://abc.com"
PARAMETERS = {
    "link": (0, 1),
    "blocked_word": (0, 1),
    "caps": (2, 0),
    "emote": (1, 0),
    "symbol": (1, 0),
    "repetition": (1, 0),
    "length": (1, 0),
    "duplicate": (2, 0),
}


def fields(client, kind):
    (row,) = (row for row in settings(client)["filters"] if row["kind"] == kind)
    return {key: row[key] for key in EDITABLE}


@pytest.fixture
def enable(host, repo, channel_id):
    def seed(kind, *, words=None):
        # 直接以任務卡既有的資料形狀備妥設定，讓執法案例可獨立於 PUT 驗證。
        params = fields(host, kind)["params"]
        if words is not None:
            lists = [key for key, value in params.items() if isinstance(value, list)]
            assert len(lists) == 1, f"{kind} 應有一個可設定的禁字清單，實得 {params}"
            params = {**params, lists[0]: words}
        repo.add(
            TwitchModerationFilter(
                twitch_id=int(channel_id), kind=kind, enabled=True, exempt_level="vip", params=params, silent=True
            )
        )

    return seed


@pytest.mark.parametrize(
    ("word", "message"),
    [
        ("f*ck", "please don't say fuck"),
        ("test", "We are Testing now"),
        ("禁字", "這句話中間含有禁字所以違規"),
    ],
)
def test_禁字支援萬用字元與中英文子字串(enable, start_chat, channel_id, word, message):
    enable("blocked_word", words=[word])
    chat = start_chat()
    chat.send("一則正常的訊息")
    blocked = chat.send(message)

    assert chat.deletions == [(channel_id, BOT, blocked.id)]


@pytest.mark.parametrize(
    ("kind", "allowed", "blocked"),
    [
        ("caps", ["Hello World From TWITCH", "這則中文訊息夾了ABC"], CAPS),
        ("symbol", ["!?#$%&*", "中文，測試。「好！」（真的？）～…—"], "!?#$%&*@"),
        ("repetition", ["今天的天氣適合到公園走走", "哈" * 9], "哈" * 10),
        ("length", ["字" * 299], "字" * 300),
    ],
)
def test_以預設門檻攔截違規訊息(enable, start_chat, channel_id, kind, allowed, blocked):
    enable(kind)
    chat = start_chat()
    for message in allowed:
        chat.send(message)
    violation = chat.send(blocked)

    assert chat.deletions == [(channel_id, BOT, violation.id)]
    assert chat.timeouts == []


def test_合計_Twitch_表情與_emoji_達門檻就刪除(enable, start_chat, channel_id):
    enable("emote")
    chat = start_chat()
    emotes = {"25": [{"start_position": "0", "end_position": "4"}, {"start_position": "6", "end_position": "10"}]}
    chat.send("Kappa Kappa", emotes=emotes)
    chat.send("😀🎉")
    violation = chat.send("Kappa Kappa 😀🎉", emotes=emotes)

    assert chat.deletions == [(channel_id, BOT, violation.id)]


def test_同一觀眾三十秒內第三則相同內容才觸發重複過濾(enable, start_chat, channel_id):
    enable("duplicate")
    chat = start_chat()
    chat.send("Hello")
    chat.now += 10
    chat.send(" hello ")
    chat.send("Hello", uid="2000000970", login="bob")
    chat.now += 19
    violation = chat.send("HELLO")

    assert chat.deletions == [(channel_id, BOT, violation.id)]
    assert chat.timeouts == []


@pytest.mark.parametrize(
    ("winner", "first", "loser", "last"),
    [
        ("link", LINK, "caps", CAPS),
        ("caps", CAPS, "link", LINK),
    ],
)
def test_同時觸犯兩種只執行較重處罰且未選中的過濾器不累計(
    enable, start_chat, repo, channel_id, winner, first, loser, last
):
    enable("link")
    enable("caps")
    chat = start_chat()
    initial = chat.send(first)
    both = chat.send(LINK_AND_CAPS)
    final = chat.send(last)

    assert chat.deletions == [(channel_id, BOT, initial.id), (channel_id, BOT, final.id)]
    assert [timeout[-1] for timeout in chat.timeouts] == [600]
    assert [(row["message"], row["filter"], row["strike"], row["action"]) for row in enforcement(repo, channel_id)] == [
        (initial.text, winner, 1, "delete"),
        (both.text, winner, 2, "timeout"),
        (final.text, loser, 1, "delete"),
    ]


def test_連結先被處罰後大寫初犯仍套用第一段(enable, start_chat, repo, channel_id):
    enable("link")
    enable("caps")
    chat = start_chat()
    link = chat.send(LINK)
    chat.now += 60
    caps = chat.send(CAPS)

    assert chat.deletions == [(channel_id, BOT, link.id), (channel_id, BOT, caps.id)]
    assert chat.timeouts == []
    assert [(row["filter"], row["strike"]) for row in enforcement(repo, channel_id)] == [("link", 1), ("caps", 1)]


def test_mod_放行連結期間大寫仍會被刪除(enable, start_chat, channel_id):
    enable("link")
    enable("caps")
    chat = start_chat()
    chat.invoke("permit", "alice")
    chat.now += 1
    chat.send(LINK)
    violation = chat.send(CAPS)

    assert chat.deletions == [(channel_id, BOT, violation.id)]
    assert chat.timeouts == []


@pytest.mark.parametrize(("kind", "counts"), PARAMETERS.items())
def test_後台可個別開關並儲存各種過濾器的設定(host, kind, counts):
    before = settings(host)["filters"]
    original = fields(host, kind)
    params = original["params"]
    numbers = {key: value for key, value in params.items() if type(value) in (int, float)}
    lists = {key: value for key, value in params.items() if isinstance(value, list)}

    response = put_filter(host, {"enabled": True}, kind=kind, original=original)
    assert response.is_success, response.text
    assert (len(numbers), len(lists)) == counts, params
    if lists:
        changed = {**params, **{key: ["example.com" if kind == "link" else "f*ck"] for key in lists}}
        response = put_filter(host, {"params": changed}, kind=kind, original=fields(host, kind))
        assert response.is_success, response.text
        assert fields(host, kind)["params"] == changed
    for key, value in numbers.items():
        current = fields(host, kind)
        # 只要求門檻可調，卡片沒有指定預設值在範圍的哪一端。
        step = 0.01 if 0 < value < 1 else 1
        changed = {**current["params"], key: round(value + step, 2)}
        response = put_filter(host, {"params": changed}, kind=kind, original=current)
        if not response.is_success:
            changed[key] = round(value - step, 2)
            response = put_filter(host, {"params": changed}, kind=kind, original=current)
        assert response.is_success, (key, response.text)
        assert fields(host, kind)["params"] == changed
    assert fields(host, kind)["enabled"] is True
    response = put_filter(host, {"enabled": False}, kind=kind, original=fields(host, kind))
    assert response.is_success, response.text
    assert fields(host, kind)["enabled"] is False
    assert [row for row in settings(host)["filters"] if row["kind"] != kind] == [
        row for row in before if row["kind"] != kind
    ]


@pytest.mark.parametrize(("kind", "count"), [(kind, num) for kind, (num, _) in PARAMETERS.items() if num])
def test_後台拒絕超出範圍的每個門檻且保留原值(host, kind, count):
    original = fields(host, kind)
    params = original["params"]
    numeric_keys = [key for key, value in params.items() if type(value) in (int, float)]
    assert len(numeric_keys) == count, params
    for key in numeric_keys:
        response = put_filter(host, {"params": {**params, key: -1}}, kind=kind, original=original)
        assert 400 <= response.status_code < 500, (key, response.text)
        assert fields(host, kind) == original
