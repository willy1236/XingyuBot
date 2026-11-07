"""Twitch 開台／下播通知：搶佔與清除的 DB 行為，以及 Discord 端 handler、輪詢的行為。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import Session, select

from starlib import sqldb
from starlib.database import NotifyCommunityType
from starlib.database.postgresql.client import SQLRepository
from starlib.database.postgresql.models import CommunityCache

TWITCH_LIVE = NotifyCommunityType.TwitchLive
YOUTUBE_ID = "t04-test-community"
T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def repo():
    """交易 rollback 寫法：測試寫入的紀錄不會留在資料庫。"""
    connection = sqldb.engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield SQLRepository(sqldb.engine, session), session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


def stored(session: Session, community_id: str, type=TWITCH_LIVE) -> CommunityCache | None:
    session.expire_all()
    return session.exec(select(CommunityCache).where(CommunityCache.notify_type == type, CommunityCache.community_id == community_id)).one_or_none()


@pytest.mark.integration
def test_claim_twitch_live_wins_when_no_record(repo):
    r, session = repo
    assert r.claim_twitch_live(YOUTUBE_ID, T0) is True
    assert stored(session, YOUTUBE_ID).value == T0


@pytest.mark.integration
def test_claim_twitch_live_wins_when_record_is_null(repo):
    r, session = repo
    session.execute(CommunityCache.__table__.insert().values(notify_type=TWITCH_LIVE, community_id=YOUTUBE_ID, value=None))
    assert r.claim_twitch_live(YOUTUBE_ID, T0) is True
    assert stored(session, YOUTUBE_ID).value == T0


@pytest.mark.integration
def test_claim_community_cache_still_loses_on_null_record(repo):
    """YouTube 用的搶佔不變：空值搶不到。"""
    r, session = repo
    session.execute(CommunityCache.__table__.insert().values(notify_type=TWITCH_LIVE, community_id=YOUTUBE_ID, value=None))
    assert r.claim_community_cache(TWITCH_LIVE, YOUTUBE_ID, T0) is False
    assert stored(session, YOUTUBE_ID).value is None


@pytest.mark.integration
def test_claim_twitch_live_only_one_wins_for_same_stream(repo):
    r, _ = repo
    assert r.claim_twitch_live(YOUTUBE_ID, T0) is True
    assert r.claim_twitch_live(YOUTUBE_ID, T0) is False
    assert r.claim_twitch_live(YOUTUBE_ID, T0 - timedelta(hours=1)) is False


@pytest.mark.integration
def test_claim_twitch_live_wins_for_newer_stream_after_stale_record(repo):
    """上一次下播沒清掉紀錄，新的一次開台仍搶得到。"""
    r, session = repo
    assert r.claim_twitch_live(YOUTUBE_ID, T0) is True
    assert r.claim_twitch_live(YOUTUBE_ID, T0 + timedelta(days=1)) is True
    assert stored(session, YOUTUBE_ID).value == T0 + timedelta(days=1)


@pytest.mark.integration
def test_clear_twitch_live_clears_older_record(repo):
    r, session = repo
    r.claim_twitch_live(YOUTUBE_ID, T0)
    r.clear_twitch_live(YOUTUBE_ID, T0 + timedelta(hours=2))
    assert stored(session, YOUTUBE_ID) is None


@pytest.mark.integration
def test_clear_twitch_live_keeps_newer_record(repo):
    """下播事件晚於下一次開台處理時，不清掉新開台的紀錄。"""
    r, session = repo
    r.claim_twitch_live(YOUTUBE_ID, T0 + timedelta(hours=3))
    r.clear_twitch_live(YOUTUBE_ID, T0 + timedelta(hours=2))
    assert stored(session, YOUTUBE_ID).value == T0 + timedelta(hours=3)


@pytest.mark.integration
def test_clear_twitch_live_clears_null_record_and_ignores_other_types(repo):
    r, session = repo
    session.execute(CommunityCache.__table__.insert().values(notify_type=TWITCH_LIVE, community_id=YOUTUBE_ID, value=None))
    other = NotifyCommunityType.Youtube
    r.claim_community_cache(other, YOUTUBE_ID, T0)
    r.clear_twitch_live(YOUTUBE_ID, T0)
    assert stored(session, YOUTUBE_ID) is None
    assert stored(session, YOUTUBE_ID, other) is not None


# ---- Discord 端 handler ----

import asyncio  # noqa: E402
from unittest.mock import AsyncMock, MagicMock  # noqa: E402

from starDiscord.cmds import twitch_live_notify  # noqa: E402
from starDiscord.cmds.twitch_live_notify import TwitchLiveNotify  # noqa: E402
from starDiscord.cmds.twitch_notify import DEFAULT_TWITCH_CHANNEL, ChannelMissing, NotConfigured  # noqa: E402
from starlib.messaging import Delivery  # noqa: E402
from starlib.messaging.events.twitch_stream import TwitchStreamOfflineEvent, TwitchStreamOnlineEvent  # noqa: E402

NEW = Delivery(redelivered=False)
REDELIVERED = Delivery(redelivered=True)


def online_event(**overrides) -> TwitchStreamOnlineEvent:
    fields = dict(
        occurred_at=T0,
        broadcaster_id="900000000000000004",
        broadcaster_name="主播",
        profile_image_url="https://example.com/avatar.png",
        stream_id="1",
        user_login="streamer",
        game_id="10",
        game_name="遊戲",
        stream_type="live",
        title="標題",
        viewer_count=3,
        started_at=T0,
        language="zh",
        thumbnail_url="https://example.com/thumb-{width}x{height}.jpg",
        tag_ids=[],
        tags=["中文", "閒聊"],
        is_mature=False,
    )
    return TwitchStreamOnlineEvent(**{**fields, **overrides})


@pytest.fixture
def cog(monkeypatch):
    monkeypatch.setattr(twitch_live_notify, "get_bus", lambda: MagicMock())
    bot = MagicMock()
    bot.send_notify_communities = AsyncMock()
    return TwitchLiveNotify(bot)


@pytest.fixture
def db(monkeypatch):
    holder = MagicMock()
    holder.claim_twitch_live.return_value = True
    monkeypatch.setattr(twitch_live_notify.sclient, "sqldb", holder)
    return holder


@pytest.fixture
def sentry_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(twitch_live_notify, "capture_exception_safe", lambda *a, **k: calls.append((a, k)))
    return calls


def set_channel(monkeypatch, result):
    monkeypatch.setattr(twitch_live_notify, "resolve_action_channel", lambda bot, twitch_id: result)


def make_channel():
    channel = MagicMock()
    channel.send = AsyncMock()
    return channel


def run(coro):
    return asyncio.run(coro)


def test_online_sends_text_and_embed_with_avatar(cog, db, monkeypatch):
    channel = make_channel()
    set_channel(monkeypatch, channel)
    run(cog.on_stream_online(online_event(), NEW))
    channel.send.assert_awaited_once_with("主播 正在直播 遊戲!")
    db.claim_twitch_live.assert_called_once_with("900000000000000004", T0)
    embed, notify_type, community_id = cog.bot.send_notify_communities.await_args.args
    assert notify_type == TWITCH_LIVE and community_id == "900000000000000004"
    assert embed.author.name == "主播 開台啦！"
    assert embed.author.icon_url == "https://example.com/avatar.png"
    assert embed.title == "標題" and embed.description == "遊戲"
    assert embed.url == "https://www.twitch.tv/streamer"


def test_online_does_nothing_when_not_configured(cog, db, monkeypatch):
    set_channel(monkeypatch, NotConfigured())
    run(cog.on_stream_online(online_event(), NEW))
    db.claim_twitch_live.assert_not_called()
    cog.bot.send_notify_communities.assert_not_awaited()


def test_online_still_claims_and_notifies_when_channel_missing(cog, db, monkeypatch):
    set_channel(monkeypatch, ChannelMissing())
    run(cog.on_stream_online(online_event(), NEW))
    db.claim_twitch_live.assert_called_once()
    cog.bot.send_notify_communities.assert_awaited_once()


def test_online_send_failure_is_reported_and_still_notifies(cog, db, monkeypatch, sentry_calls):
    channel = make_channel()
    channel.send.side_effect = RuntimeError("boom")
    set_channel(monkeypatch, channel)
    run(cog.on_stream_online(online_event(), NEW))
    assert len(sentry_calls) == 1
    db.claim_twitch_live.assert_called_once()
    cog.bot.send_notify_communities.assert_awaited_once()


def test_online_lost_claim_sends_no_community_notification(cog, db, monkeypatch):
    db.claim_twitch_live.return_value = False
    channel = make_channel()
    set_channel(monkeypatch, channel)
    run(cog.on_stream_online(online_event(), NEW))
    channel.send.assert_awaited_once()
    cog.bot.send_notify_communities.assert_not_awaited()


def test_online_redelivered_notifies_even_when_claim_lost(cog, db, monkeypatch):
    """處理到一半被殺、重啟後補送：搶佔照樣呼叫（寫入紀錄），回傳值忽略，照發。"""
    db.claim_twitch_live.return_value = False
    set_channel(monkeypatch, make_channel())
    run(cog.on_stream_online(online_event(), REDELIVERED))
    db.claim_twitch_live.assert_called_once()
    cog.bot.send_notify_communities.assert_awaited_once()


def test_offline_sends_to_default_channel_then_clears_with_event_time(cog, db):
    channel = make_channel()
    cog.bot.get_channel.return_value = channel
    event = TwitchStreamOfflineEvent(occurred_at=T0 + timedelta(hours=1), broadcaster_id="900000000000000004", broadcaster_name="主播")
    run(cog.on_stream_offline(event, NEW))
    cog.bot.get_channel.assert_called_once_with(DEFAULT_TWITCH_CHANNEL)
    channel.send.assert_awaited_once_with("主播 ending stream.")
    db.clear_twitch_live.assert_called_once_with("900000000000000004", T0 + timedelta(hours=1))


def test_offline_clears_even_when_default_channel_missing(cog, db):
    cog.bot.get_channel.return_value = None
    event = TwitchStreamOfflineEvent(occurred_at=T0, broadcaster_id="1", broadcaster_name="主播")
    run(cog.on_stream_offline(event, NEW))
    db.clear_twitch_live.assert_called_once_with("1", T0)


def test_event_ttl_and_receivers():
    assert TwitchStreamOnlineEvent.ttl == timedelta(minutes=10)
    assert TwitchStreamOfflineEvent.ttl == timedelta(minutes=5)
    assert TwitchStreamOnlineEvent.receivers == TwitchStreamOfflineEvent.receivers == ("discord",)


def test_online_event_survives_json_roundtrip():
    event = online_event()
    assert TwitchStreamOnlineEvent.model_validate_json(event.model_dump_json()) == event


def test_cog_subscribes_and_unsubscribes_both_events(monkeypatch):
    bus = MagicMock()
    monkeypatch.setattr(twitch_live_notify, "get_bus", lambda: bus)
    bot = MagicMock()
    cog = TwitchLiveNotify(bot)
    subscribed = {c.args[0]: c.args[1] for c in bus.subscribe.call_args_list}
    assert subscribed == {TwitchStreamOnlineEvent: cog.on_stream_online, TwitchStreamOfflineEvent: cog.on_stream_offline}
    assert all(c.kwargs["loop"] is bot.loop for c in bus.subscribe.call_args_list)
    cog.cog_unload()
    assert {c.args for c in bus.unsubscribe.call_args_list} == {(TwitchStreamOnlineEvent, cog.on_stream_online), (TwitchStreamOfflineEvent, cog.on_stream_offline)}


# ---- 輪詢 task.twitch_live ----

from starDiscord.cmds import task as task_module  # noqa: E402


def poll_cog(monkeypatch, lives: dict, caches: dict, db, now=T0):
    cog = task_module.task(MagicMock())
    cog.bot.send_notify_communities = AsyncMock()
    db.get_community_caches.return_value = caches
    monkeypatch.setattr(task_module.sclient, "sqldb", db)
    monkeypatch.setattr(task_module, "tw_api", MagicMock(get_lives=MagicMock(side_effect=lambda ids: {i: lives.get(i) for i in ids})))
    monkeypatch.setattr(task_module.utils, "nowtz", lambda: now)
    return cog


def stream_for(started_at):
    from starlib.providers.social.models import TwitchStream

    e = online_event(started_at=started_at)
    return TwitchStream(
        id=e.stream_id, user_id=e.broadcaster_id, user_login=e.user_login, user_name=e.broadcaster_name, game_id=e.game_id,
        game_name=e.game_name, type=e.stream_type, title=e.title, viewer_count=e.viewer_count, started_at=e.started_at,
        language=e.language, thumbnail_url=e.thumbnail_url, tag_ids=e.tag_ids, tags=e.tags, is_mature=e.is_mature,
    )


def test_poll_notifies_when_claim_won_without_avatar(monkeypatch, db):
    started = T0 - timedelta(minutes=5)
    cog = poll_cog(monkeypatch, {"1": stream_for(started)}, {"1": None}, db, now=T0)
    run(cog.twitch_live())
    db.claim_twitch_live.assert_called_once_with("1", started)
    embed = cog.bot.send_notify_communities.await_args.args[0]
    assert embed.author.name == "主播 開台啦！"
    assert embed.author.icon_url != "https://example.com/avatar.png"


def test_poll_claims_even_when_cache_record_exists_and_skips_when_lost(monkeypatch, db):
    """不再看 cache_data：事件先搶到時輪詢搶不到，不重複發。"""
    db.claim_twitch_live.return_value = False
    cog = poll_cog(monkeypatch, {"1": stream_for(T0)}, {"1": MagicMock()}, db)
    run(cog.twitch_live())
    db.claim_twitch_live.assert_called_once()
    cog.bot.send_notify_communities.assert_not_awaited()


def test_poll_claims_but_does_not_notify_stream_older_than_one_day(monkeypatch, db):
    started = T0 - timedelta(days=2)
    cog = poll_cog(monkeypatch, {"1": stream_for(started)}, {"1": None}, db, now=T0)
    run(cog.twitch_live())
    db.claim_twitch_live.assert_called_once_with("1", started)
    cog.bot.send_notify_communities.assert_not_awaited()


def test_poll_clears_with_time_taken_before_query_only_when_record_exists(monkeypatch, db):
    times = iter([T0, T0 + timedelta(seconds=30)])
    cog = poll_cog(monkeypatch, {}, {"1": MagicMock(), "2": None}, db)
    monkeypatch.setattr(task_module.utils, "nowtz", lambda: next(times))
    run(cog.twitch_live())
    db.clear_twitch_live.assert_called_once_with("1", T0)  # 查詢前的時間，不是清除當下
    db.claim_twitch_live.assert_not_called()
    cog.bot.send_notify_communities.assert_not_awaited()
