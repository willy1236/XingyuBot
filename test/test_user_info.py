"""/user_info 顯示析域帳號狀態：repository（真實 PostgreSQL，交易結束後 rollback）與指令 callback（假的 auth server）。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

from starDiscord import checks
from starDiscord.cmds import system_user as user_cog
from starlib.database import DiscordIdentity, DriveShare, PlatformType
from starlib.identity import IdentityResolver
from starlib.utils import nowtz
from test_identity import TTL, FakeDirectory, _account, repo  # noqa: F401  (repo 為 fixture)

CALLER = 900000000000000010
TARGET = 900000000000000011
OTHER = 900000000000000012


def _record(discord_id: int, user_id, *, formal: bool) -> DiscordIdentity:
    return DiscordIdentity(discord_id=discord_id, user_id=user_id, is_formal=formal, username=None, roles=[], suspended=False, checked_at=nowtz())


# ─── Repository ─────────────────────────────────────────────────────────────


class TestGetDiscordIdsByUser:
    def test_returns_all_sorted_and_excludes_other_users(self, repo):
        uid = uuid4()
        repo.merge(_record(OTHER, uid, formal=True))
        repo.merge(_record(CALLER, uid, formal=True))
        repo.merge(_record(TARGET, uuid4(), formal=True))

        assert repo.get_discord_ids_by_user(uid) == [CALLER, OTHER]

    def test_unknown_user_is_empty(self, repo):
        assert repo.get_discord_ids_by_user(uuid4()) == []


# ─── 指令 callback ──────────────────────────────────────────────────────────


class FakeCtx:
    def __init__(self, discord_id: int = CALLER):
        self.author = SimpleNamespace(id=discord_id, avatar=None)
        self.guild_id = 0
        self.responses: list[SimpleNamespace] = []

    async def respond(self, content=None, **kwargs):
        self.responses.append(SimpleNamespace(content=content, **kwargs))

    @property
    def embeds(self):
        return self.responses[-1].embeds

    @property
    def account_text(self) -> str:
        """第一個 embed（析域帳號區塊）的所有欄位文字。"""
        return "\n".join(f"{f.name}\n{f.value}" for f in self.embeds[0].fields)

    @property
    def all_text(self) -> str:
        return "\n".join(f"{e.title}\n{e.description}\n" + "\n".join(f"{f.name}\n{f.value}" for f in e.fields) for e in self.embeds)


def member(discord_id: int) -> SimpleNamespace:
    return SimpleNamespace(id=discord_id, avatar=None)


@pytest.fixture
def directory() -> FakeDirectory:
    return FakeDirectory()


@pytest.fixture
def env(monkeypatch, repo, directory):
    """指令與 with_identity 都走同一個解析器（假的 auth server＋真實 DB）。"""
    resolver = IdentityResolver(directory, repo, TTL)
    monkeypatch.setattr(checks, "resolve_identity", resolver.resolve)
    monkeypatch.setattr(user_cog, "resolve_identity", resolver.resolve)
    monkeypatch.setattr(user_cog, "sclient", SimpleNamespace(sqldb=repo))
    return SimpleNamespace(repo=repo, directory=directory)


def run(ctx: FakeCtx, target=None):
    cog = user_cog.system_user(SimpleNamespace())
    asyncio.run(user_cog.system_user.user_info.callback(cog, ctx, target))
    return ctx


class TestUserInfoCommand:
    def test_temporary_user_shows_unregistered_without_any_id(self, env):
        ctx = run(FakeCtx())

        record = env.repo.get_discord_identity(CALLER)
        assert record is not None and not record.is_formal
        assert "析域帳號\n未註冊" in ctx.account_text
        assert str(record.user_id) not in ctx.all_text
        assert "Cloud ID" not in ctx.all_text

    def test_formal_user_shows_username(self, env):
        env.directory.accounts[CALLER] = _account(username="citizen-a")
        ctx = run(FakeCtx())

        assert "析域帳號\ncitizen-a" in ctx.account_text
        assert "未註冊" not in ctx.account_text

    def test_linked_accounts_and_other_discord_accounts(self, env):
        account = _account()
        env.directory.accounts[CALLER] = account
        env.directory.accounts[OTHER] = account
        env.repo.upsert_linked_account(account.account_id, PlatformType.Minecraft, "mc-1", "Steve")
        env.repo.upsert_linked_account(account.account_id, PlatformType.Twitch, "tw-1", "streamer")
        env.repo.upsert_linked_account(account.account_id, PlatformType.Google, "g-1", "a@gmail.com")
        env.repo.upsert_linked_account(uuid4(), PlatformType.Minecraft, "mc-other", "NotMine")
        # OTHER 要先有紀錄，bot 才「知道」這個 Discord 帳號
        run(FakeCtx(OTHER))

        text = run(FakeCtx()).account_text

        assert "Minecraft：Steve" in text
        assert "Twitch：streamer" in text
        assert "Google：a@gmail.com" in text
        assert f"Discord：<@{OTHER}>" in text
        assert f"<@{CALLER}>" not in text  # 被查的帳號自己不列
        assert "NotMine" not in text

    def test_no_bindings_has_no_bound_section(self, env):
        assert "綁定的帳號" not in run(FakeCtx()).account_text

    def test_drive_share_status(self, env):
        account = _account()
        env.directory.accounts[CALLER] = account
        assert "雲端共用資料夾\n未共用" in run(FakeCtx()).account_text

        env.repo.merge(DriveShare(user_id=account.account_id, gmail="a@gmail.com", share_id="perm1"))
        assert "雲端共用資料夾\n已共用" in run(FakeCtx()).account_text

    def test_query_other_shows_their_data_not_callers(self, env):
        caller_acc, target_acc = _account(username="caller"), _account(username="target")
        env.directory.accounts[CALLER] = caller_acc
        env.directory.accounts[TARGET] = target_acc
        env.repo.upsert_linked_account(caller_acc.account_id, PlatformType.Minecraft, "mc-caller", "CallerMC")
        env.repo.upsert_linked_account(target_acc.account_id, PlatformType.Minecraft, "mc-target", "TargetMC")

        text = run(FakeCtx(), member(TARGET)).account_text

        assert "target" in text and "TargetMC" in text
        assert "caller" not in text and "CallerMC" not in text

    def test_query_never_seen_user_shows_unregistered_and_creates_no_record(self, env):
        ctx = run(FakeCtx(), member(TARGET))

        assert "析域帳號\n未註冊" in ctx.account_text
        assert env.repo.get_discord_identity(TARGET) is None
        assert env.repo.get_discord_identity(CALLER) is not None  # 呼叫者自己照 with_identity 拿到 ID

    def test_query_other_when_directory_down_shows_unavailable_but_keeps_discord_data(self, env):
        run(FakeCtx())  # 呼叫者先有紀錄
        env.directory.unavailable = True
        ctx = run(FakeCtx(), member(TARGET))

        assert "身分服務暫時無法連線" in ctx.account_text
        assert "未註冊" not in ctx.account_text
        assert len(ctx.embeds) == 2  # Discord 資料區塊仍然顯示
        assert env.repo.get_discord_identity(TARGET) is None

    def test_suspended_caller_is_blocked(self, env):
        env.directory.accounts[CALLER] = _account(suspended=True)
        ctx = run(FakeCtx())

        assert ctx.responses[-1].content == checks.SUSPENDED_MESSAGE
        assert not hasattr(ctx.responses[-1], "embeds")

    def test_suspended_target_is_still_viewable(self, env):
        env.directory.accounts[TARGET] = _account(username="target", suspended=True)
        ctx = run(FakeCtx(), member(TARGET))

        assert "析域帳號\ntarget" in ctx.account_text

    def test_link_code_command_removed(self):
        assert not hasattr(user_cog.system_user, "link_code")
