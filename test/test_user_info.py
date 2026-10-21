"""/user_info 顯示析域帳號狀態：repository（真實 PostgreSQL，交易結束後 rollback）與指令 callback（假的 auth server）。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_identity import TTL, FakeDirectory, _account, expire, repo  # noqa: F401  (repo 為 fixture)

from starDiscord import checks
from starDiscord.cmds import system_user as user_cog
from starlib.database import DiscordIdentity, DriveShare, LinkedAccount, PlatformType
from starlib.identity import IdentityResolver, LinkedPassport
from starlib.identity import twitch as twitch_module
from starlib.utils import nowtz

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
        self.deferred = False
        self.events: list[str] = []

    async def defer(self, **kwargs):
        self.deferred = True
        self.events.append("defer")

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
    # 即時查 Twitch 走真實的 fetch_twitch_passports，只把解析器換成用假 auth server 的那個
    monkeypatch.setattr(twitch_module, "_get_default", lambda: resolver)
    return SimpleNamespace(repo=repo, directory=directory, resolver=resolver)


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
        account = _account(twitch_passports=(LinkedPassport("tw-1", "streamer"),))
        env.directory.accounts[CALLER] = account
        env.directory.accounts[OTHER] = account
        env.repo.upsert_linked_account(account.account_id, PlatformType.Minecraft, "mc-1", "Steve")
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

    def test_command_defers_before_slow_lookups(self, env, monkeypatch):
        env.directory.accounts[CALLER] = _account(twitch_passports=(LinkedPassport("1", "streamer"),))
        run(FakeCtx())  # 先有紀錄，之後 TTL 內解析不查 auth server，Twitch 才會走即時查
        ctx = FakeCtx()
        original = user_cog.fetch_twitch_passports

        async def spy_fetch(discord_id):
            ctx.events.append("fetch_twitch")
            return await original(discord_id)

        monkeypatch.setattr(user_cog, "fetch_twitch_passports", spy_fetch)

        run(ctx)

        assert ctx.deferred
        assert ctx.events == ["defer", "fetch_twitch"]

    def test_expired_ttl_reuses_twitch_from_same_resolution(self, env):
        env.directory.accounts[CALLER] = _account(twitch_passports=(LinkedPassport("1", "streamer"),))

        ctx = run(FakeCtx())

        assert "Twitch：streamer" in ctx.account_text
        assert env.directory.calls == 1  # 解析時已查到，不再為 Twitch 查第二次

    def test_directory_down_backoff_is_shared_with_twitch_lookup(self, env):
        env.directory.accounts[CALLER] = _account(twitch_passports=(LinkedPassport("1", "streamer"),))
        run(FakeCtx())
        expire(env.repo, CALLER)
        env.directory.unavailable = True
        calls = env.directory.calls

        ctx = run(FakeCtx())

        assert "Twitch" not in ctx.account_text
        assert env.directory.calls == calls + 1  # 解析連不上後，Twitch 即時查直接略過，不再等一次逾時

    def test_suspended_target_twitch_is_hidden(self, env):
        env.directory.accounts[TARGET] = _account(username="target", suspended=True, twitch_passports=(LinkedPassport("2", "targetTV"),))

        first = run(FakeCtx(), member(TARGET)).account_text  # 解析時剛查到
        second = run(FakeCtx(), member(TARGET)).account_text  # TTL 內走即時查

        assert "析域帳號\ntarget" in first
        assert "targetTV" not in first and "targetTV" not in second

    def test_multiple_twitch_passports_listed_in_auth_server_order(self, env):
        env.directory.accounts[CALLER] = _account(twitch_passports=(LinkedPassport("2", "second"), LinkedPassport("1", "first")))

        assert "Twitch：second\nTwitch：first" in run(FakeCtx()).account_text

    def test_twitch_without_username_shows_subject(self, env):
        env.directory.accounts[CALLER] = _account(twitch_passports=(LinkedPassport("689775663", None),))

        assert "Twitch：689775663" in run(FakeCtx()).account_text

    def test_query_other_shows_their_twitch_not_callers(self, env):
        env.directory.accounts[CALLER] = _account(twitch_passports=(LinkedPassport("1", "callerTV"),))
        env.directory.accounts[TARGET] = _account(username="target", twitch_passports=(LinkedPassport("2", "targetTV"),))

        text = run(FakeCtx(), member(TARGET)).account_text

        assert "Twitch：targetTV" in text
        assert "callerTV" not in text

    def test_twitch_reflects_link_and_unlink_immediately(self, env):
        account = _account()
        env.directory.accounts[CALLER] = account
        assert "Twitch" not in run(FakeCtx()).account_text

        env.directory.accounts[CALLER] = _account(account.account_id, twitch_passports=(LinkedPassport("1", "streamer"),))
        assert "Twitch：streamer" in run(FakeCtx()).account_text  # 不必等 TTL 過期

        env.directory.accounts[CALLER] = _account(account.account_id)
        assert "Twitch" not in run(FakeCtx()).account_text

    def test_twitch_omitted_when_directory_down_but_rest_shown(self, env):
        account = _account(username="citizen-a", twitch_passports=(LinkedPassport("1", "streamer"),))
        env.directory.accounts[CALLER] = account
        env.repo.upsert_linked_account(account.account_id, PlatformType.Minecraft, "mc-1", "Steve")
        run(FakeCtx())  # 先有紀錄，TTL 內解析不打 auth server
        env.directory.unavailable = True

        ctx = run(FakeCtx())

        assert "Twitch" not in ctx.account_text
        assert "析域帳號\ncitizen-a" in ctx.account_text
        assert "Minecraft：Steve" in ctx.account_text
        assert len(ctx.embeds) == 2

    def test_temporary_user_has_no_twitch_row_and_no_lookup(self, env):
        run(FakeCtx())  # 建立臨時 ID 紀錄
        calls = env.directory.calls

        ctx = run(FakeCtx())

        assert "Twitch" not in ctx.account_text
        assert env.directory.calls == calls  # 臨時使用者不是域民，不查 auth server

    def test_leftover_linked_account_twitch_row_is_hidden(self, env):
        account = _account()
        env.directory.accounts[CALLER] = account
        # 上線前留下的舊資料，直接寫表模擬
        env.repo.session.add(LinkedAccount(user_id=account.account_id, platform=PlatformType.Twitch, external_id="tw-old", display_name="oldstreamer"))
        env.repo.commit()
        env.repo.upsert_linked_account(account.account_id, PlatformType.Minecraft, "mc-1", "Steve")

        text = run(FakeCtx()).account_text

        assert "Twitch" not in text and "oldstreamer" not in text
        assert "Minecraft：Steve" in text

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
