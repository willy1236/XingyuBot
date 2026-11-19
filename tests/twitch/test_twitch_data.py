"""Twitch 頻道功能資料（指令、計時訊息、事件回應、擋下紀錄）的 sqldb 存取函式。用綁在外層交易的 repo，測完 rollback。"""

from sqlalchemy import text
from sqlmodel import select

from starlib.database import (
    DBCacheType,
    TwitchAutomodBlock,
    TwitchChannelAudit,
    TwitchChatCommand,
    TwitchEventResponse,
    TwitchPoint,
    TwitchTimer,
)

TWITCH_ID = 2000000011
OTHER_ID = 2000000012


def test_舊指令列取得新欄位的預設值(repo):
    repo.session.execute(
        text("INSERT INTO stardb_basic.twitch_chat_command (twitch_id, name, response) VALUES (:t, 'hi', 'hello')"),
        {"t": TWITCH_ID},
    )
    row = repo.get_chat_command("hi", TWITCH_ID)
    repo.session.refresh(row)
    assert (row.aliases, row.enabled, row.global_cooldown, row.user_cooldown) == ([], True, 30, 0)
    assert (row.permission, row.use_count) == ("everyone", 0)
    assert row.updated_at is not None


def test_add_twitch_cmd_之後快取仍是整列(repo):
    """回歸：單頻道重載曾經把快取換成 {名稱: 回應字串}，之後讀 .response 會 AttributeError。"""
    repo.reload_cache(DBCacheType.TwitchCmd)
    repo.add_twitch_cmd(TWITCH_ID, "hi", "hello")
    cached = repo.get_twitch_cmd_response_cache(TWITCH_ID, "hi")
    assert isinstance(cached, TwitchChatCommand)
    assert cached.response == "hello"
    repo.remove_twitch_cmd(TWITCH_ID, "hi")
    assert repo.get_twitch_cmd_response_cache(TWITCH_ID, "hi") is None


def test_add_twitch_cmd_覆寫回應時保留其他欄位(repo):
    repo.save_twitch_chat_command(
        TwitchChatCommand(twitch_id=TWITCH_ID, name="hi", response="a", aliases=["h"], global_cooldown=5, use_count=7)
    )
    repo.add_twitch_cmd(TWITCH_ID, "hi", "b")
    row = repo.get_chat_command("hi", TWITCH_ID)
    assert (row.response, row.aliases, row.global_cooldown, row.use_count) == ("b", ["h"], 5, 7)


def test_指令的儲存_刪除與使用次數(repo):
    repo.save_twitch_chat_command(TwitchChatCommand(twitch_id=TWITCH_ID, name="hi", response="a"))
    assert repo.increment_twitch_cmd_use_count(TWITCH_ID, "hi") == 1
    assert repo.increment_twitch_cmd_use_count(TWITCH_ID, "hi") == 2
    assert repo.increment_twitch_cmd_use_count(TWITCH_ID, "nope") is None
    assert repo.delete_twitch_chat_command(TWITCH_ID, "hi") is True
    assert repo.delete_twitch_chat_command(TWITCH_ID, "hi") is False


def test_計時訊息的新增_更新_刪除(repo):
    saved = repo.save_twitch_timer(TwitchTimer(twitch_id=TWITCH_ID, message="m", interval_minutes=10))
    assert saved.id is not None
    saved.message = "m2"
    repo.save_twitch_timer(saved)
    repo.save_twitch_timer(TwitchTimer(twitch_id=OTHER_ID, message="x", interval_minutes=5))
    assert [t.message for t in repo.list_twitch_timers(TWITCH_ID)] == ["m2"]
    assert repo.get_twitch_timer(OTHER_ID, saved.id) is None  # 別的頻道看不到
    assert repo.delete_twitch_timer(TWITCH_ID, saved.id) is True
    assert repo.list_twitch_timers(TWITCH_ID) == []


def test_事件回應的儲存與恢復預設(repo):
    repo.save_twitch_event_response(
        TwitchEventResponse(twitch_id=TWITCH_ID, event_kind="follow", enabled=False, template="t")
    )
    repo.save_twitch_event_response(TwitchEventResponse(twitch_id=TWITCH_ID, event_kind="follow", template="t2"))
    rows = repo.list_twitch_event_responses(TWITCH_ID)
    assert [(r.event_kind, r.enabled, r.template) for r in rows] == [("follow", True, "t2")]
    assert repo.delete_twitch_event_response(TWITCH_ID, "follow") is True
    assert repo.get_twitch_event_response(TWITCH_ID, "follow") is None


def test_擋下紀錄每個頻道只留最新100筆(repo):
    for i in range(105):
        repo.add_twitch_automod_block(TWITCH_ID, "command", "hi", f"t{i}", "automod")
    repo.add_twitch_automod_block(OTHER_ID, "timer", "1", "other", "check_failed")
    rows = repo.session.exec(select(TwitchAutomodBlock).where(TwitchAutomodBlock.twitch_id == TWITCH_ID)).all()
    assert len(rows) == 100
    latest = repo.list_twitch_automod_blocks(TWITCH_ID, limit=20)
    assert [r.text for r in latest] == [f"t{i}" for i in range(104, 84, -1)]
    assert min(int(r.text[1:]) for r in rows) == 5
    assert len(repo.list_twitch_automod_blocks(OTHER_ID)) == 1


def test_依_twitch_id_刪除頻道資料_不碰修改紀錄與其他頻道(repo):
    for tid in (TWITCH_ID, OTHER_ID):
        repo.save_twitch_chat_command(TwitchChatCommand(twitch_id=tid, name="hi", response="a"))
        repo.save_twitch_timer(TwitchTimer(twitch_id=tid, message="m", interval_minutes=5))
        repo.save_twitch_event_response(TwitchEventResponse(twitch_id=tid, event_kind="raid", template="t"))
        repo.add_twitch_automod_block(tid, "command", "hi", "x", "automod")
        repo.session.add(TwitchPoint(twitch_id=1, broadcaster_id=tid, point=3))
        repo.session.add(
            TwitchChannelAudit(
                twitch_id=tid,
                actor_platform="twitch",
                actor_id="1",
                actor_name="a",
                source="dashboard",
                target_kind="command",
                target_key="hi",
                action="create",
            )
        )
    repo.session.flush()

    repo.delete_twitch_channel_data(TWITCH_ID)

    def counts(tid: int) -> list[int]:
        models = (TwitchChatCommand, TwitchTimer, TwitchEventResponse, TwitchAutomodBlock, TwitchChannelAudit)
        result = [len(repo.session.exec(select(m).where(m.twitch_id == tid)).all()) for m in models]
        result.append(len(repo.session.exec(select(TwitchPoint).where(TwitchPoint.broadcaster_id == tid)).all()))
        return result

    assert counts(TWITCH_ID) == [0, 0, 0, 0, 1, 0]
    assert counts(OTHER_ID) == [1, 1, 1, 1, 1, 1]


def test_指令快取存與_session_無關的複本(repo):
    """回歸：快取存 session 內的 instance，session 釋放或 commit 後讀屬性會 DetachedInstanceError 或多一次 SELECT。"""
    from sqlalchemy.orm import object_session

    repo.save_twitch_chat_command(TwitchChatCommand(twitch_id=TWITCH_ID, name="hi", response="a", aliases=["h"]))
    for rows in (
        repo.get_raw_chat_command_channel(TWITCH_ID),
        repo.get_raw_chat_command_all()[TWITCH_ID],
    ):
        assert object_session(rows["hi"]) is None
        assert (rows["hi"].response, rows["hi"].aliases) == ("a", ["h"])


def test_新表的_twitch_id_是_64_位元(repo):
    big = 3_000_000_000  # 超過 int32
    repo.save_twitch_timer(TwitchTimer(twitch_id=big, message="m", interval_minutes=5))
    repo.add_twitch_automod_block(big, "command", "hi", "x", "automod")
    repo.session.add(
        TwitchChannelAudit(
            twitch_id=big,
            actor_platform="twitch",
            actor_id="1",
            actor_name="a",
            source="dashboard",
            target_kind="command",
            target_key="hi",
            action="create",
        )
    )
    repo.session.flush()
    assert len(repo.list_twitch_timers(big)) == 1
    assert len(repo.list_twitch_automod_blocks(big)) == 1
