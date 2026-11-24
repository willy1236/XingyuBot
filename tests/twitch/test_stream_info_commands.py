"""C-08：聊天室的 `!title`、`!game`、`!uptime`。

指令以 `twitch_chatbot.run()` 註冊的名稱觸發（`title`、`game`、`uptime`）；Helix 在 HTTP 層以有狀態的替身取代，真的 `BotTwitch` 走完 SDK。
實況主 token 與 AutoMod 檢查換成替身。回覆文字卡片只定了語意，測試只比對「權限不足」「過長」「修改失敗」「找不到」「未開台」「標題已更新」「重新授權」這些關鍵詞。
"""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import text
from twitchAPI import twitch as sdk
from twitchAPI.type import AuthScope

from starlib import twitch_audit, twitch_tokens
from starlib.database import APIType, OAuthToken, TwitchBotJoinChannel
from starlib.twitch_audit import list_changes
from starServer.twitch_bot import speech, state
from starServer.twitch_bot.helix import BotTwitch
from tests.dashboard.test_channel_moderation import (
    BOT,
    channel_id,  # noqa: F401 (fixture)
    host,  # noqa: F401 (fixture)
    start_chat,  # noqa: F401 (fixture)
)

SCOPE = "channel:manage:broadcast"
OLD_TITLE = "原本的標題"
OLD_GAME = "Just Chatting"
NEW_TITLE = "新標題 abc"


class StubTwitch:
    """Helix `channels`（GET／PATCH）與 `search/categories` 的替身；頻道的標題與分類存在記憶體。"""

    def __init__(self):
        self.title = OLD_TITLE
        self.game_id, self.game_name = "509658", OLD_GAME
        #: 搜尋結果：關鍵字 -> [(id, name)]
        self.categories: dict[str, list[tuple[str, str]]] = {}
        self.requests: list[tuple[str, str, dict]] = []
        self.patch_status: int | None = None

    def patches(self):
        return [params for method, _, params in self.requests if method == "PATCH"]

    async def request(self, method, url, **kwargs):
        query = {key: values[0] for key, values in parse_qs(urlsplit(url).query).items()}
        query.update(kwargs.get("params") or {})
        body = kwargs.get("json") or {}
        params = {**query, **body}
        self.requests.append((method, url, params))
        path = urlsplit(url).path
        if method == "PATCH" and self.patch_status is not None:
            payload = {"error": "x", "status": self.patch_status, "message": "x"}
            return self._reply(self.patch_status, payload)
        if path.endswith("/search/categories"):
            found = self.categories.get(params["query"], [])
            return self._reply(200, {"data": [{"id": i, "name": n, "box_art_url": ""} for i, n in found]})
        if method == "PATCH":
            if "title" in params:
                self.title = params["title"]
            if "game_id" in params:
                self.game_id = params["game_id"]
                self.game_name = next(
                    (n for found in self.categories.values() for i, n in found if i == self.game_id), self.game_name
                )
            return self._reply(204, {})
        return self._reply(200, {"data": [self._channel(params["broadcaster_id"])]})

    def _channel(self, broadcaster_id):
        return {
            "broadcaster_id": broadcaster_id,
            "broadcaster_login": "host",
            "broadcaster_name": "Host",
            "broadcaster_language": "zh",
            "game_id": self.game_id,
            "game_name": self.game_name,
            "title": self.title,
            "delay": 0,
            "tags": [],
            "content_classification_labels": [],
            "is_branded_content": False,
        }

    @staticmethod
    def _reply(status, payload):
        return SimpleNamespace(status=status, headers={"Ratelimit-Reset": "0"}, json=AsyncMock(return_value=payload))


class Env(SimpleNamespace):
    """測試用的聊天室環境：stub（Helix）、chat（指令 harness）、automod（AutoMod 檢查結果）。"""

    def say(self, command, parameter="", *, uid="100", mod=False, broadcaster=False):
        assert command in self.chat.commands, f"!{command} 尚未註冊"
        user_id = self.channel_id if broadcaster else uid
        cmd = SimpleNamespace(
            parameter=parameter,
            room=self.chat.room,
            user=SimpleNamespace(id=user_id, name="user", display_name="User", mod=mod, vip=False, subscriber=False),
            reply=AsyncMock(),
        )
        asyncio.run(self.chat.commands[command](cmd))
        sent = [call.args[0] for call in cmd.reply.await_args_list]
        return sent + [message for _, message in self.chat.notices]


def _seed_token(repo, channel_id, scope):
    credential = repo.get_oauth_client(APIType.Twitch, twitch_tokens.BROADCASTER_CLIENT_SEQ).credential_id
    repo.merge(
        OAuthToken(
            user_id=channel_id,
            client_credential_id=credential,
            access_token="broadcaster-token",
            refresh_token="refresh",
            scope=scope,
            expires_at=datetime.now(UTC) + timedelta(hours=2),
        )
    )


@pytest.fixture
def env(monkeypatch, repo, host, channel_id, start_chat):
    stub = StubTwitch()

    class Session:
        def __init__(self, **_options):
            pass

        async def __aenter__(self):
            return SimpleNamespace(request=stub.request)

        async def __aexit__(self, *_exc):
            pass

    monkeypatch.setattr(sdk, "ClientSession", Session)
    client = BotTwitch("test-client", authenticate_app=False)
    scopes = [AuthScope.CHANNEL_MANAGE_BROADCAST]
    asyncio.run(client.set_user_authentication("test-token", scopes, "test-refresh", validate=False))
    client.auto_refresh_auth = False
    chat = start_chat()
    monkeypatch.setattr(state, "twitch", client, raising=False)
    monkeypatch.setattr(state, "bot_user_id", BOT, raising=False)

    # 實況主 token：DB 的 scope 決定有沒有改標題的權限；Helix 的呼叫在替身，不看 token 內容
    for module in ("starServer.twitch_bot.stream_info", "starlib.twitch_stream_info"):
        try:
            monkeypatch.setattr(__import__(module, fromlist=["sqldb"]), "sqldb", repo)
        except ImportError, AttributeError:
            pass
    monkeypatch.setattr(twitch_tokens, "sqldb", repo)
    monkeypatch.setattr(twitch_tokens, "broadcaster_token", AsyncMock(return_value="broadcaster-token"))
    _seed_token(repo, channel_id, [*twitch_tokens.ENABLE_SCOPES, SCOPE])

    automod = AsyncMock(return_value="ok")
    monkeypatch.setattr(speech, "check_text", automod)
    monkeypatch.setattr(speech, "_check_cache", {})
    monkeypatch.setattr(speech, "_channel_info", {})
    monkeypatch.setattr(speech, "_live", {})
    monkeypatch.setattr(twitch_audit, "sqldb", repo)
    return Env(stub=stub, chat=chat, automod=automod, repo=repo, channel_id=channel_id)


def grant_only_enable_scopes(env):
    """模擬沒有重新授權的既有頻道：token 沒有 `channel:manage:broadcast`。"""
    _seed_token(env.repo, env.channel_id, list(twitch_tokens.ENABLE_SCOPES))


def changes(env):
    return [e for e in list_changes(int(env.channel_id)) if e.target_kind == "stream_info"]


def has(replies, *words):
    return any(all(word in message for word in words) for message in replies)


# ── 查看 ──


def test_任何觀眾_title_回覆目前標題(env):
    assert has(env.say("title"), OLD_TITLE)


def test_任何觀眾_game_回覆目前分類(env):
    assert has(env.say("game"), OLD_GAME)


def test_沒開台時_uptime_回覆未開台(env):
    speech.set_offline(int(env.channel_id))
    assert has(env.say("uptime"), "未開台")


def test_開台中_uptime_回覆開台時長(env):
    started = datetime.now(UTC) - timedelta(hours=1, minutes=30, seconds=5)
    speech.set_live(int(env.channel_id), speech.StreamInfo(started_at=started, game=OLD_GAME, title=OLD_TITLE))
    replies = env.say("uptime")
    assert has(replies, "1 小時 30 分")
    assert not has(replies, "未開台")


# ── 修改標題 ──


def test_mod_改標題後_Twitch_的標題變了_並記下來源是聊天室(env):
    env.say("title", NEW_TITLE, mod=True)

    assert env.stub.title == NEW_TITLE
    [entry] = changes(env)
    assert (entry.source, entry.action) == ("chat", "update")
    assert OLD_TITLE in str(entry.before) and NEW_TITLE in str(entry.after)


def test_實況主改標題(env):
    env.say("title", NEW_TITLE, broadcaster=True)
    assert env.stub.title == NEW_TITLE


def test_一般觀眾改標題_標題不變並回覆權限不足(env):
    replies = env.say("title", NEW_TITLE)

    assert has(replies, "權限不足")
    assert env.stub.patches() == [] and env.stub.title == OLD_TITLE
    assert changes(env) == []


def test_mod_協作關閉時_mod_改標題回覆權限不足_查看照常(env):
    row = env.repo.session.get(TwitchBotJoinChannel, int(env.channel_id))
    row.mod_collab_enabled = False
    env.repo.session.flush()

    assert has(env.say("title", NEW_TITLE, mod=True), "權限不足")
    assert env.stub.patches() == [] and env.stub.title == OLD_TITLE
    assert has(env.say("title", mod=True), OLD_TITLE)


def test_標題超過長度上限_標題不變並回覆過長(env):
    replies = env.say("title", "長" * 500, mod=True)

    assert has(replies, "過長")
    assert env.stub.title == OLD_TITLE
    assert changes(env) == []


def test_Twitch_呼叫失敗_回覆修改失敗(env):
    env.stub.patch_status = 500

    replies = env.say("title", NEW_TITLE, mod=True)

    assert has(replies, "修改失敗")
    assert env.stub.title == OLD_TITLE
    assert changes(env) == []


def test_標題通過_AutoMod_時回覆帶新標題(env):
    assert has(env.say("title", NEW_TITLE, mod=True), NEW_TITLE)


@pytest.mark.parametrize("verdict", ["blocked", "unavailable"])
def test_新標題被_AutoMod_擋下或無法檢查_標題照改_回覆不含標題文字(env, verdict):
    env.automod.return_value = verdict

    replies = env.say("title", NEW_TITLE, mod=True)

    assert env.stub.title == NEW_TITLE
    assert has(replies, "標題已更新")
    assert not has(replies, NEW_TITLE)
    assert len(changes(env)) == 1


def test_AutoMod_擋下標題不寫擋下紀錄(env):
    env.automod.return_value = "blocked"

    env.say("title", NEW_TITLE, mod=True)

    count = env.repo.session.execute(
        text("SELECT count(*) FROM stardb_basic.twitch_automod_block WHERE twitch_id = :c"),
        {"c": int(env.channel_id)},
    ).scalar_one()
    assert count == 0


def test_沒有重新授權的既有頻道_改標題回覆需要重新授權_查看照常(env):
    grant_only_enable_scopes(env)

    assert has(env.say("title", NEW_TITLE, mod=True), "重新授權")
    assert env.stub.patches() == [] and env.stub.title == OLD_TITLE
    assert has(env.say("title"), OLD_TITLE)


# ── 修改分類 ──


def test_game_有完全相同的名稱時改成該分類_不分大小寫(env):
    env.stub.categories["minecraft"] = [("1", "Minecraft Dungeons"), ("2", "Minecraft")]

    replies = env.say("game", "minecraft", mod=True)

    assert (env.stub.game_id, env.stub.game_name) == ("2", "Minecraft")
    assert has(replies, "Minecraft")
    [entry] = changes(env)
    assert entry.source == "chat" and "Minecraft" in str(entry.after)


def test_game_沒有完全相同的名稱時改成搜尋第一筆並回覆改成哪個(env):
    env.stub.categories["mine"] = [("1", "Minecraft Dungeons"), ("2", "Minecraft")]

    replies = env.say("game", "mine", mod=True)

    assert env.stub.game_id == "1"
    assert has(replies, "Minecraft Dungeons")


def test_game_搜尋不到時不改並回覆找不到(env):
    replies = env.say("game", "不存在的遊戲", mod=True)

    assert has(replies, "找不到")
    assert env.stub.patches() == [] and env.stub.game_name == OLD_GAME
    assert changes(env) == []


def test_一般觀眾改分類_分類不變並回覆權限不足(env):
    env.stub.categories["minecraft"] = [("2", "Minecraft")]

    assert has(env.say("game", "minecraft"), "權限不足")
    assert env.stub.patches() == [] and env.stub.game_name == OLD_GAME


def test_分類名稱不經_AutoMod_檢查(env):
    env.stub.categories["minecraft"] = [("2", "Minecraft")]

    env.say("game", "minecraft", mod=True)

    env.automod.assert_not_awaited()
