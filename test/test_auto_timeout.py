"""B-02 警告累計自動禁言：設定換算、觸發判斷與執行（真實 PostgreSQL 計數，假 Discord）。"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from sqlmodel import select
from test_identity import repo  # noqa: F401  (fixture)

from starlib import auto_timeout, moderation
from starlib.database import GuildSetting, UserModerate, WarningType
from starlib.moderation import punish, register_after_warning
from starlib.utils import format_seconds, nowtz

GUILD_ID = 910000000000000001
TARGET = 910000000000000002
BOT_ID = 910000000000000003
ADMIN = SimpleNamespace(id=910000000000000004, name="admin", mention="<@admin>")


def run(coro):
    return asyncio.run(coro)


def forbidden():
    return discord.Forbidden(SimpleNamespace(status=403, reason="x"), "no")


def make_member(uid=TARGET):
    m = MagicMock(spec=discord.Member)
    m.id, m.bot, m.name, m.mention = uid, False, "target", f"<@{uid}>"
    m.timeout_for = AsyncMock()
    return m


def make_guild(member: discord.Member | None, *, moderate_members=True):
    g = MagicMock(spec=discord.Guild)
    g.id = GUILD_ID
    g.get_member = MagicMock(return_value=member)
    g.me = SimpleNamespace(id=BOT_ID, name="bot", bot=True, guild_permissions=SimpleNamespace(moderate_members=moderate_members))
    g.text_channels = []
    return g


@pytest.fixture
def db(repo, monkeypatch):  # noqa: F811
    monkeypatch.setattr(moderation.sclient, "sqldb", repo, raising=False)
    monkeypatch.setattr(auto_timeout.sclient, "sqldb", repo, raising=False)
    auto_timeout.register()
    yield repo
    register_after_warning(None)


def configure(db, *, enabled=True, times=2, seconds=600):
    db.merge(GuildSetting(guild_id=GUILD_ID, timeout_after_warning_times=times, voice_time_counter=None, auto_timeout_enabled=enabled, auto_timeout_seconds=seconds))


def warn(guild, member, cross_guild=False):
    return run(punish(guild, WarningType.Warning, member, ADMIN, "r", cross_guild=cross_guild, via_dashboard=False))


def records(db, kind: WarningType) -> list[UserModerate]:
    stmt = select(UserModerate).where(UserModerate.discord_id == TARGET, UserModerate.create_guild == GUILD_ID, UserModerate.moderate_type == kind)
    return list(db.session.exec(stmt).all())


class TestSettingHelpers:
    def test_defaults_without_row(self):
        assert auto_timeout.effective_setting(None) == auto_timeout.AutoTimeoutSetting(False, 3, 600)

    def test_null_columns_use_defaults(self):
        row = GuildSetting(guild_id=1, timeout_after_warning_times=None, voice_time_counter=None, auto_timeout_enabled=True, auto_timeout_seconds=None)
        assert auto_timeout.effective_setting(row) == auto_timeout.AutoTimeoutSetting(True, 3, 600)

    @pytest.mark.parametrize(
        "text,seconds",
        [("10m", 600), ("1h20m", 4800), ("30s", None), ("59s", None), ("60s", 60), ("90s", None), ("1m30s", None), ("7d", 604800), ("8d", None), ("10", None), ("abc", None), ("", None), ("5m3", None)],
    )
    def test_parse_duration(self, text, seconds):
        assert auto_timeout.parse_duration(text) == seconds

    @pytest.mark.parametrize("seconds,text", [(600, "10 分鐘"), (5400, "1 小時 30 分鐘"), (604800, "7 天"), (0, "0 秒")])
    def test_format_seconds(self, seconds, text):
        assert format_seconds(seconds) == text

    @pytest.mark.parametrize("times,ok", [(0, False), (1, True), (20, True), (21, False)])
    def test_valid_times(self, times, ok):
        assert auto_timeout.valid_times(times) is ok

    def test_permission_issue(self):
        assert auto_timeout.moderate_members_issue(make_guild(None)) is None
        assert auto_timeout.moderate_members_issue(make_guild(None, moderate_members=False)).permission == "Moderate Members"


class TestTrigger:
    def test_second_warning_triggers_then_resets_count(self, db):
        configure(db, times=2, seconds=600)
        member = make_member()
        guild = make_guild(member)
        assert warn(guild, member).auto_timeout is None
        second = warn(guild, member)
        assert second.auto_timeout.ok and second.auto_timeout.duration == timedelta(seconds=600)
        member.timeout_for.assert_awaited_once()
        assert member.timeout_for.await_args.args[0] == timedelta(seconds=600)
        (record,) = records(db, WarningType.Timeout)
        assert record.moderate_user == BOT_ID and record.guild_only is True
        assert record.reason == "累計 2 次警告自動禁言" and record.last_time == timedelta(seconds=600)
        # 之後再警告一次不觸發，再一次才觸發
        assert warn(guild, member).auto_timeout is None
        assert warn(guild, member).auto_timeout.ok
        assert len(records(db, WarningType.Timeout)) == 2

    def test_cross_guild_warnings_count_too(self, db):
        configure(db, times=2)
        member = make_member()
        guild = make_guild(member)
        warn(guild, member, cross_guild=True)
        assert warn(guild, member, cross_guild=False).auto_timeout.ok

    def test_count_already_over_threshold_triggers_next_warning(self, db):
        member = make_member()
        guild = make_guild(member)
        configure(db, enabled=False, times=5)
        for _ in range(4):
            assert warn(guild, member).auto_timeout is None
        configure(db, enabled=True, times=2)
        assert warn(guild, member).auto_timeout.ok

    def test_removing_auto_timeout_record_counts_old_warnings_again(self, db):
        configure(db, times=2)
        member = make_member()
        guild = make_guild(member)
        warn(guild, member)
        warn(guild, member)
        (record,) = records(db, WarningType.Timeout)
        assert db.get_warning_count(TARGET, GUILD_ID) == 0
        db.remove_warning(record.warning_id)
        assert db.get_warning_count(TARGET, GUILD_ID) == 2
        assert warn(guild, member).auto_timeout.ok

    def test_manual_timeout_without_record_flag_resets_count(self, db):
        configure(db, times=2)
        member = make_member()
        guild = make_guild(member)
        warn(guild, member)
        run(punish(guild, WarningType.Timeout, member, ADMIN, "r", cross_guild=False, duration=timedelta(minutes=5), via_dashboard=False))
        assert warn(guild, member).auto_timeout is None

    def test_other_guild_records_not_counted(self, db):
        configure(db, times=2)
        member = make_member()
        db.add_warning(TARGET, WarningType.Warning, ADMIN.id, GUILD_ID + 1, nowtz(), "x", None, guild_only=False)
        assert warn(make_guild(member), member).auto_timeout is None

    def test_disabled_never_triggers(self, db):
        configure(db, enabled=False, times=1)
        member = make_member()
        assert warn(make_guild(member), member).auto_timeout is None
        member.timeout_for.assert_not_awaited()

    def test_no_setting_row_never_triggers(self, db):
        member = make_member()
        assert warn(make_guild(member), member).auto_timeout is None

    def test_target_not_in_guild_does_not_trigger(self, db):
        configure(db, times=1)
        user = MagicMock(spec=discord.User)
        user.id, user.bot, user.name, user.mention = TARGET, False, "away", f"<@{TARGET}>"
        assert run(auto_timeout.after_warning(make_guild(None), user, 1)) is None
        assert records(db, WarningType.Timeout) == []

    def test_discord_refusal_keeps_warning_and_writes_no_timeout_record(self, db):
        configure(db, times=1)
        member = make_member()
        member.timeout_for.side_effect = forbidden()
        res = warn(make_guild(member), member)
        assert res.ok and res.warning_id is not None
        assert not res.auto_timeout.ok and "權限不足" in res.auto_timeout.error
        assert records(db, WarningType.Timeout) == []
        assert len(records(db, WarningType.Warning)) == 1

    def test_simultaneous_warnings_time_out_only_once(self, db):
        configure(db, times=2)
        member = make_member()

        async def slow_timeout(*args, **kwargs):
            await asyncio.sleep(0.05)  # 讓另一筆警告在禁言執行期間寫入

        member.timeout_for.side_effect = slow_timeout
        guild = make_guild(member)

        async def both():
            first = punish(guild, WarningType.Warning, member, ADMIN, "a", cross_guild=False, via_dashboard=False)
            second = punish(guild, WarningType.Warning, member, ADMIN, "b", cross_guild=False, via_dashboard=False)
            return await asyncio.gather(first, second)

        warn(guild, member)  # 先累計 1 次，之後任一筆新警告都會達到 N
        results = run(both())
        assert sum(1 for r in results if r.auto_timeout is not None and r.auto_timeout.ok) == 1
        assert member.timeout_for.await_count == 1
        assert len(records(db, WarningType.Timeout)) == 1

    def test_register_installs_hook(self):
        register_after_warning(None)
        auto_timeout.register()
        try:
            assert moderation._after_warning is auto_timeout.after_warning
        finally:
            register_after_warning(None)
