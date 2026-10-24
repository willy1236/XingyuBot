"""VPN、NetBird、雲端資料夾綁定：repository（真實 PostgreSQL，交易結束後 rollback）與改用 with_identity 的指令 callback。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from starDiscord import checks
from starDiscord.cmds import command as command_cog
from starDiscord.cmds import system_game as game_cog
from starlib import sqldb
from starlib.database import DriveShare, LinkedAccount, NetBirdBinding, PlatformType, UserIPDetails
from starlib.database.postgresql.client import SQLRepository
from starlib.identity import BotIdentity, IdentityUnavailable
from starlib.utils import nowtz

# ─── Repository ─────────────────────────────────────────────────────────────


@pytest.fixture
def repo():
    """綁在外層交易上的 repository，repository 內的 commit 只會提交 savepoint，測試結束整個 rollback。"""
    connection = sqldb.engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    repository = SQLRepository(sqldb.engine, session)
    try:
        yield repository
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def user_id() -> UUID:
    return uuid4()


class TestLinkedAccountTable:
    def test_unique_user_platform_blocks_duplicates(self, repo, user_id):
        repo.session.add(LinkedAccount(user_id=user_id, platform=PlatformType.Minecraft, external_id="a"))
        repo.session.flush()
        repo.session.add(LinkedAccount(user_id=user_id, platform=PlatformType.Minecraft, external_id="b"))
        with pytest.raises(IntegrityError):
            repo.session.flush()


class TestNetBirdAndDriveRepository:
    def test_netbird_binding_by_uuid(self, repo, user_id):
        assert repo.get_netbird_binding(user_id) is None
        repo.merge(NetBirdBinding(user_id=user_id, group_id="g1", group_name=f"user-{user_id}", updated_at=nowtz()))

        assert repo.get_netbird_binding(user_id).group_id == "g1"

    def test_drive_share_roundtrip(self, repo, user_id):
        assert repo.get_drive_share(user_id) is None
        repo.merge(DriveShare(user_id=user_id, gmail="a@gmail.com", share_id="perm1"))
        assert repo.get_drive_share(user_id).share_id == "perm1"

        repo.remove_drive_share(user_id)
        repo.remove_drive_share(user_id)  # 沒有也不報錯
        assert repo.get_drive_share(user_id) is None


# ─── 指令 callback ──────────────────────────────────────────────────────────

GAME = game_cog.system_game
DRIVE_COG = next(v for v in vars(command_cog).values() if isinstance(v, type) and "drive" in vars(v))


class FakeCtx:
    def __init__(self, discord_id: int = 900000000000000002):
        self.author = SimpleNamespace(id=discord_id, mention=f"<@{discord_id}>")
        self.responses: list[SimpleNamespace] = []

    async def defer(self, **kwargs):
        pass

    async def respond(self, content=None, **kwargs):
        self.responses.append(SimpleNamespace(content=content, **kwargs))
        return SimpleNamespace(content=content)

    @property
    def text(self) -> str:
        return "\n".join(str(r.content) for r in self.responses)


async def _report(*args, **kwargs):
    pass


def make_cog(cls):
    return cls(SimpleNamespace(report=_report))


def call(command, cog, ctx, *args, **kwargs):
    return asyncio.run(command.callback(cog, ctx, *args, **kwargs))


@pytest.fixture
def temp_identity(monkeypatch, user_id):
    """沒註冊的人：resolve_identity 回臨時 ID（is_formal=False）。"""
    identity = BotIdentity(user_id=user_id, is_formal=False, username=None, roles=(), suspended=False)

    async def fake_resolve(discord_id, *, create=True):
        return identity

    monkeypatch.setattr(checks, "resolve_identity", fake_resolve)
    return identity


@pytest.fixture
def cog_repo(monkeypatch, repo):
    """指令內的 sclient.sqldb 換成綁外層交易的 repository。"""
    fake = SimpleNamespace(sqldb=repo)
    monkeypatch.setattr(game_cog, "sclient", fake)
    monkeypatch.setattr(command_cog, "sclient", fake)
    return repo


class FakeNetBirdAPI:
    def __init__(self):
        self.created = []

    def get_group(self, group_id):
        return {"id": group_id}

    def find_group_by_name(self, name):
        return None

    def create_group(self, name):
        self.created.append(name)
        return {"id": "grp-1", "name": name}

    def create_setup_key(self, name, auto_groups):
        return {"id": "key-1", "key": "SETUPKEY"}

    def get_peers_in_group(self, group_id):
        return [{"name": "pc", "ip": "100.64.0.1", "connected": True, "last_seen": "2026-01-01T00:00:00Z", "os": "Windows", "version": "0.1"}]


class TestNetBirdCommands:
    def test_setup_then_query_for_unregistered(self, monkeypatch, cog_repo, temp_identity):
        api = FakeNetBirdAPI()
        monkeypatch.setattr(game_cog, "NetBirdAPI", lambda: api)

        ctx = FakeCtx()
        call(GAME.netbird_setup, make_cog(GAME), ctx)
        assert "SETUPKEY" in ctx.text
        assert api.created == [f"user-{temp_identity.user_id}"]
        assert cog_repo.get_netbird_binding(temp_identity.user_id).group_id == "grp-1"

        ctx = FakeCtx()
        call(GAME.netbird, make_cog(GAME), ctx)
        assert ctx.responses[-1].content == "查詢成功"
        assert "100.64.0.1" in ctx.responses[-1].embed.fields[0].value

    def test_query_without_binding(self, cog_repo, temp_identity):
        ctx = FakeCtx()
        call(GAME.netbird, make_cog(GAME), ctx)
        assert "尚未綁定NetBird" in ctx.text


def test_minecraft_set_command_removed():
    """Minecraft 綁定改由 auth server 管理，bot 不再提供設定指令"""
    assert not hasattr(GAME, "minecraft_set")
    assert not hasattr(GAME, "minecraft_cmd")


class TestVpnCommand:
    """vpn 只用 Discord ID，不掛身分 decorator：不需要 identity，auth server 連不上也照常運作。"""

    @pytest.fixture(autouse=True)
    def identity_must_not_be_resolved(self, monkeypatch):
        async def boom(discord_id, *, create=True):
            raise AssertionError("vpn 不應該解析身分")

        monkeypatch.setattr(checks, "resolve_identity", boom)

    def test_vpn_with_records(self, monkeypatch, cog_repo):
        now = nowtz()
        record = UserIPDetails(ip="26.0.0.1", last_seen=now, discord_id=1, registration_at=now)
        monkeypatch.setattr(cog_repo, "get_user_ip_details", lambda discord_id: [record])

        ctx = FakeCtx()
        call(GAME.vpn, make_cog(GAME), ctx)
        assert ctx.responses[-1].content == "查詢成功"

    def test_vpn_without_records(self, monkeypatch, cog_repo):
        monkeypatch.setattr(cog_repo, "get_user_ip_details", lambda discord_id: [])
        ctx = FakeCtx()
        call(GAME.vpn, make_cog(GAME), ctx)
        assert "查無登記資料" in ctx.text


class TestIdentityUnavailable:
    def test_identity_unavailable_stops_before_command(self, monkeypatch, cog_repo):
        async def down(discord_id, *, create=True):
            raise IdentityUnavailable()

        monkeypatch.setattr(checks, "resolve_identity", down)
        ctx = FakeCtx()
        call(GAME.netbird, make_cog(GAME), ctx)
        assert "暫時無法連線" in ctx.text


@pytest.mark.parametrize("command", [GAME.netbird_setup, GAME.netbird, DRIVE_COG.drive])
def test_commands_use_with_identity(command):
    """靜態斷言：decorator 已換成 with_identity，不再走 ensure_registered。"""
    wrapper_code = command.callback.__code__
    assert wrapper_code.co_filename.endswith("checks.py")
    assert "resolve_identity" in wrapper_code.co_names
    assert "RegisterView" not in wrapper_code.co_names


@pytest.mark.parametrize("command", [GAME.radmin, GAME.zerotier, GAME.vpn])
def test_discord_id_only_commands_have_no_identity_decorator(command):
    """靜態斷言：只用 Discord ID 的指令不掛任何身分 decorator，停權或 auth server 異常都不影響。"""
    code = command.callback.__code__
    assert not code.co_filename.endswith("checks.py")
    assert "resolve_identity" not in code.co_names
    assert "RegisterView" not in code.co_names


class TestDriveCommand:
    @pytest.fixture
    def google(self, monkeypatch):
        calls = SimpleNamespace(added=[], removed=[])

        class FakeGoogle:
            def add_file_permissions(self, file_id, email):
                calls.added.append(email)
                return {"id": "perm-1"}

            def remove_file_permissions(self, file_id, share_id):
                calls.removed.append(share_id)

        monkeypatch.setattr(command_cog, "XingyuGoogleCloud", FakeGoogle)
        return calls

    def test_set_then_remove_for_unregistered(self, cog_repo, temp_identity, google):
        cog = make_cog(DRIVE_COG)
        call(DRIVE_COG.drive, cog, FakeCtx(), "someone")
        assert google.added == ["someone@gmail.com"]
        share = cog_repo.get_drive_share(temp_identity.user_id)
        assert (share.gmail, share.share_id) == ("someone@gmail.com", "perm-1")

        ctx = FakeCtx()
        call(DRIVE_COG.drive, cog, ctx, "other")
        assert "已經共用" in ctx.text
        assert google.added == ["someone@gmail.com"]

        ctx = FakeCtx()
        call(DRIVE_COG.drive, cog, ctx, None)
        assert "移除完成" in ctx.text
        assert google.removed == ["perm-1"]
        assert cog_repo.get_drive_share(temp_identity.user_id) is None

    def test_remove_without_setting(self, cog_repo, temp_identity, google):
        ctx = FakeCtx()
        call(DRIVE_COG.drive, make_cog(DRIVE_COG), ctx, None)
        assert "沒有設定過" in ctx.text
        assert google.removed == []
