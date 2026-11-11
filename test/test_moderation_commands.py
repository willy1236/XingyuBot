"""W-04 指令懲處：/timeout、/kick、/ban、/warning add 走 punish，機器人與自己走保留路徑。"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from starDiscord.cmds import moderation as cmd
from starlib.database import WarningType
from starlib.moderation import PunishResult


def run(coro):
    return asyncio.run(coro)


def make_member(uid=10, bot=False):
    m = MagicMock(spec=discord.Member)
    m.id, m.bot, m.name, m.mention = uid, bot, "target", f"<@{uid}>"
    m.display_avatar = SimpleNamespace(url="http://x/a.png")
    m.timeout_for, m.kick, m.ban = AsyncMock(), AsyncMock(), AsyncMock()
    return m


def make_ctx(author_id=99):
    ctx = MagicMock()
    ctx.guild = MagicMock(spec=discord.Guild)
    ctx.guild.id = 1
    ctx.guild.members = []
    ctx.author = SimpleNamespace(id=author_id, name="admin", mention=f"<@{author_id}>")
    ctx.user = ctx.author
    ctx.defer, ctx.respond = AsyncMock(), AsyncMock()
    return ctx


@pytest.fixture
def env(monkeypatch):
    db = SimpleNamespace(add_warning=MagicMock(return_value=5))
    monkeypatch.setattr(cmd.sclient, "sqldb", db, raising=False)
    fake_punish = AsyncMock(return_value=PunishResult(ok=True, warning_id=7))
    monkeypatch.setattr(cmd, "punish", fake_punish)
    monkeypatch.setattr(cmd, "announcement", MagicMock(return_value={"content": "<@10>", "embed": discord.Embed()}))
    cog = cmd.moderation(MagicMock())
    return SimpleNamespace(db=db, punish=fake_punish, cog=cog)


@pytest.mark.parametrize("name,kind", [("kick", WarningType.Kick), ("ban", WarningType.Ban)])
@pytest.mark.parametrize("add_record", [False, True])
def test_kick_ban_use_punish_and_announcement(env, name, kind, add_record):
    ctx, user = make_ctx(), make_member()
    kwargs = {"delete_message_seconds": None} if name == "ban" else {}
    run(getattr(env.cog, name).callback(env.cog, ctx, user, "r", add_record, **kwargs))
    args, kw = env.punish.call_args
    assert args[1] == kind and kw["cross_guild"] is add_record and kw["via_dashboard"] is False
    ctx.respond.assert_awaited_once()
    assert ctx.respond.call_args.kwargs["content"] == "<@10>"


def test_timeout_passes_duration_and_records(env):
    ctx, user = make_ctx(), make_member()
    run(env.cog.timeout.callback(env.cog, ctx, user, "1h", "r", False, 60))
    args, kw = env.punish.call_args
    assert args[1] == WarningType.Timeout and kw["duration"] == timedelta(hours=1) and kw["delete_message_seconds"] == 60 and kw["cross_guild"] is False
    assert ctx.respond.call_args.kwargs["embed"].footer.text == "編號 7"


def test_timeout_failure_reports_error(env):
    env.punish.return_value = PunishResult(ok=False, error="機器人權限不足")
    ctx = make_ctx()
    run(env.cog.timeout.callback(env.cog, ctx, make_member(), "1h", "r", False, None))
    assert "機器人權限不足" in ctx.respond.call_args.args[0]


@pytest.mark.parametrize("name", ["kick", "ban"])
def test_bot_target_executes_without_record(env, name):
    ctx, user = make_ctx(), make_member(bot=True)
    kwargs = {"delete_message_seconds": None} if name == "ban" else {}
    run(getattr(env.cog, name).callback(env.cog, ctx, user, "r", True, **kwargs))
    getattr(user, name).assert_awaited_once()
    env.punish.assert_not_awaited()
    env.db.add_warning.assert_not_called()
    assert "embed" in ctx.respond.call_args.kwargs


def test_timeout_bot_target_executes_without_record(env):
    ctx, user = make_ctx(), make_member(bot=True)
    run(env.cog.timeout.callback(env.cog, ctx, user, "1h", "r", True, None))
    user.timeout_for.assert_awaited_once()
    env.punish.assert_not_awaited()
    env.db.add_warning.assert_not_called()


def test_self_target_keeps_legacy_path_and_records_guild_only(env):
    ctx, user = make_ctx(author_id=10), make_member(uid=10)
    run(env.cog.kick.callback(env.cog, ctx, user, "r", False))
    user.kick.assert_awaited_once()
    env.punish.assert_not_awaited()
    assert env.db.add_warning.call_args.kwargs["guild_only"] is True


def test_warning_add_uses_punish(env):
    ctx, user = make_ctx(), make_member()
    ctx.guild.members = [user]
    env.cog.bot.is_owner = AsyncMock(return_value=False)
    run(env.cog.warning_add.callback(env.cog, ctx, user, "r", True))
    args, kw = env.punish.call_args
    assert args[1] == WarningType.Warning and kw["cross_guild"] is True
    assert ctx.respond.call_args.kwargs["embed"].footer.text == "編號 7"


def test_warning_add_rejects_bot_and_nonmember(env):
    env.cog.bot.is_owner = AsyncMock(return_value=False)
    ctx = make_ctx()
    run(env.cog.warning_add.callback(env.cog, ctx, make_member(bot=True), "r", False))
    run(env.cog.warning_add.callback(env.cog, ctx, make_member(uid=11), "r", False))
    env.punish.assert_not_awaited()


def test_warning_add_owner_self_keeps_legacy(env):
    ctx, user = make_ctx(author_id=10), make_member(uid=10)
    env.cog.bot.is_owner = AsyncMock(return_value=True)
    run(env.cog.warning_add.callback(env.cog, ctx, user, "r", False))
    env.punish.assert_not_awaited()
    env.db.add_warning.assert_called_once()
