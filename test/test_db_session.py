"""BaseRepository 的交易邊界：bot 的 event loop thread 一直持有同一個 scoped session，讀完要結束交易，
連線才不會停在 idle in transaction 握著讀過的表的鎖（真實 PostgreSQL）。"""

from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlmodel import Session, select

from starlib import sqldb
from starlib.database import TwitchBotJoinChannel
from starlib.database.postgresql.client import SQLRepository

# 不會跟真實資料撞到的 twitch_id；只 flush 不 commit，測試結束 rollback
_TEST_TWITCH_ID = -987654321


class _Repo(SQLRepository):
    def read_join_channels(self):
        return list(self.session.exec(select(TwitchBotJoinChannel)).all())

    def outer_read(self) -> bool:
        """巢狀呼叫：內層方法結束時不能收掉外層還在用的交易"""
        self.read_join_channels()
        return self.session.in_transaction()

    def lock_and_read(self) -> None:
        self._keep_transaction_open()
        self.session.exec(text("SELECT 1"))


@pytest.fixture
def scoped():
    app_name = f"txn-test-{uuid4().hex[:8]}"
    engine = create_engine(sqldb.engine.url, connect_args={"application_name": app_name})
    factory = scoped_session(sessionmaker(bind=engine, class_=Session, autoflush=True, expire_on_commit=True))
    repo = _Repo(engine, factory)

    def idle_in_transaction() -> int:
        with sqldb.engine.connect() as conn:
            return conn.execute(
                text(
                    "SELECT count(*) FROM pg_stat_activity WHERE application_name = :n AND state LIKE 'idle in transaction%'"
                ),
                {"n": app_name},
            ).scalar_one()

    try:
        yield repo, idle_in_transaction
    finally:
        factory.remove()
        engine.dispose()


def test_read_ends_transaction(scoped):
    repo, idle_in_transaction = scoped
    repo.get_bot_join_channel_all()
    assert not repo.session.in_transaction()
    assert idle_in_transaction() == 0


def test_returned_objects_stay_loaded(scoped):
    repo, _ = scoped
    repo.session.add(TwitchBotJoinChannel(twitch_id=_TEST_TWITCH_ID, point_name="p"))
    repo.session.flush()
    repo.session.rollback()
    rows = repo.read_join_channels()
    # 讀屬性不能因為 commit 時 expire 而再開一個交易
    [r.point_name for r in rows]
    assert not repo.session.in_transaction()


def test_nested_call_keeps_outer_transaction(scoped):
    repo, _ = scoped
    assert repo.outer_read() is True
    assert not repo.session.in_transaction()


def test_flushed_write_keeps_transaction(scoped):
    repo, idle_in_transaction = scoped
    repo.session.add(TwitchBotJoinChannel(twitch_id=_TEST_TWITCH_ID))
    repo.read_join_channels()  # autoflush 把 INSERT 送出，但還沒 commit
    assert repo.session.in_transaction()
    assert idle_in_transaction() == 1
    repo.session.rollback()
    repo.read_join_channels()
    assert not repo.session.in_transaction()


def test_pending_object_keeps_transaction(scoped):
    repo, _ = scoped
    repo.session.exec(text("SELECT 1"))  # 直接用 session 開交易，不經包裝
    repo.session.add(TwitchBotJoinChannel(twitch_id=_TEST_TWITCH_ID))  # 還沒 flush
    repo.get_twitch_cmd_response_cache(0, "x")  # 有包裝、不碰 DB 的方法
    assert repo.session.in_transaction()
    assert repo.session.new
    repo.session.rollback()


def test_base_repository_methods_end_transaction(scoped):
    repo, _ = scoped
    repo.get(TwitchBotJoinChannel, (_TEST_TWITCH_ID,))
    assert not repo.session.in_transaction()


def test_kept_transaction_until_commit(scoped):
    repo, _ = scoped
    repo.lock_and_read()
    assert repo.session.in_transaction()
    repo.read_join_channels()
    assert repo.session.in_transaction()
    repo.commit()
    repo.read_join_channels()
    assert not repo.session.in_transaction()


def test_plain_session_untouched():
    """固定單一 Session（測試的 savepoint fixture）不能被自動 commit"""
    with Session(sqldb.engine) as session:
        repo = SQLRepository(sqldb.engine, session)
        repo.get_bot_join_channel_all()
        assert session.in_transaction()
