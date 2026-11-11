"""B-02 `/server setting`：查看與修改伺服器設定（真實 PostgreSQL，假 Discord）。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from test_identity import repo  # noqa: F401  (fixture)

from starDiscord.cmds import moderation as cmd
from starlib import auto_timeout

GUILD_ID = 920000000000000001


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def env(repo, monkeypatch):  # noqa: F811
    monkeypatch.setattr(cmd.sclient, "sqldb", repo, raising=False)
    repo.cache.voice_time_counter.load([])
    ctx = MagicMock()
    ctx.guild = MagicMock(spec=discord.Guild)
    ctx.guild.id = GUILD_ID
    ctx.guild.icon = None
    ctx.guild.me = SimpleNamespace(guild_permissions=SimpleNamespace(moderate_members=True))
    ctx.respond = AsyncMock()
    return SimpleNamespace(repo=repo, ctx=ctx, cog=cmd.moderation(MagicMock()))


def call(env, voice=None, auto=None, times=None, duration=None):
    run(env.cog.server_setting.callback(env.cog, env.ctx, voice, auto, times, duration))
    return env.ctx.respond


def fields(respond) -> dict[str, str]:
    embed = respond.call_args.kwargs["embed"]
    return {f.name: f.value for f in embed.fields}


def test_no_options_shows_defaults_and_writes_nothing(env):
    respond = call(env)
    assert respond.call_args.kwargs["ephemeral"] is True
    assert fields(respond)["語音時數統計"] == "關閉"
    assert "關閉" in fields(respond)["自動禁言"] and "3 次" in fields(respond)["自動禁言"]
    assert env.repo.get_guild_setting_fresh(GUILD_ID) is None


def test_toggle_voice_time_counter_refreshes_cache(env):
    respond = call(env, voice=True)
    assert fields(respond)["語音時數統計"] == "開啟"
    assert GUILD_ID in env.repo.cache.voice_time_counter.raw()
    call(env, voice=False)
    assert GUILD_ID not in env.repo.cache.voice_time_counter.raw()


def test_enable_auto_timeout_writes_defaults_for_unset_values(env):
    respond = call(env, auto=True)
    row = env.repo.get_guild_setting_fresh(GUILD_ID)
    assert (row.auto_timeout_enabled, row.timeout_after_warning_times, row.auto_timeout_seconds) == (True, 3, 600)
    assert "累計 3 次禁言 10 分鐘" in fields(respond)["自動禁言"]


def test_set_times_and_duration(env):
    respond = call(env, auto=True, times=2, duration="1h30m")
    row = env.repo.get_guild_setting_fresh(GUILD_ID)
    assert (row.timeout_after_warning_times, row.auto_timeout_seconds) == (2, 5400)
    assert "累計 2 次禁言 1 小時 30 分鐘" in fields(respond)["自動禁言"]


def test_only_given_options_change(env):
    call(env, voice=True, auto=True, times=5, duration="30m")
    call(env, times=7)
    row = env.repo.get_guild_setting_fresh(GUILD_ID)
    assert (row.voice_time_counter, row.auto_timeout_enabled, row.timeout_after_warning_times, row.auto_timeout_seconds) == (True, True, 7, 1800)


def test_enable_keeps_existing_values(env):
    call(env, times=4, duration="20m")
    call(env, auto=True)
    row = env.repo.get_guild_setting_fresh(GUILD_ID)
    assert (row.timeout_after_warning_times, row.auto_timeout_seconds) == (4, 1200)


def test_disable_auto_timeout(env):
    call(env, auto=True)
    respond = call(env, auto=False)
    assert env.repo.get_guild_setting_fresh(GUILD_ID).auto_timeout_enabled is False
    assert "關閉" in fields(respond)["自動禁言"]


@pytest.mark.parametrize("duration", ["10", "abc", "30s", "8d", "5m3", "90s", "1m30s"])
def test_invalid_duration_is_rejected_without_writing(env, duration):
    respond = call(env, voice=True, duration=duration)
    assert "時長格式錯誤" in respond.call_args.args[0] and respond.call_args.kwargs["ephemeral"] is True
    assert env.repo.get_guild_setting_fresh(GUILD_ID) is None


def test_warns_when_bot_lacks_moderate_members(env):
    env.ctx.guild.me.guild_permissions.moderate_members = False
    respond = call(env, auto=True)
    assert "Moderate Members" in fields(respond)["注意"]
    assert auto_timeout.moderate_members_issue(env.ctx.guild) is not None


def test_requires_manage_guild():
    checks = [c.__qualname__ for c in cmd.moderation.server_setting.checks]
    assert any("has_guild_permissions" in name for name in checks)
