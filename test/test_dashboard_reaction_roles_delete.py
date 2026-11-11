"""伺服器管理後台 R-04：刪除、失效處理與重新發送（假 Discord；端點用假 repository，repository 與 bot 啟動載入用真實 DB／假 bot）。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import discord
import pytest
from test_dashboard_auth import FRONTEND, dashboard_env  # noqa: F401
from test_dashboard_guilds import MANAGE_CHANNELS, g
from test_dashboard_guilds import discord as discord_env  # noqa: F401
from test_dashboard_notifies import GUILD_ID
from test_dashboard_reaction_roles import ROLE_ABOVE, ROLE_GONE, ROLE_OK
from test_dashboard_reaction_roles_write import (  # noqa: F401  (fixture 與 helper)
    EMOJI_GONE,
    EMOJI_OK,
    ROLE_B,
    TEXT,
    URL,
    FakeMessage,
    FakeRepo,
    btn,
    http_error,
    original,
    seed,
)
from test_dashboard_reaction_roles_write import client as base_client  # noqa: F401
from test_identity import repo  # noqa: F401

from starlib.database import ReactionRoleMessage, ReactionRoleOption
from starlib.message_content import MessageContent, from_json, to_json

R_GUILD = 8_810_000_000_000_001
R_CHANNEL = 8_810_000_000_000_002


class DeleteRepo(FakeRepo):
    def __init__(self):
        super().__init__()
        self.fail_delete = False
        self.moves: list[tuple] = []
        self.fail_move = False

    def delete_reaction_role_message(self, message_id: int):
        if self.fail_delete:
            raise RuntimeError("db down")
        self.messages.pop(message_id, None)

    def move_reaction_role_message(self, old_id, new_channel_id, new_id, content_json=None, keep_role_ids=None):
        self.moves.append((old_id, new_channel_id, new_id, content_json, keep_role_ids))
        if self.fail_move:
            raise RuntimeError("db down")
        m = self.messages.pop(old_id)
        m["channel_id"] = new_channel_id
        if content_json is not None:
            m["content_json"] = content_json
        if keep_role_ids is not None:
            by_role = {b["role_id"]: b for b in m["buttons"]}
            m["buttons"] = [by_role[r] for r in keep_role_ids]
        self.messages[new_id] = m


@pytest.fixture
def client(base_client, monkeypatch):  # noqa: F811
    from starServer.dashboard import reaction_roles

    fake = DeleteRepo()
    monkeypatch.setattr(reaction_roles, "sqldb", fake)
    base_client.repo = fake
    return base_client


def delete(client, mid: int, mode: str = "delete_message", orig: dict | None = None):
    return client.request(
        "DELETE",
        f"{URL}/{mid}",
        json={"mode": mode, "original": orig or original(client, mid)},
        headers={"Origin": FRONTEND},
    )


def resend(client, mid: int, channel: int | str | None = 502, message: dict | None = None):
    body: dict = {"message": message}
    if channel is not None:
        body["channel_id"] = str(channel)
    return client.post(f"{URL}/{mid}/resend", json=body, headers={"Origin": FRONTEND})


def drop_message(client, mid: int):
    """模擬 Discord 上訊息已被刪除。"""
    del client.guild.channel.messages[mid]


# ====== DELETE ======
class TestDelete:
    def test_delete_message_mode_deletes_message_and_record(self, client):
        message = seed(client, 900, [btn(ROLE_OK)], content=MessageContent(content="歡迎"))
        r = delete(client, 900, "delete_message")
        assert r.status_code == 200 and r.json() == {"deleted": True}
        assert message.deleted is True
        assert 900 not in client.repo.messages

    def test_remove_buttons_mode_keeps_message(self, client):
        message = seed(client, 900, [btn(ROLE_OK)], content=MessageContent(content="歡迎"))
        r = delete(client, 900, "remove_buttons")
        assert r.status_code == 200
        assert message.deleted is False
        assert message.edits == [{"view": None}]
        assert 900 not in client.repo.messages

    @pytest.mark.parametrize("mode", ["delete_message", "remove_buttons"])
    def test_message_already_gone_is_success(self, client, mode):
        seed(client, 900, [btn(ROLE_OK)], content=MessageContent(content="歡迎"))
        orig = original(client, 900)
        drop_message(client, 900)
        assert delete(client, 900, mode, orig).status_code == 200
        assert 900 not in client.repo.messages

    @pytest.mark.parametrize("mode", ["delete_message", "remove_buttons"])
    def test_channel_already_gone_is_success(self, client, mode):
        seed(client, 900, [btn(ROLE_OK)], content=MessageContent(content="歡迎"))
        orig = original(client, 900)
        client.guild.text_channels = [client.guild.other_channel]
        assert delete(client, 900, mode, orig).status_code == 200
        assert 900 not in client.repo.messages

    def test_conflict_when_buttons_changed(self, client):
        message = seed(client, 900, [btn(ROLE_OK, "活動")], content=MessageContent(content="歡迎"))
        orig = original(client, 900)
        client.repo.messages[900]["buttons"][0]["title"] = "別人改的"
        r = delete(client, 900, "delete_message", orig)
        assert r.status_code == 409
        body = r.json()
        assert body["error"] == "conflict" and body["deleted"] is False
        assert body["current"]["buttons"][0]["title"] == "別人改的"
        assert message.deleted is False and 900 in client.repo.messages

    def test_conflict_when_content_changed(self, client):
        seed(client, 900, [btn(ROLE_OK)], content=MessageContent(content="歡迎"))
        orig = original(client, 900)
        client.repo.messages[900]["content_json"] = to_json(MessageContent(content="新內容"))
        r = delete(client, 900, "remove_buttons", orig)
        assert r.status_code == 409 and r.json()["current"]["content"]["content"] == "新內容"
        assert 900 in client.repo.messages

    def test_conflict_when_record_already_deleted(self, client):
        seed(client, 900, [btn(ROLE_OK)], content=MessageContent(content="歡迎"))
        orig = original(client, 900)
        del client.repo.messages[900]
        r = delete(client, 900, "delete_message", orig)
        assert r.status_code == 409 and r.json()["deleted"] is True and r.json()["current"] is None

    def test_other_guild_record_is_treated_as_missing(self, client):
        seed(client, 900, [btn(ROLE_OK)], content=MessageContent(content="歡迎"))
        orig = original(client, 900)
        client.repo.messages[900]["guild_id"] = GUILD_ID + 1
        assert delete(client, 900, "delete_message", orig).status_code == 409
        assert 900 in client.repo.messages

    def test_discord_error_keeps_record(self, client):
        message = seed(client, 900, [btn(ROLE_OK)], content=MessageContent(content="歡迎"))

        async def boom():
            raise http_error(403)

        message.delete = boom  # pyright: ignore[reportAttributeAccessIssue]
        r = delete(client, 900, "delete_message")
        assert r.status_code == 502 and r.json()["error"] == "discord_error"
        assert 900 in client.repo.messages

    def test_db_error(self, client):
        seed(client, 900, [btn(ROLE_OK)], content=MessageContent(content="歡迎"))
        client.repo.fail_delete = True
        r = delete(client, 900)
        assert r.status_code == 500 and r.json()["error"] == "save_failed"

    def test_invalid_mode_rejected(self, client):
        seed(client, 900, [btn(ROLE_OK)], content=MessageContent(content="歡迎"))
        r = client.request(
            "DELETE",
            f"{URL}/900",
            json={"mode": "whatever", "original": original(client, 900)},
            headers={"Origin": FRONTEND},
        )
        assert r.status_code == 422 or r.status_code == 400
        assert 900 in client.repo.messages

    def test_requires_manage_roles(self, client):
        seed(client, 900, [btn(ROLE_OK)], content=MessageContent(content="歡迎"))
        orig = {"content_json": client.repo.messages[900]["content_json"], "buttons": [btn(ROLE_OK)]}
        client.discord_env.guilds = [g(str(GUILD_ID), "guild", MANAGE_CHANNELS)]
        assert delete(client, 900, "delete_message", orig).status_code == 403
        assert 900 in client.repo.messages


# ====== POST /{message_id}/resend ======
CONTENT = MessageContent(content="歡迎來領身分組")


class TestResend:
    def seed_gone(self, client, buttons=None, content=CONTENT, mid: int = 900):
        seed(client, mid, buttons or [btn(ROLE_OK, "活動"), btn(ROLE_B, "遊戲")], content=content)
        drop_message(client, mid)

    def test_resend_to_other_channel_moves_record(self, client):
        self.seed_gone(client)
        r = resend(client, 900, 502)
        assert r.status_code == 200
        body = r.json()
        new_id = int(body["message_id"])
        assert body["channel_id"] == "502" and body["skipped"] == []
        sent = client.guild.other_channel.sent[0]
        assert sent.id == new_id and sent.content == "歡迎來領身分組"
        assert client.repo.moves == [(900, 502, new_id, None, [ROLE_OK, ROLE_B])]
        assert 900 not in client.repo.messages
        assert client.repo.messages[new_id]["channel_id"] == 502
        assert [m for m, _ in client.bot.views] == [new_id]
        # 新訊息帶 view，按鈕的 custom_id 指向新訊息
        assert sent.edits and sent.edits[0]["view"] is not None
        ids = [c.custom_id for c in sent.edits[0]["view"].children]
        assert all(str(new_id) in i for i in ids)

    def test_resend_defaults_to_original_channel(self, client):
        self.seed_gone(client)
        r = resend(client, 900, channel=None)
        assert r.status_code == 200 and r.json()["channel_id"] == "501"
        assert len(client.guild.channel.sent) == 1

    def test_original_channel_gone_requires_channel(self, client):
        self.seed_gone(client)
        client.guild.text_channels = [client.guild.other_channel]
        r = resend(client, 900, channel=None)
        assert r.status_code == 400
        assert r.json()["fields"][0]["path"] == "channel_id"
        assert 900 in client.repo.messages and client.repo.moves == []
        # 另選頻道即可
        assert resend(client, 900, 502).status_code == 200

    def test_original_channel_deleted_resend_to_other(self, client):
        self.seed_gone(client)
        client.guild.text_channels = [client.guild.other_channel]
        r = resend(client, 900, 502)
        assert r.status_code == 200 and client.repo.messages[int(r.json()["message_id"])]["channel_id"] == 502

    def test_skips_invalid_buttons_and_reports_them(self, client):
        self.seed_gone(
            client,
            [btn(ROLE_OK, "活動"), btn(ROLE_GONE, "已刪除"), btn(ROLE_ABOVE, "太高"), btn(ROLE_B, "遊戲", EMOJI_GONE)],
        )
        r = resend(client, 900, 502)
        assert r.status_code == 200
        skipped = r.json()["skipped"]
        assert [(s["role_id"], s["title"]) for s in skipped] == [
            (str(ROLE_GONE), "已刪除"),
            (str(ROLE_ABOVE), "太高"),
            (str(ROLE_B), "遊戲"),
        ]
        assert all(s["reason"] for s in skipped)
        new_id = int(r.json()["message_id"])
        assert client.repo.moves[0][4] == [ROLE_OK]
        sent = client.guild.other_channel.sent[0]
        assert [c.label for c in sent.edits[0]["view"].children] == ["活動"]
        assert [b["role_id"] for b in client.repo.messages[new_id]["buttons"]] == [ROLE_OK]

    def test_all_buttons_invalid_rejected(self, client):
        self.seed_gone(client, [btn(ROLE_GONE, "已刪除")])
        r = resend(client, 900, 502)
        assert r.status_code == 400 and r.json()["error"] == "no_valid_buttons"
        assert len(r.json()["skipped"]) == 1
        assert client.guild.other_channel.sent == [] and 900 in client.repo.messages

    def test_no_stored_content_requires_message(self, client):
        self.seed_gone(client, content=None)
        r = resend(client, 900, 502)
        assert r.status_code == 400
        assert r.json()["fields"][0]["path"] == "message"
        assert "沒有可重新發送的內容" in r.json()["fields"][0]["reason"]
        assert client.guild.other_channel.sent == [] and 900 in client.repo.messages

    def test_no_stored_content_with_message_stores_it(self, client):
        self.seed_gone(client, content=None)
        r = resend(client, 900, 502, message={"content": "重新編排", "embed": None})
        assert r.status_code == 200
        new_id = int(r.json()["message_id"])
        assert client.guild.other_channel.sent[0].content == "重新編排"
        assert from_json(client.repo.messages[new_id]["content_json"]).content == "重新編排"

    def test_message_overrides_stored_content(self, client):
        self.seed_gone(client)
        r = resend(client, 900, 502, message={"content": "改過的", "embed": None})
        assert r.status_code == 200
        assert client.guild.other_channel.sent[0].content == "改過的"
        new_id = int(r.json()["message_id"])
        assert from_json(client.repo.messages[new_id]["content_json"]).content == "改過的"

    def test_invalid_message_content_rejected(self, client):
        self.seed_gone(client)
        r = resend(client, 900, 502, message={"content": "x" * 2001, "embed": None})
        assert r.status_code == 400 and r.json()["error"] == "invalid_request"
        assert client.guild.other_channel.sent == []

    def test_resend_when_channel_gone_uses_new_content_with_multiple_embed_record(self, client):
        # 多 embed 或附件的訊息 content_json 為 null，失效後必須重新編排
        self.seed_gone(client, content=None)
        client.guild.text_channels = [client.guild.other_channel]
        assert resend(client, 900, 502).status_code == 400
        assert resend(client, 900, 502, message={"content": "新排", "embed": None}).status_code == 200

    def test_message_still_exists_rejected(self, client):
        seed(client, 900, [btn(ROLE_OK)], content=CONTENT)
        r = resend(client, 900, 502)
        assert r.status_code == 400 and r.json()["error"] == "message_exists"
        assert client.guild.other_channel.sent == [] and 900 in client.repo.messages

    def test_unknown_record_404(self, client):
        assert resend(client, 12345, 502).status_code == 404

    def test_target_channel_must_be_text_channel_of_guild(self, client):
        self.seed_gone(client)
        r = resend(client, 900, 999999)
        assert r.status_code == 400 and r.json()["fields"][0]["path"] == "channel_id"

    def test_bot_missing_send_permission(self, client):
        self.seed_gone(client)
        client.guild.other_channel.perms["send_messages"] = False
        r = resend(client, 900, 502)
        assert r.status_code == 400 and r.json()["error"] == "bot_missing_permission"

    def test_db_failure_deletes_new_message(self, client):
        self.seed_gone(client)
        client.repo.fail_move = True
        r = resend(client, 900, 502)
        assert r.status_code == 500 and r.json()["error"] == "save_failed"
        assert client.guild.other_channel.sent[0].deleted is True
        assert 900 in client.repo.messages

    def test_attach_view_failure_deletes_new_message(self, client):
        self.seed_gone(client)
        client.guild.other_channel.fail_edit_new = True
        r = resend(client, 900, 502)
        assert r.status_code == 502
        assert client.guild.other_channel.sent[0].deleted is True
        assert client.repo.moves == [] and 900 in client.repo.messages

    def test_send_failure(self, client):
        self.seed_gone(client)
        client.guild.other_channel.fail_send = True
        r = resend(client, 900, 502)
        assert r.status_code == 502 and 900 in client.repo.messages

    def test_requires_manage_roles(self, client):
        self.seed_gone(client)
        client.discord_env.guilds = [g(str(GUILD_ID), "guild", MANAGE_CHANNELS)]
        assert resend(client, 900, 502).status_code == 403


# ====== repository：move_reaction_role_message（真實 PostgreSQL）======
def option(mid: int, rid: int, title: str = "t", position: int = 0) -> ReactionRoleOption:
    return ReactionRoleOption(message_id=mid, role_id=rid, title=title, description=None, emoji=None, style=1, position=position)


class TestMoveRepository:
    def test_moves_message_and_options_in_one_transaction(self, repo):  # noqa: F811
        old, new = 8_810_000_000_000_100, 8_810_000_000_000_101
        repo.replace_reaction_role_message(R_GUILD, R_CHANNEL, old, "舊內容", [option(old, 1, "a"), option(old, 2, "b"), option(old, 3, "c")])
        repo.move_reaction_role_message(old, R_CHANNEL + 1, new)
        assert repo.get_reaction_role_snapshot(old) is None
        assert repo.get_reaction_roles_by_message(old) == []
        snap = repo.get_reaction_role_snapshot(new)
        assert snap["channel_id"] == R_CHANNEL + 1 and snap["guild_id"] == R_GUILD
        assert snap["content_json"] == "舊內容"
        assert [(b["role_id"], b["title"]) for b in snap["buttons"]] == [(1, "a"), (2, "b"), (3, "c")]

    def test_keep_role_ids_drops_others_and_renumbers(self, repo):  # noqa: F811
        old, new = 8_810_000_000_000_200, 8_810_000_000_000_201
        repo.replace_reaction_role_message(R_GUILD, R_CHANNEL, old, "x", [option(old, 1), option(old, 2), option(old, 3), option(old, 4)])
        repo.move_reaction_role_message(old, R_CHANNEL, new, None, [4, 2])
        assert [(o.role_id, o.position) for o in repo.get_reaction_roles_by_message(new)] == [(4, 0), (2, 1)]

    def test_content_json_replaced_when_given(self, repo):  # noqa: F811
        old, new = 8_810_000_000_000_300, 8_810_000_000_000_301
        repo.replace_reaction_role_message(R_GUILD, R_CHANNEL, old, "舊", [option(old, 1)])
        repo.move_reaction_role_message(old, R_CHANNEL, new, "新")
        assert repo.get_reaction_role_snapshot(new)["content_json"] == "新"

    def test_only_touches_that_message(self, repo):  # noqa: F811
        old, other, new = 8_810_000_000_000_400, 8_810_000_000_000_401, 8_810_000_000_000_402
        repo.replace_reaction_role_message(R_GUILD, R_CHANNEL, old, "a", [option(old, 1)])
        repo.replace_reaction_role_message(R_GUILD, R_CHANNEL, other, "b", [option(other, 1)])
        repo.move_reaction_role_message(old, R_CHANNEL, new)
        assert repo.get_reaction_role_snapshot(other)["content_json"] == "b"
        assert len(repo.get_reaction_roles_by_message(other)) == 1

    def test_atomic_when_new_id_collides(self, repo):  # noqa: F811
        old, taken = 8_810_000_000_000_500, 8_810_000_000_000_501
        repo.replace_reaction_role_message(R_GUILD, R_CHANNEL, old, "a", [option(old, 1), option(old, 2)])
        repo.replace_reaction_role_message(R_GUILD, R_CHANNEL, taken, "b", [option(taken, 1)])
        with pytest.raises(Exception):  # noqa: B017  新 message_id 與既有紀錄的主鍵衝突
            repo.move_reaction_role_message(old, R_CHANNEL, taken, None, [1])
        snap = repo.get_reaction_role_snapshot(old)
        assert snap is not None and [b["role_id"] for b in snap["buttons"]] == [1, 2]
        assert repo.get_reaction_role_snapshot(taken)["content_json"] == "b"

    def test_unknown_message_is_noop(self, repo):  # noqa: F811
        repo.move_reaction_role_message(8_810_000_000_000_600, R_CHANNEL, 8_810_000_000_000_601)
        assert repo.get_reaction_role_snapshot(8_810_000_000_000_601) is None

    def test_set_reaction_role_content_only_when_null(self, repo):  # noqa: F811
        mid = 8_810_000_000_000_700
        repo.merge(ReactionRoleMessage(guild_id=R_GUILD, channel_id=R_CHANNEL, message_id=mid))
        assert repo.set_reaction_role_content(mid, "回填") is True
        assert repo.get_reaction_role_message(mid).content_json == "回填"
        assert repo.set_reaction_role_content(mid, "不覆蓋") is False
        assert repo.get_reaction_role_message(mid).content_json == "回填"


# ====== bot 啟動載入（bot_event.load_reaction_role_views）======
class LoaderChannel:
    def __init__(self, messages: dict[int, object], error: Exception | None = None):
        self.messages = messages
        self.error = error

    async def fetch_message(self, mid: int):
        if self.error is not None:
            raise self.error
        if mid not in self.messages:
            raise discord.NotFound(SimpleNamespace(status=404, reason="Not Found"), "unknown")
        return self.messages[mid]


class LoaderBot:
    def __init__(self, channels: dict[int, LoaderChannel]):
        self.channels = channels
        self.views: list[tuple[int, object]] = []

    def get_channel(self, cid: int):
        return self.channels.get(cid)

    def add_view(self, view, message_id=None):
        self.views.append((message_id, view))


class LoaderRepo:
    def __init__(self, rows: list[tuple[int, int, str | None]]):
        self.rows = [SimpleNamespace(channel_id=c, message_id=m, content_json=j) for c, m, j in rows]
        self.deleted: list[int] = []
        self.saved: dict[int, str] = {}

    def get_reaction_role_message_all(self):
        return self.rows

    def get_reaction_roles_by_message(self, mid: int):
        return [option(mid, 1, "a")]

    def delete_reaction_role_message(self, mid: int):
        self.deleted.append(mid)

    def set_reaction_role_content(self, mid: int, content_json: str):
        self.saved[mid] = content_json
        return True


class _Channel(discord.abc.Messageable):
    """讓 `isinstance(channel, discord.abc.Messageable)` 成立的假頻道。"""

    def __init__(self, inner: LoaderChannel):
        self._inner = inner

    async def _get_channel(self):  # pragma: no cover
        raise NotImplementedError

    async def fetch_message(self, mid: int):
        return await self._inner.fetch_message(mid)


def run_loader(rows, channels):
    from starDiscord.cmds import bot_event

    bot = LoaderBot({cid: _Channel(ch) for cid, ch in channels.items()})
    repo = LoaderRepo(rows)

    async def _no_sleep(_):
        return None

    original_sleep = bot_event.asyncio.sleep
    bot_event.asyncio.sleep = _no_sleep  # pyright: ignore[reportAttributeAccessIssue]
    try:
        asyncio.run(bot_event.load_reaction_role_views(bot, repo))
    finally:
        bot_event.asyncio.sleep = original_sleep
    return bot, repo


def discord_message(mid: int, content: str = "", embeds=(), attachments=()):
    return SimpleNamespace(id=mid, content=content, embeds=list(embeds), attachments=list(attachments))


class TestBotEventLoader:
    def test_channel_gone_skips_view_keeps_record(self):
        bot, repo = run_loader([(1, 10, None)], {})
        assert bot.views == [] and repo.deleted == []

    def test_message_gone_skips_view_keeps_record(self):
        bot, repo = run_loader([(1, 10, None)], {1: LoaderChannel({})})
        assert bot.views == [] and repo.deleted == [] and repo.saved == {}

    def test_existing_message_loads_view(self):
        bot, repo = run_loader([(1, 10, "{}")], {1: LoaderChannel({10: discord_message(10, "x")})})
        assert [m for m, _ in bot.views] == [10] and repo.deleted == []

    def test_unreadable_message_still_loads_view_without_backfill(self):
        err = discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), "missing access")
        bot, repo = run_loader([(1, 10, None)], {1: LoaderChannel({}, error=err)})
        assert [m for m, _ in bot.views] == [10] and repo.saved == {} and repo.deleted == []

    def test_backfills_content_json_when_null(self):
        embed = discord.Embed(title="標題", description="說明")
        bot, repo = run_loader([(1, 10, None)], {1: LoaderChannel({10: discord_message(10, "文字", [embed])})})
        assert [m for m, _ in bot.views] == [10]
        stored = from_json(repo.saved[10])
        assert stored.content == "文字" and stored.embed and stored.embed.title == "標題"

    def test_does_not_overwrite_existing_content_json(self):
        bot, repo = run_loader([(1, 10, '{"content": "舊"}')], {1: LoaderChannel({10: discord_message(10, "新")})})
        assert repo.saved == {}

    def test_multiple_embeds_stay_null(self):
        embeds = [discord.Embed(title="一"), discord.Embed(title="二")]
        bot, repo = run_loader([(1, 10, None)], {1: LoaderChannel({10: discord_message(10, "", embeds)})})
        assert repo.saved == {} and [m for m, _ in bot.views] == [10]

    def test_attachments_stay_null(self):
        bot, repo = run_loader([(1, 10, None)], {1: LoaderChannel({10: discord_message(10, "有圖", attachments=[object()])})})
        assert repo.saved == {} and [m for m, _ in bot.views] == [10]
