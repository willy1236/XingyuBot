"""突襲、訂閱、續訂、點數兌換、預測結果、私訊：Discord 端 handler 的輸出要跟拆開前逐字相同。

期望值是把拆開前 twitch_chatbot 的字串組法直接寫進測試；直接呼叫 handler，不需要 Redis。
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from starDiscord.cmds import twitch_notify
from starDiscord.cmds.twitch_notify import ChannelMissing, NotConfigured, TwitchNotify
from starlib import Jsondb, twitch_event_responses
from starlib.messaging import Delivery
from starlib.messaging.events import registry
from starlib.messaging.events.twitch_activity import (
    TwitchPredictionResultEvent,
    TwitchRaidEvent,
    TwitchRedemptionEvent,
    TwitchSubscribeEvent,
    TwitchSubscriptionGiftEvent,
    TwitchSubscriptionMessageEvent,
    TwitchWhisperEvent,
)
from starlib.twitch_event_responses import default_response

NOW = datetime.now(UTC)
DELIVERY = Delivery(redelivered=False)
TWITCH_ID = "900000000000000003"


@pytest.fixture
def cog(monkeypatch) -> TwitchNotify:
    monkeypatch.setattr(twitch_notify, "get_bus", lambda: MagicMock())
    return TwitchNotify(MagicMock())


def make_channel() -> MagicMock:
    channel = MagicMock()
    channel.send = AsyncMock()
    return channel


@pytest.fixture
def action_channel(monkeypatch) -> MagicMock:
    channel = make_channel()
    monkeypatch.setattr(twitch_notify, "resolve_action_channel", lambda bot, twitch_id: channel)
    return channel


@pytest.fixture
def default_channel(cog) -> MagicMock:
    channel = make_channel()
    cog.bot.get_channel.return_value = channel
    return channel


def run(coro):
    return asyncio.run(coro)


def raid():
    return TwitchRaidEvent(
        occurred_at=NOW,
        to_broadcaster_id=TWITCH_ID,
        to_broadcaster_name="主播",
        from_broadcaster_name="突襲者",
        viewers=42,
    )


def prediction_result():
    return TwitchPredictionResultEvent(
        occurred_at=NOW, broadcaster_id=TWITCH_ID, broadcaster_name="主播", title="會贏嗎", outcome_title="會", users=5
    )


def gift(**overrides):
    data = dict(occurred_at=NOW, broadcaster_id=TWITCH_ID, user_name="贈送者", total=5, tier="2000")
    return TwitchSubscriptionGiftEvent(**{**data, **overrides})


def subscribe():
    return TwitchSubscribeEvent(occurred_at=NOW, broadcaster_id=TWITCH_ID, user_name="訂閱者")


def sub_message(**overrides):
    fields = dict(
        occurred_at=NOW,
        broadcaster_id=TWITCH_ID,
        broadcaster_name="主播",
        user_name="訂閱者",
        tier="2000",
        duration_months=3,
        cumulative_months=7,
        message="加油",
    )
    return TwitchSubscriptionMessageEvent(**{**fields, **overrides})


def redemption(**overrides):
    fields = dict(
        occurred_at=NOW,
        broadcaster_id=TWITCH_ID,
        user_name="兌換者",
        user_login="redeemer",
        reward_title="喝水",
        user_input=None,
    )
    return TwitchRedemptionEvent(**{**fields, **overrides})


# ---- 通知頻道的四種事件：逐字相同 ----


def test_raid_text(cog, action_channel):
    run(cog.on_raid(raid(), DELIVERY))
    action_channel.send.assert_awaited_once_with("突襲者 帶了 42 位觀眾降落在 主播 的頻道!")


def test_subscribe_text(cog, action_channel):
    run(cog.on_subscribe(subscribe(), DELIVERY))
    action_channel.send.assert_awaited_once_with("感謝 訂閱者 的訂閱！")


def test_subscription_message_sends_two_messages_in_order(cog, action_channel):
    run(cog.on_subscription_message(sub_message(), DELIVERY))
    assert [c.args for c in action_channel.send.await_args_list] == [
        ("感謝 訂閱者 的訂閱！\n累積訂閱7個月！",),
        ("訂閱者 在 主播 的3個月 層級2訂閱\n他已經訂閱 7 個月了\n訊息：加油",),
    ]


def test_subscription_message_without_message_text(cog, action_channel):
    run(cog.on_subscription_message(sub_message(message=None), DELIVERY))
    assert action_channel.send.await_args_list[1].args == ("訂閱者 在 主播 的3個月 層級2訂閱\n他已經訂閱 7 個月了",)


def test_subscription_message_omits_cumulative_sentences_when_none(cog, action_channel):
    """使用者決定：累積月數為 None 時省略含它的句子（偏離卡上逐字相同），不印 None。"""
    run(cog.on_subscription_message(sub_message(cumulative_months=None), DELIVERY))
    sent = [c.args[0] for c in action_channel.send.await_args_list]
    assert sent == ["感謝 訂閱者 的訂閱！", "訂閱者 在 主播 的3個月 層級2訂閱\n訊息：加油"]
    assert all("None" not in text for text in sent)


@pytest.mark.parametrize(
    ("user_input", "expected"),
    [
        (None, "兌換者(redeemer) 兌換了 喝水!"),
        ("", "兌換者(redeemer) 兌換了 喝水!"),
        ("謝謝", "兌換者(redeemer) 兌換了 喝水! (謝謝)"),
    ],
)
def test_redemption_text(cog, action_channel, user_input, expected):
    run(cog.on_redemption(redemption(user_input=user_input), DELIVERY))
    action_channel.send.assert_awaited_once_with(expected)


@pytest.mark.parametrize("result", [NotConfigured(), ChannelMissing()])
@pytest.mark.parametrize(
    ("handler", "make_event"),
    [
        ("on_raid", raid),
        ("on_subscribe", subscribe),
        ("on_subscription_message", sub_message),
        ("on_redemption", redemption),
        ("on_gift", gift),
        ("on_prediction_result", prediction_result),
    ],
)
def test_no_action_channel_sends_nothing(cog, monkeypatch, result, handler, make_event):
    monkeypatch.setattr(twitch_notify, "resolve_action_channel", lambda bot, twitch_id: result)
    cog.bot.get_channel.side_effect = AssertionError("沒有通知頻道時不該碰預設頻道")
    run(getattr(cog, handler)(make_event(), DELIVERY))


def test_resolve_uses_broadcaster_id_of_each_event(cog, monkeypatch):
    seen = []
    channel = make_channel()
    monkeypatch.setattr(
        twitch_notify, "resolve_action_channel", lambda bot, twitch_id: seen.append(twitch_id) or channel
    )
    for handler, event in [
        (cog.on_raid, raid()),
        (cog.on_subscribe, subscribe()),
        (cog.on_subscription_message, sub_message()),
        (cog.on_redemption, redemption()),
        (cog.on_gift, gift()),
        (cog.on_prediction_result, prediction_result()),
    ]:
        run(handler(event, DELIVERY))
    assert seen == [TWITCH_ID] * 6


def test_prediction_result_embed_to_action_channel(cog, action_channel):
    run(cog.on_prediction_result(prediction_result(), DELIVERY))
    embed = action_channel.send.await_args.kwargs["embed"]
    assert embed.author.name == "主播"
    assert embed.description == "會贏嗎\n會 獲勝！5個人成功預測"
    assert "content" not in action_channel.send.await_args.kwargs


def test_gift_text(cog, action_channel):
    run(cog.on_gift(gift(), DELIVERY))
    action_channel.send.assert_awaited_once_with("感謝 贈送者 贈送了 5 份層級2訂閱！")


def test_anonymous_gift_text(cog, action_channel):
    run(cog.on_gift(gift(user_name=None), DELIVERY))
    action_channel.send.assert_awaited_once_with("感謝 匿名 贈送了 5 份層級2訂閱！")


# ---- 預設頻道：只剩私訊 ----


def test_whisper_embed_to_default_channel(cog, default_channel):
    run(cog.on_whisper(TwitchWhisperEvent(occurred_at=NOW, user_name="路人", message="哈囉"), DELIVERY))
    cog.bot.get_channel.assert_called_once_with(566533708371329026)
    embed = default_channel.send.await_args.kwargs["embed"]
    assert embed.author.name == "路人"
    assert embed.author.icon_url == Jsondb.get_picture("twitch_001")
    assert embed.description == "哈囉"


def test_default_channel_missing_is_silent(cog):
    cog.bot.get_channel.return_value = None
    run(cog.on_whisper(TwitchWhisperEvent(occurred_at=NOW, user_name="路人", message="哈囉"), DELIVERY))  # 不拋例外


# ---- 事件 model ----


@pytest.mark.parametrize(
    ("cls", "event_type", "ttl"),
    [
        (TwitchRaidEvent, "twitch.raid", timedelta(minutes=10)),
        (TwitchSubscribeEvent, "twitch.subscribe", timedelta(hours=1)),
        (TwitchSubscriptionMessageEvent, "twitch.subscription_message", timedelta(hours=1)),
        (TwitchSubscriptionGiftEvent, "twitch.subscription_gift", timedelta(hours=1)),
        (TwitchRedemptionEvent, "twitch.redemption", timedelta(hours=1)),
        (TwitchPredictionResultEvent, "twitch.prediction_result", timedelta(hours=1)),
        (TwitchWhisperEvent, "twitch.whisper", timedelta(hours=1)),
    ],
)
def test_event_contract(cls, event_type, ttl):
    assert cls.event_type == event_type
    assert cls.ttl == ttl
    assert cls.receivers == ("discord",)
    assert registry[event_type] is cls


def test_cog_subscribes_and_unsubscribes_all_events(monkeypatch):
    bus = MagicMock()
    monkeypatch.setattr(twitch_notify, "get_bus", lambda: bus)
    cog = TwitchNotify(MagicMock())
    subscribed = {call.args[0] for call in bus.subscribe.call_args_list}
    assert {
        TwitchRaidEvent,
        TwitchSubscribeEvent,
        TwitchSubscriptionMessageEvent,
        TwitchSubscriptionGiftEvent,
        TwitchRedemptionEvent,
        TwitchPredictionResultEvent,
        TwitchWhisperEvent,
    } <= subscribed
    cog.cog_unload()
    assert subscribed == {call.args[0] for call in bus.unsubscribe.call_args_list}


# ---- Twitch 端：handler 發送的事件與聊天室行為 ----


@pytest.fixture
def chatbot(monkeypatch):
    """載入 twitch_bot.events；替換 bus 與 chat，記錄呼叫順序。"""
    from starlib import sclient

    monkeypatch.setattr(type(sclient.sqldb), "get_bot_join_channel_all", lambda self: {})
    from starServer.twitch_bot import events as module
    from starServer.twitch_bot import state

    calls: list[str] = []
    bus = MagicMock()
    bus.publish.side_effect = lambda event: calls.append("publish")
    fake_chat = MagicMock()
    fake_chat.send_message = AsyncMock(side_effect=lambda *a, **k: calls.append("chat"))
    monkeypatch.setattr(module, "get_bus", lambda: bus)
    monkeypatch.setattr(state, "chat", fake_chat, raising=False)
    # 事件回應全部開啟並使用預設文字，不查資料庫（沒有設定時預設是關閉）
    monkeypatch.setattr(
        module,
        "_load",
        lambda twitch_id: {k: replace(default_response(k), enabled=True) for k in twitch_event_responses.KINDS},
    )
    monkeypatch.setattr(module, "_responses", {})
    module.test_calls = calls
    module.test_bus = bus
    module.test_chat = fake_chat
    return module


def eventsub_event(**data):
    return SimpleNamespace(metadata=SimpleNamespace(message_timestamp=NOW), event=SimpleNamespace(**data))


def published(chatbot):
    return [call.args[0] for call in chatbot.test_bus.publish.call_args_list]


def raid_payload():
    return eventsub_event(
        from_broadcaster_user_name="突襲者",
        to_broadcaster_user_id=TWITCH_ID,
        to_broadcaster_user_login="host",
        to_broadcaster_user_name="主播",
        viewers=42,
    )


def test_raid_chat_then_publish(chatbot):
    run(chatbot.on_channel_raid(raid_payload()))
    assert chatbot.test_calls == ["chat", "publish"]
    chatbot.test_chat.send_message.assert_awaited_once_with("host", "突襲者 帶了 42 位觀眾降落在 主播 的頻道！")
    assert published(chatbot) == [raid()]  # 與 Discord 端測試用的事件同欄位，occurred_at 取 message_timestamp


def test_raid_responds_without_forward_config(chatbot, monkeypatch):
    monkeypatch.setattr(chatbot.state, "join_channels", {})  # 沒設定轉發 Discord 的頻道
    run(chatbot.on_channel_raid(raid_payload()))
    chatbot.test_chat.send_message.assert_awaited_once()
    assert len(published(chatbot)) == 1


def test_raid_response_disabled_skips_chat_but_still_publishes(chatbot, monkeypatch):
    disabled = {k: replace(default_response(k), enabled=True) for k in twitch_event_responses.KINDS}
    disabled["raid"] = default_response("raid")
    monkeypatch.setattr(chatbot, "_load", lambda twitch_id: disabled)
    run(chatbot.on_channel_raid(raid_payload()))
    chatbot.test_chat.send_message.assert_not_awaited()
    assert len(published(chatbot)) == 1


def test_gift_subscribe_is_not_published_nor_answered(chatbot):
    payload = eventsub_event(
        broadcaster_user_id=TWITCH_ID,
        broadcaster_user_login="host",
        broadcaster_user_name="主播",
        user_name="訂閱者",
        tier="1000",
        is_gift=True,
    )
    run(chatbot.on_channel_subscribe(payload))
    chatbot.test_bus.publish.assert_not_called()
    chatbot.test_chat.send_message.assert_not_awaited()


def test_subscribe_answered_then_published_regardless_of_action_channel(chatbot, monkeypatch):
    monkeypatch.setattr(chatbot.state, "join_channels", {})
    payload = eventsub_event(
        broadcaster_user_id=TWITCH_ID,
        broadcaster_user_login="host",
        broadcaster_user_name="主播",
        user_name="訂閱者",
        tier="1000",
        is_gift=False,
    )
    run(chatbot.on_channel_subscribe(payload))
    assert chatbot.test_calls == ["chat", "publish"]
    chatbot.test_chat.send_message.assert_awaited_once_with("host", "感謝 訂閱者 的訂閱！")
    assert published(chatbot) == [subscribe()]


def sub_message_payload(**overrides):
    data = dict(
        broadcaster_user_id=TWITCH_ID,
        broadcaster_user_login="host",
        broadcaster_user_name="主播",
        user_name="訂閱者",
        tier="2000",
        duration_months=3,
        cumulative_months=7,
        message=SimpleNamespace(text="加油"),
    )
    return eventsub_event(**{**data, **overrides})


def test_subscription_message_chat_then_publish(chatbot):
    run(chatbot.on_channel_subscription_message(sub_message_payload()))
    assert chatbot.test_calls == ["chat", "publish"]
    chatbot.test_chat.send_message.assert_awaited_once_with("host", "感謝 訂閱者 的訂閱！累積訂閱 7 個月！")
    assert published(chatbot) == [sub_message()]


def test_subscription_message_without_cumulative_or_message(chatbot):
    run(chatbot.on_channel_subscription_message(sub_message_payload(cumulative_months=None, message=None)))
    (sent,) = published(chatbot)
    assert sent.cumulative_months is None
    assert sent.message is None
    # 沒有累積月數時用這次的訂閱月數，不會送出字面的 {months}
    chatbot.test_chat.send_message.assert_awaited_once_with("host", "感謝 訂閱者 的訂閱！累積訂閱 3 個月！")


def test_gift_subscription_answered_then_published(chatbot):
    payload = eventsub_event(
        broadcaster_user_id=TWITCH_ID,
        broadcaster_user_login="host",
        broadcaster_user_name="主播",
        user_name="贈送者",
        tier="1000",
        total=5,
        is_anonymous=False,
    )
    run(chatbot.on_channel_subscription_gift(payload))
    chatbot.test_chat.send_message.assert_awaited_once_with("host", "感謝 贈送者 送出 5 份訂閱！")
    assert published(chatbot) == [gift(user_name="贈送者", total=5, tier="1000")]


def test_anonymous_gift_subscription_is_answered_as_anonymous(chatbot):
    payload = eventsub_event(
        broadcaster_user_id=TWITCH_ID,
        broadcaster_user_login="host",
        broadcaster_user_name="主播",
        user_name="ANONYMOUS",
        tier="1000",
        total=5,
        is_anonymous=True,
    )
    run(chatbot.on_channel_subscription_gift(payload))
    chatbot.test_chat.send_message.assert_awaited_once_with("host", "感謝 匿名 送出 5 份訂閱！")
    assert published(chatbot) == [gift(user_name=None, total=5, tier="1000")]


def test_redemption_published_regardless_of_action_channel(chatbot, monkeypatch):
    monkeypatch.setattr(chatbot.state, "join_channels", {})
    payload = eventsub_event(
        broadcaster_user_id=TWITCH_ID,
        user_name="兌換者",
        user_login="redeemer",
        reward=SimpleNamespace(title="喝水"),
        user_input="謝謝",
    )
    run(chatbot.on_channel_points_custom_reward_redemption_add(payload))
    assert published(chatbot) == [redemption(user_input="謝謝")]


def prediction_payload(status="resolved"):
    outcomes = [
        SimpleNamespace(id="a", title="不會", color="PINK", users=2),
        SimpleNamespace(id="b", title="會", color="BLUE", users=5),
    ]
    return eventsub_event(
        broadcaster_user_id=TWITCH_ID,
        broadcaster_user_name="主播",
        title="會贏嗎",
        status=status,
        winning_outcome_id="b",
        outcomes=outcomes,
    )


def test_prediction_resolved_publishes_winner(chatbot):
    run(chatbot.on_channel_prediction_end(prediction_payload()))
    assert published(chatbot) == [prediction_result()]


def test_prediction_canceled_publishes_nothing(chatbot):
    run(chatbot.on_channel_prediction_end(prediction_payload("canceled")))
    chatbot.test_bus.publish.assert_not_called()


def test_whisper_publishes_with_receive_time(chatbot):
    before = datetime.now(UTC)
    run(chatbot.on_whisper(SimpleNamespace(user=SimpleNamespace(name="路人"), message="哈囉")))
    (sent,) = published(chatbot)
    assert (sent.user_name, sent.message) == ("路人", "哈囉")
    assert before <= sent.occurred_at <= datetime.now(UTC)


def test_poll_and_prediction_begin_only_log(chatbot):
    poll = eventsub_event(broadcaster_user_name="主播", title="投票", choices=[])
    prediction = eventsub_event(
        broadcaster_user_name="主播", title="預測", outcomes=[SimpleNamespace(title="甲"), SimpleNamespace(title="乙")]
    )
    run(chatbot.on_channel_poll_begin(poll))
    run(chatbot.on_channel_prediction_begin(prediction))
    chatbot.test_bus.publish.assert_not_called()


def test_publish_is_not_blocked_by_unreachable_redis(chatbot, monkeypatch):
    """真正的 bus.publish 在 Redis 沒開時也立即返回、不拋例外（T-01 介面），handler 不會被拖慢。"""
    import time

    from starlib.messaging import MessageBus

    bus = MessageBus(f"test-activity-{id(chatbot)}")
    try:
        monkeypatch.setattr(chatbot, "get_bus", lambda: bus)
        started = time.monotonic()
        run(chatbot.on_channel_raid(raid_payload()))
        assert time.monotonic() - started < 1
    finally:
        bus.close()
