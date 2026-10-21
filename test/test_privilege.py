"""管理員權限由 auth server 身分組決定：privilege_of、PRIVILEGE_ROLES 驗證、has_privilege_level 與 check_any 的組合。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import discord
import pytest
from discord.ext import commands
from pydantic import ValidationError

from starDiscord import checks
from starlib import settings as settings_module
from starlib.database import PrivilegeLevel
from starlib.identity import BotIdentity, IdentityUnavailable, privilege_of


def _identity(roles=(), *, is_formal=True, suspended=False) -> BotIdentity:
    return BotIdentity(user_id=uuid4(), is_formal=is_formal, username="citizen" if is_formal else None, roles=tuple(roles), suspended=suspended)


@pytest.fixture
def role_map(monkeypatch):
    mapping = {"mod": 1, "admin": 2, "owner": 3}
    monkeypatch.setattr(settings_module.get_settings(), "PRIVILEGE_ROLES", mapping)
    return mapping


class TestPrivilegeOf:
    def test_mapped_role(self, role_map):
        assert privilege_of(_identity(["admin"])) == PrivilegeLevel.Level2

    def test_highest_of_multiple(self, role_map):
        assert privilege_of(_identity(["mod", "owner", "admin"])) == PrivilegeLevel.Level3

    def test_unmapped_role_is_user(self, role_map):
        assert privilege_of(_identity(["member"])) == PrivilegeLevel.User

    def test_empty_mapping_is_user(self, monkeypatch):
        monkeypatch.setattr(settings_module.get_settings(), "PRIVILEGE_ROLES", {})
        assert privilege_of(_identity(["admin"])) == PrivilegeLevel.User

    def test_temporary_is_user(self, role_map):
        assert privilege_of(_identity(["admin"], is_formal=False)) == PrivilegeLevel.User

    def test_suspended_is_user(self, role_map):
        assert privilege_of(_identity(["admin"], suspended=True)) == PrivilegeLevel.User

    def test_none_is_user(self, role_map):
        assert privilege_of(None) == PrivilegeLevel.User


class TestPrivilegeRolesSetting:
    @staticmethod
    def _build(roles):
        base = settings_module.get_settings().model_dump()
        base["PRIVILEGE_ROLES"] = roles
        return settings_module.AppSettings(**base)

    def test_default_is_empty(self, monkeypatch):
        monkeypatch.delenv("PRIVILEGE_ROLES", raising=False)
        base = settings_module.get_settings().model_dump()
        base.pop("PRIVILEGE_ROLES")
        assert settings_module.AppSettings(_env_file=None, **base).PRIVILEGE_ROLES == {}

    def test_valid(self):
        assert self._build({"some-role": 2, "a": 0}).PRIVILEGE_ROLES == {"some-role": 2, "a": 0}

    @pytest.mark.parametrize("roles", [{"r": 9}, {"r": -1}, {"Admin": 1}, {"-x": 1}, {"a" * 65: 1}, {"": 1}, {"a_b": 1}])
    def test_invalid(self, roles):
        with pytest.raises(ValidationError):
            self._build(roles)

    def test_valid_values_match_enum(self):
        assert settings_module.VALID_PRIVILEGE_VALUES == {int(level) for level in PrivilegeLevel}

    def test_json_from_env(self, monkeypatch):
        monkeypatch.setenv("PRIVILEGE_ROLES", '{"some-role": 2}')
        base = settings_module.get_settings().model_dump()
        base.pop("PRIVILEGE_ROLES")
        assert settings_module.AppSettings(_env_file=None, **base).PRIVILEGE_ROLES == {"some-role": 2}


class TestHasPrivilegeLevel:
    @staticmethod
    def _ctx(*, manage_channels=False):
        author = SimpleNamespace(id=123, guild_permissions=discord.Permissions(manage_channels=manage_channels))
        return SimpleNamespace(author=author, guild=object())

    @staticmethod
    def _patch(monkeypatch, result):
        calls = []

        async def fake(discord_id, *, create=True):
            calls.append((discord_id, create))
            if isinstance(result, Exception):
                raise result
            return result

        monkeypatch.setattr(checks, "resolve_identity", fake)
        return calls

    def _run(self, predicate, ctx):
        return asyncio.run(predicate(ctx))

    def test_allows_enough_level_and_never_creates(self, role_map, monkeypatch):
        calls = self._patch(monkeypatch, _identity(["admin"]))
        assert self._run(checks.has_privilege_level(PrivilegeLevel.Level2).predicate, self._ctx()) is True
        assert calls == [(123, False)]

    def test_denies_lower_level(self, role_map, monkeypatch):
        self._patch(monkeypatch, _identity(["mod"]))
        with pytest.raises(checks.PrivilegeError):
            self._run(checks.has_privilege_level(PrivilegeLevel.Level2).predicate, self._ctx())

    @pytest.mark.parametrize("result", [None, IdentityUnavailable(), _identity(["admin"], is_formal=False), _identity(["admin"], suspended=True)])
    def test_everyone_else_is_user(self, role_map, monkeypatch, result):
        self._patch(monkeypatch, result)
        with pytest.raises(checks.PrivilegeError):
            self._run(checks.has_privilege_level(PrivilegeLevel.Level1).predicate, self._ctx())

    def test_privilege_error_is_check_failure_and_command_error(self):
        assert issubclass(checks.PrivilegeError, commands.CheckFailure)
        assert issubclass(checks.PrivilegeError, discord.ApplicationCommandError)

    @pytest.mark.parametrize(
        ("identity", "manage_channels", "allowed"),
        [
            (_identity(["admin"]), False, True),  # 只有權限等級
            (None, True, True),  # 只有 manage_channels：privilege 檢查不能提前擋掉
            (_identity(["admin"]), True, True),
            (None, False, False),
        ],
    )
    def test_check_any_is_or(self, role_map, monkeypatch, identity, manage_channels, allowed):
        self._patch(monkeypatch, identity)
        combined = commands.check_any(checks.has_privilege_level(PrivilegeLevel.Level2), commands.has_guild_permissions(manage_channels=True))
        ctx = self._ctx(manage_channels=manage_channels)
        if allowed:
            assert self._run(combined.predicate, ctx) is True
        else:
            with pytest.raises(commands.CheckAnyFailure):
                self._run(combined.predicate, ctx)
