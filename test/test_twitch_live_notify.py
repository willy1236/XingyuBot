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
