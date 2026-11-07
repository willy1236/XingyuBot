"""突襲、訂閱、續訂、點數兌換、預測結果、私訊：Discord 端 handler 的輸出要跟拆開前逐字相同。

期望值是把拆開前 twitch_chatbot 的字串組法直接寫進測試；直接呼叫 handler，不需要 Redis。
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from starDiscord.cmds import twitch_notify
from starDiscord.cmds.twitch_notify import ChannelMissing, NotConfigured, TwitchNotify
from starlib import Jsondb
from starlib.messaging import Delivery
from starlib.messaging.events import registry
from starlib.messaging.events.twitch_activity import (
    TwitchPredictionResultEvent,
    TwitchRaidEvent,
    TwitchRedemptionEvent,
    TwitchSubscribeEvent,
    TwitchSubscriptionMessageEvent,
    TwitchWhisperEvent,
)

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
    return TwitchRaidEvent(occurred_at=NOW, to_broadcaster_id=TWITCH_ID, to_broadcaster_name="主播", from_broadcaster_name="突襲者", viewers=42)


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
    fields = dict(occurred_at=NOW, broadcaster_id=TWITCH_ID, user_name="兌換者", user_login="redeemer", reward_title="喝水", user_input=None)
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
    [(None, "兌換者(redeemer) 兌換了 喝水!"), ("", "兌換者(redeemer) 兌換了 喝水!"), ("謝謝", "兌換者(redeemer) 兌換了 喝水! (謝謝)")],
)
def test_redemption_text(cog, action_channel, user_input, expected):
    run(cog.on_redemption(redemption(user_input=user_input), DELIVERY))
    action_channel.send.assert_awaited_once_with(expected)


@pytest.mark.parametrize("result", [NotConfigured(), ChannelMissing()])
@pytest.mark.parametrize(
    ("handler", "make_event"),
    [("on_raid", raid), ("on_subscribe", subscribe), ("on_subscription_message", sub_message), ("on_redemption", redemption)],
)
def test_no_action_channel_sends_nothing(cog, monkeypatch, result, handler, make_event):
    monkeypatch.setattr(twitch_notify, "resolve_action_channel", lambda bot, twitch_id: result)
    cog.bot.get_channel.side_effect = AssertionError("沒有通知頻道時不該碰預設頻道")
    run(getattr(cog, handler)(make_event(), DELIVERY))


def test_resolve_uses_broadcaster_id_of_each_event(cog, monkeypatch):
    seen = []
    channel = make_channel()
    monkeypatch.setattr(twitch_notify, "resolve_action_channel", lambda bot, twitch_id: seen.append(twitch_id) or channel)
    for handler, event in [(cog.on_raid, raid()), (cog.on_subscribe, subscribe()), (cog.on_subscription_message, sub_message()), (cog.on_redemption, redemption())]:
        run(handler(event, DELIVERY))
    assert seen == [TWITCH_ID] * 4


# ---- 預設頻道的兩種事件：embed 相同 ----


def test_prediction_result_embed_to_default_channel(cog, default_channel):
    event = TwitchPredictionResultEvent(occurred_at=NOW, broadcaster_name="主播", title="會贏嗎", outcome_title="會", users=5)
    run(cog.on_prediction_result(event, DELIVERY))
    cog.bot.get_channel.assert_called_once_with(566533708371329026)
    embed = default_channel.send.await_args.kwargs["embed"]
    assert embed.author.name == "主播"
    assert embed.description == "會贏嗎\n會 獲勝！5個人成功預測"
    assert "content" not in default_channel.send.await_args.kwargs


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


def test_cog_subscribes_and_unsubscribes_all_six_events(monkeypatch):
    bus = MagicMock()
    monkeypatch.setattr(twitch_notify, "get_bus", lambda: bus)
    cog = TwitchNotify(MagicMock())
    subscribed = {call.args[0] for call in bus.subscribe.call_args_list}
    assert {TwitchRaidEvent, TwitchSubscribeEvent, TwitchSubscriptionMessageEvent, TwitchRedemptionEvent, TwitchPredictionResultEvent, TwitchWhisperEvent} <= subscribed
    cog.cog_unload()
    assert subscribed == {call.args[0] for call in bus.unsubscribe.call_args_list}
