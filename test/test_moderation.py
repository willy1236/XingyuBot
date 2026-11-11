"""S-03 懲處服務：執行、寫紀錄、公告與稽核原因。"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from enum import IntEnum
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from starlib import moderation
from starlib.database import WarningType
from starlib.moderation import AutoTimeoutResult, announcement, audit_reason, punish, register_after_warning


def run(coro):
    return asyncio.run(coro)


def http_error(cls=discord.HTTPException):
    status = {discord.Forbidden: 403, discord.NotFound: 404}.get(cls, 500)
    return cls(SimpleNamespace(status=status, reason="x"), "boom")


def make_member(uid=10, bot=False, name="target"):
    m = MagicMock(spec=discord.Member)
    m.id, m.bot, m.name, m.mention = uid, bot, name, f"<@{uid}>"
    m.timeout_for, m.kick = AsyncMock(), AsyncMock()
    return m


def make_user(uid=10, bot=False):
    u = MagicMock(spec=discord.User)
    u.id, u.bot, u.name, u.mention = uid, bot, "outsider", f"<@{uid}>"
    return u


def make_guild(member=None):
    g = MagicMock(spec=discord.Guild)
    g.id = 1
    g.ban, g.fetch_ban = AsyncMock(), AsyncMock(side_effect=http_error(discord.NotFound))
    g.get_member = MagicMock(return_value=member)
    g.text_channels = []
    return g


@pytest.fixture
def db(monkeypatch):
    fake = SimpleNamespace(add_warning=MagicMock(return_value=77), get_warning=MagicMock())
    monkeypatch.setattr(moderation.sclient, "sqldb", fake, raising=False)
    register_after_warning(None)
    yield fake
    register_after_warning(None)


ACTOR = SimpleNamespace(id=99, name="admin", mention="<@99>")
HOUR = timedelta(hours=1)


def test_warning_type_is_int_enum():
    assert issubclass(WarningType, IntEnum)
    assert WarningType.Warning == 1 and WarningType.Ban == 4


@pytest.mark.parametrize("kind", [WarningType.Warning, WarningType.Timeout, WarningType.Kick, WarningType.Ban])
@pytest.mark.parametrize("cross_guild", [False, True])
def test_success_writes_one_record(db, kind, cross_guild):
    member = make_member()
    res = run(punish(make_guild(member), kind, member, ACTOR, "r", cross_guild=cross_guild, duration=HOUR, via_dashboard=False))
    assert res.ok and res.warning_id == 77
    db.add_warning.assert_called_once()
    args, kwargs = db.add_warning.call_args
    assert args[1] == kind and args[2] == 99 and args[3] == 1
    assert args[4].tzinfo is not None
    assert kwargs["guild_only"] is (not cross_guild)
    assert (args[6] == HOUR) is (kind == WarningType.Timeout)


@pytest.mark.parametrize("kind", [WarningType.Warning, WarningType.Timeout, WarningType.Kick, WarningType.Ban])
@pytest.mark.parametrize("who", ["bot", "self"])
def test_bot_or_self_target_is_blocked(db, kind, who):
    member = make_member(uid=99 if who == "self" else 10, bot=who == "bot")
    guild = make_guild(member)
    called = []

    async def hook(guild, target, warning_id):
        called.append(1)

    register_after_warning(hook)
    res = run(punish(guild, kind, member, ACTOR, "r", cross_guild=True, duration=HOUR, via_dashboard=False))
    assert not res.ok and res.error and res.warning_id is None and called == []
    member.kick.assert_not_awaited()
    member.timeout_for.assert_not_awaited()
    guild.ban.assert_not_awaited()
    guild.fetch_ban.assert_not_awaited()
    db.add_warning.assert_not_called()


@pytest.mark.parametrize("cls", [discord.Forbidden, discord.HTTPException])
@pytest.mark.parametrize("kind", [WarningType.Timeout, WarningType.Kick, WarningType.Ban])
def test_discord_failure_writes_nothing(db, cls, kind):
    member = make_member()
    member.timeout_for.side_effect = member.kick.side_effect = http_error(cls)
    guild = make_guild(member)
    guild.ban.side_effect = http_error(cls)
    res = run(punish(guild, kind, member, ACTOR, "r", cross_guild=False, duration=HOUR, via_dashboard=False))
    assert not res.ok and res.error and res.warning_id is None
    db.add_warning.assert_not_called()


def test_already_banned_is_success_without_record(db):
    guild = make_guild()
    guild.fetch_ban = AsyncMock(return_value=object())
    res = run(punish(guild, WarningType.Ban, make_user(), ACTOR, "r", cross_guild=False, via_dashboard=False))
    assert res.ok and res.already and res.warning_id is None
    guild.ban.assert_not_awaited()
    db.add_warning.assert_not_called()


@pytest.mark.parametrize("err", [discord.NotFound, discord.HTTPException])
def test_ban_when_fetch_ban_not_found_or_lookup_fails(db, err):
    guild = make_guild()
    guild.fetch_ban = AsyncMock(side_effect=http_error(err))
    res = run(punish(guild, WarningType.Ban, make_user(), ACTOR, "r", cross_guild=False, delete_message_seconds=60, via_dashboard=False))
    assert res.ok and not res.already and res.warning_id == 77
    assert guild.ban.await_args.kwargs["delete_message_seconds"] == 60


@pytest.mark.parametrize("kind", [WarningType.Timeout, WarningType.Kick])
def test_timeout_kick_need_member(db, kind):
    res = run(punish(make_guild(None), kind, make_user(), ACTOR, "r", cross_guild=False, duration=HOUR, via_dashboard=False))
    assert not res.ok and "不在伺服器" in res.error
    db.add_warning.assert_not_called()


def test_timeout_resolves_member_from_user(db):
    member = make_member()
    res = run(punish(make_guild(member), WarningType.Timeout, make_user(), ACTOR, "r", cross_guild=False, duration=HOUR, via_dashboard=False))
    assert res.ok
    member.timeout_for.assert_awaited_once()


def test_timeout_duration_limits(db):
    member = make_member()
    kw = dict(cross_guild=False, via_dashboard=False)
    ok = run(punish(make_guild(member), WarningType.Timeout, member, ACTOR, "r", duration=timedelta(days=7), **kw))
    over = run(punish(make_guild(member), WarningType.Timeout, member, ACTOR, "r", duration=timedelta(days=7, seconds=1), **kw))
    none = run(punish(make_guild(member), WarningType.Timeout, member, ACTOR, "r", **kw))
    assert ok.ok and not over.ok and not none.ok
    assert member.timeout_for.await_count == 1


def test_timeout_delete_messages_counts_skipped(db):
    member = make_member()
    guild = make_guild(member)
    full = SimpleNamespace(view_channel=True, read_message_history=True, manage_messages=True)
    good = MagicMock()
    good.permissions_for.return_value = full
    good.purge = AsyncMock(return_value=[1, 2, 3])
    denied = MagicMock()
    denied.permissions_for.return_value = SimpleNamespace(view_channel=True, read_message_history=True, manage_messages=False)
    broken = MagicMock()
    broken.permissions_for.return_value = full
    broken.purge = AsyncMock(side_effect=http_error(discord.Forbidden))
    guild.text_channels = [good, denied, broken]
    res = run(punish(guild, WarningType.Timeout, member, ACTOR, "r", cross_guild=False, duration=HOUR, delete_message_seconds=120, via_dashboard=False))
    assert res.deleted_summary == "最近 120 秒內全伺服器共刪除 3 則（略過 2 個頻道）"
    assert good.purge.await_args.kwargs["limit"] == 50


def test_hook_only_for_warning_and_result_passed(db):
    calls = []

    async def hook(guild, target, warning_id):
        calls.append(warning_id)
        return AutoTimeoutResult(ok=True, duration=HOUR)

    member = make_member()
    run(punish(make_guild(member), WarningType.Kick, member, ACTOR, "r", cross_guild=False, via_dashboard=False))
    assert calls == []
    register_after_warning(hook)
    res = run(punish(make_guild(member), WarningType.Warning, member, ACTOR, "r", cross_guild=False, via_dashboard=False))
    assert calls == [77] and res.auto_timeout.ok


def test_no_hook_means_no_auto_timeout(db):
    member = make_member()
    res = run(punish(make_guild(member), WarningType.Warning, member, ACTOR, "r", cross_guild=False, via_dashboard=False))
    assert res.auto_timeout is None


def test_hook_exception_becomes_error_result_and_keeps_record(db):
    async def hook(guild, target, warning_id):
        raise RuntimeError("bad")

    register_after_warning(hook)
    member = make_member()
    res = run(punish(make_guild(member), WarningType.Warning, member, ACTOR, "r", cross_guild=False, via_dashboard=False))
    assert res.ok and res.warning_id == 77
    assert not res.auto_timeout.ok and "bad" in res.auto_timeout.error


def test_audit_reason():
    assert audit_reason(ACTOR, "原因", True) == "admin 透過後台：原因"
    assert audit_reason(ACTOR, "原因", False) == "原因"
    assert audit_reason(ACTOR, None, False) == ""
    long = audit_reason(ACTOR, "x" * 600, True)
    assert len(long) == 512 and long.endswith("…") and long.startswith("admin 透過後台：")


def test_announcement_mentions_target_and_has_record_embed(db, monkeypatch):
    embed = discord.Embed(description="編號：77")
    row = MagicMock()
    row.embed.return_value = embed
    db.get_warning.return_value = row
    monkeypatch.setattr(moderation.sclient, "bot", object(), raising=False)
    res = moderation.PunishResult(ok=True, warning_id=77, deleted_summary="已刪 3 則", auto_timeout=AutoTimeoutResult(ok=True, duration=HOUR))
    data = announcement(res, make_member(), ACTOR)
    assert data["content"] == "<@10>"
    assert data["embed"] is embed and "77" in embed.description
    assert [f.name for f in embed.fields] == ["訊息刪除", "自動禁言"]
    am = data["allowed_mentions"]
    assert am.everyone is False and am.roles is False and [u.id for u in am.users] == [10]
    db.get_warning.assert_called_once_with(77)


@pytest.mark.parametrize("duration,text", [(timedelta(minutes=10), "10 分鐘"), (timedelta(hours=1, minutes=30), "1 小時 30 分鐘"), (timedelta(days=7), "7 天")])
def test_announcement_auto_timeout_duration_in_chinese(db, monkeypatch, duration, text):
    row = MagicMock()
    row.embed.return_value = discord.Embed()
    db.get_warning.return_value = row
    monkeypatch.setattr(moderation.sclient, "bot", object(), raising=False)
    res = moderation.PunishResult(ok=True, warning_id=77, auto_timeout=AutoTimeoutResult(ok=True, duration=duration))
    value = announcement(res, make_member(), ACTOR)["embed"].fields[0].value
    assert value == f"已禁言 {text}"


def test_announcement_auto_timeout_done_but_record_failed_shows_error(db, monkeypatch):
    row = MagicMock()
    row.embed.return_value = discord.Embed()
    db.get_warning.return_value = row
    monkeypatch.setattr(moderation.sclient, "bot", object(), raising=False)
    auto = AutoTimeoutResult(ok=True, duration=timedelta(minutes=10), error="動作已執行，但紀錄寫入失敗")
    value = announcement(moderation.PunishResult(ok=True, warning_id=77, auto_timeout=auto), make_member(), ACTOR)["embed"].fields[0].value
    assert value == "已禁言 10 分鐘\n注意：動作已執行，但紀錄寫入失敗"


def test_announcement_auto_timeout_failure_reason(db, monkeypatch):
    row = MagicMock()
    row.embed.return_value = discord.Embed()
    db.get_warning.return_value = row
    monkeypatch.setattr(moderation.sclient, "bot", object(), raising=False)
    res = moderation.PunishResult(ok=True, warning_id=77, auto_timeout=AutoTimeoutResult(ok=False, error="權限不足"))
    embed = announcement(res, make_member(), ACTOR)["embed"]
    assert "權限不足" in embed.fields[0].value


def test_record_write_failure_keeps_ok_and_skips_hook(db):
    called = []

    async def hook(guild, target, warning_id):
        called.append(1)

    register_after_warning(hook)
    db.add_warning.side_effect = RuntimeError("db down")
    member = make_member()
    res = run(punish(make_guild(member), WarningType.Warning, member, ACTOR, "r", cross_guild=False, via_dashboard=False))
    assert res.ok and res.warning_id is None and "紀錄寫入失敗" in res.error
    assert res.auto_timeout is None and called == []
    kick = run(punish(make_guild(member), WarningType.Kick, member, ACTOR, "r", cross_guild=False, via_dashboard=False))
    assert kick.ok and kick.warning_id is None
    member.kick.assert_awaited_once()


def test_announcement_works_without_record(db, monkeypatch):
    monkeypatch.setattr(moderation.sclient, "bot", object(), raising=False)
    res = moderation.PunishResult(ok=True, error="動作已執行，但紀錄寫入失敗")
    data = announcement(res, make_member(), ACTOR)
    assert data["content"] == "<@10>" and data["embed"] is not None
    db.get_warning.assert_not_called()
