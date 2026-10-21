"""停權的人不能用需要使用者 ID 的功能：with_identity、歌單 autocomplete、音樂面板歌單按鈕。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from starDiscord import checks
from starDiscord.cmds import music
from starDiscord.uiElement import music_panel
from starlib.identity import BotIdentity, IdentityResolver, IdentityUnavailable
from test_identity import DISCORD_ID, TTL, FakeDirectory, _account, expire, repo  # noqa: F401  (repo 為 fixture)


def _identity(*, suspended=False) -> BotIdentity:
    return BotIdentity(user_id=uuid4(), is_formal=True, username="citizen", roles=(), suspended=suspended)


def _patch(monkeypatch, module, result):
    calls = []

    async def fake(discord_id, *, create=True):
        calls.append((discord_id, create))
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(module, "resolve_identity", fake)
    return calls


class TestWithIdentity:
    @staticmethod
    def _run():
        body = AsyncMock(return_value="done")
        wrapped = checks.with_identity()(body)
        ctx = SimpleNamespace(author=SimpleNamespace(id=1), respond=AsyncMock())
        result = asyncio.run(wrapped(None, ctx))
        return body, ctx, result

    def test_suspended_is_blocked(self, monkeypatch):
        _patch(monkeypatch, checks, _identity(suspended=True))
        body, ctx, result = self._run()
        body.assert_not_awaited()
        ctx.respond.assert_awaited_once_with("你的析域帳號已停權，無法使用此功能", ephemeral=True)
        assert result is None

    def test_not_suspended_passes(self, monkeypatch):
        identity = _identity()
        _patch(monkeypatch, checks, identity)
        body, ctx, result = self._run()
        body.assert_awaited_once()
        ctx.respond.assert_not_awaited()
        assert ctx.identity is identity
        assert result == "done"

    def test_unavailable_still_asks_to_retry(self, monkeypatch):
        _patch(monkeypatch, checks, IdentityUnavailable())
        body, ctx, _ = self._run()
        body.assert_not_awaited()
        ctx.respond.assert_awaited_once_with("身分服務暫時無法連線，請稍後再試", ephemeral=True)

    def test_message_constant(self):
        assert checks.SUSPENDED_MESSAGE == "你的析域帳號已停權，無法使用此功能"


class TestAutocomplete:
    @staticmethod
    def _ctx():
        return SimpleNamespace(interaction=SimpleNamespace(user=SimpleNamespace(id=1)), value="")

    def test_suspended_returns_empty_without_db(self, monkeypatch):
        _patch(monkeypatch, music, _identity(suspended=True))
        monkeypatch.setattr(music.sqldb, "get_music_playlists", lambda *_: pytest.fail("不該查歌單"))
        assert asyncio.run(music._playlist_name_autocomplete(self._ctx())) == []

    def test_normal_returns_names(self, monkeypatch):
        _patch(monkeypatch, music, _identity())
        monkeypatch.setattr(music.sqldb, "get_music_playlists", lambda *_: [SimpleNamespace(name="A"), SimpleNamespace(name="B")])
        assert asyncio.run(music._playlist_name_autocomplete(self._ctx())) == ["A", "B"]


class TestPanelPlaylists:
    @staticmethod
    def _run(monkeypatch, result):
        _patch(monkeypatch, music_panel, result)
        interaction = SimpleNamespace(user=SimpleNamespace(id=1), response=SimpleNamespace(send_message=AsyncMock()), message=None)
        panel = object.__new__(music_panel.MusicPanelView)
        asyncio.run(panel._open_playlists(interaction))
        return interaction.response.send_message

    def test_suspended_is_blocked(self, monkeypatch):
        monkeypatch.setattr(music_panel.sqldb, "get_music_playlists", lambda *_: pytest.fail("不該查歌單"))
        send = self._run(monkeypatch, _identity(suspended=True))
        send.assert_awaited_once_with("你的析域帳號已停權，無法使用此功能", ephemeral=True)

    def test_normal_without_playlists_gets_hint(self, monkeypatch):
        monkeypatch.setattr(music_panel.sqldb, "get_music_playlists", lambda *_: [])
        send = self._run(monkeypatch, _identity())
        assert "還沒有歌單" in send.await_args.args[0]


class TestSuspensionLifecycle:
    """真的 IdentityResolver 加假 directory 串 with_identity：TTL 內放行、過期後被擋、解除後恢復且資料還在"""

    @staticmethod
    def _call(monkeypatch, resolver):
        async def real_resolve(discord_id, *, create=True):
            return await resolver.resolve(discord_id, create=create)

        monkeypatch.setattr(checks, "resolve_identity", real_resolve)
        body = AsyncMock(return_value="done")
        ctx = SimpleNamespace(author=SimpleNamespace(id=DISCORD_ID), respond=AsyncMock())
        asyncio.run(checks.with_identity()(body)(None, ctx))
        return body, ctx

    def test_suspend_then_unsuspend(self, monkeypatch, repo):
        directory = FakeDirectory()
        resolver = IdentityResolver(directory, repo, TTL)
        account = _account(suspended=False)
        directory.accounts[DISCORD_ID] = account

        body, _ = self._call(monkeypatch, resolver)
        body.assert_awaited_once()
        playlist = repo.create_music_playlist(account.account_id, "A")

        # auth server 已停權，但 TTL 內仍用舊紀錄放行，也不會再打 auth server
        directory.accounts[DISCORD_ID] = _account(account.account_id, suspended=True)
        body, ctx = self._call(monkeypatch, resolver)
        body.assert_awaited_once()
        ctx.respond.assert_not_awaited()
        assert directory.calls == 1

        # TTL 過期後的下一次使用被擋
        expire(repo)
        body, ctx = self._call(monkeypatch, resolver)
        body.assert_not_awaited()
        ctx.respond.assert_awaited_once_with(checks.SUSPENDED_MESSAGE, ephemeral=True)

        # 解除停權，過期後恢復，歌單還在
        directory.accounts[DISCORD_ID] = _account(account.account_id, suspended=False)
        expire(repo)
        body, ctx = self._call(monkeypatch, resolver)
        body.assert_awaited_once()
        ctx.respond.assert_not_awaited()
        assert repo.get_music_playlist(account.account_id, "A").id == playlist.id
