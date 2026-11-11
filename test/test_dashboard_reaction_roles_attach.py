"""伺服器管理後台 R-03：把反應身分組掛到 bot 既有的訊息（候選清單、解析連結、POST target.kind=existing）。"""

from __future__ import annotations

from types import SimpleNamespace

import discord
from test_dashboard_auth import FRONTEND, dashboard_env  # noqa: F401  (fixture)
from test_dashboard_guilds import discord as discord_env  # noqa: F401  (fixture)
from test_dashboard_notifies import GUILD_ID
from test_dashboard_reaction_roles_write import (  # noqa: F401  (fixture 與 helper)
    ROLE_OK,
    URL,
    FakeMessage,
    btn,
    client,
    fields,
    seed,
)
from test_identity import repo  # noqa: F401

from starlib.message_content import MessageContent, from_json

OTHER = 777  # 不是 bot 的作者
ROLE_MISSING = 3999  # 不存在的身分組


def put_message(client, mid: int, **kwargs) -> FakeMessage:
    m = FakeMessage(mid, kwargs.pop("content", "公告"), **kwargs)
    client.guild.channel.messages[mid] = m
    return m


def seed_registered(client, mid: int) -> FakeMessage:
    return seed(
        client,
        mid,
        [btn(ROLE_OK)],
        content=MessageContent(content="已掛"),
        message=FakeMessage(mid, "已掛", components=[object()]),
    )


def link(mid: int, channel: int = 501, guild: int = GUILD_ID) -> str:
    return f"https://discord.com/channels/{guild}/{channel}/{mid}"


def candidates(client, channel: int = 501):
    return client.get(f"{URL}/candidates", params={"channel_id": channel})


def resolve(client, text: str):
    return client.get(f"{URL}/resolve", params={"link": text})


def attach(client, mid: int, buttons: list[dict], message: dict | None = None, channel: int = 501):
    return client.post(
        URL,
        json={
            "target": {"kind": "existing", "channel_id": str(channel), "message_id": str(mid)},
            "message": message,
            "buttons": buttons,
        },
        headers={"Origin": FRONTEND},
    )


def embed_message(mid: int, n: int = 1, **kwargs) -> FakeMessage:
    embeds = [discord.Embed(title=f"標題{i}", description="內文") for i in range(n)]
    return FakeMessage(mid, "", embeds=embeds, **kwargs)


# ====== GET /candidates ======
class TestCandidates:
    def test_only_bot_messages(self, client):
        put_message(client, 10)
        put_message(client, 11, author_id=OTHER)
        data = candidates(client).json()
        assert [m["message_id"] for m in data["messages"]] == ["10"]
        assert data["messages"][0]["status"] == "free"
        assert data["messages"][0]["summary"] == "公告"
        assert data["messages"][0]["created_at"]

    def test_excludes_other_components(self, client):
        put_message(client, 10)
        put_message(client, 11, components=[object()])
        assert [m["message_id"] for m in candidates(client).json()["messages"]] == ["10"]

    def test_reaction_role_listed_with_status(self, client):
        seed_registered(client, 20)
        put_message(client, 10)
        data = {m["message_id"]: m["status"] for m in candidates(client).json()["messages"]}
        assert data == {"20": "reaction_role", "10": "free"}

    def test_newest_first(self, client):
        for mid in (10, 12, 11):
            put_message(client, mid)
        assert [m["message_id"] for m in candidates(client).json()["messages"]] == ["12", "11", "10"]

    def test_max_25_free_and_reaction_role_not_counted(self, client):
        for mid in range(1, 31):  # 30 則 free
            put_message(client, mid)
        for mid in range(31, 34):  # 3 則反應身分組，比 free 新
            seed_registered(client, mid)
        msgs = candidates(client).json()["messages"]
        statuses = [m["status"] for m in msgs]
        assert statuses.count("free") == 25
        assert statuses.count("reaction_role") == 3
        # 只取最近的 25 則 free
        assert {m["message_id"] for m in msgs if m["status"] == "free"} == {str(i) for i in range(6, 31)}

    def test_only_last_100_scanned(self, client):
        put_message(client, 1)  # 第 101 新
        for mid in range(2, 102):
            put_message(client, mid, author_id=OTHER)
        assert candidates(client).json()["messages"] == []

    def test_unknown_channel_400(self, client):
        assert candidates(client, channel=999).status_code == 400

    def test_forbidden_history(self, client):
        async def boom(limit=100):
            raise discord.Forbidden(SimpleNamespace(status=403, reason="x"), "no")
            yield  # pragma: no cover

        client.guild.channel.history = boom
        r = candidates(client)
        assert r.status_code == 400 and r.json()["error"] == "bot_missing_permission"

    def test_requires_section(self, client):
        from test_dashboard_guilds import MANAGE_CHANNELS, g

        client.discord_env.guilds = [g(str(GUILD_ID), "guild", MANAGE_CHANNELS)]
        assert candidates(client).status_code == 403


# ====== GET /resolve ======
class TestResolve:
    def test_free_message_returns_content(self, client):
        client.guild.channel.messages[30] = embed_message(30)
        r = resolve(client, link(30))
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "free" and d["content_locked"] is None
        assert d["content"]["embed"]["title"] == "標題0"
        assert d["channel"] == {"id": "501", "name": "身分組"}

    def test_accepts_ptb_and_angle_brackets(self, client):
        put_message(client, 30)
        assert resolve(client, f"<{link(30).replace('discord.com', 'ptb.discord.com')}>").status_code == 200

    def test_multiple_embeds_locked(self, client):
        client.guild.channel.messages[30] = embed_message(30, n=2)
        d = resolve(client, link(30)).json()
        assert d["content"] is None and d["content_locked"] == "multiple_embeds"

    def test_attachments_locked(self, client):
        put_message(client, 30, attachments=[object()])
        assert resolve(client, link(30)).json()["content_locked"] == "has_attachments"

    def test_not_a_link(self, client):
        r = resolve(client, "https://example.com/x")
        assert r.status_code == 400 and r.json()["error"] == "invalid_link"

    def test_other_guild(self, client):
        put_message(client, 30)
        r = resolve(client, link(30, guild=GUILD_ID + 1))
        assert r.status_code == 400 and r.json()["error"] == "wrong_guild"

    def test_channel_not_in_guild(self, client):
        assert resolve(client, link(30, channel=999)).json()["error"] == "wrong_guild"

    def test_message_missing(self, client):
        r = resolve(client, link(404))
        assert r.status_code == 404 and r.json()["error"] == "message_not_found"

    def test_not_bot_message(self, client):
        put_message(client, 30, author_id=OTHER)
        r = resolve(client, link(30))
        assert r.status_code == 400 and r.json()["error"] == "not_bot_message"
        assert r.json()["message"]

    def test_other_components(self, client):
        put_message(client, 30, components=[object()])
        r = resolve(client, link(30))
        assert r.status_code == 400 and r.json()["error"] == "has_components"
        assert r.json()["message"]

    def test_already_reaction_role(self, client):
        seed_registered(client, 20)
        d = resolve(client, link(20)).json()
        assert d["status"] == "reaction_role" and d["message_id"] == "20"


# ====== POST target.kind=existing ======
class TestAttach:
    def test_edits_original_message_and_records_content(self, client):
        m = embed_message(30)
        client.guild.channel.messages[30] = m
        content = {"content": "新字", "embed": {"title": "新標題"}}
        r = attach(client, 30, [btn(ROLE_OK, "活動")], content)
        assert r.status_code == 200, r.text
        assert r.json() == {"message_id": "30", "jump_url": m.jump_url}
        assert client.guild.channel.sent == []  # 沒有發新訊息
        assert m.content == "新字" and m.embeds[0].title == "新標題"
        assert m.edits[-1]["view"].children[0].label == "活動"
        assert client.bot.views[0][0] == 30
        record = client.repo.messages[30]
        assert (record["guild_id"], record["channel_id"]) == (GUILD_ID, 501)
        assert from_json(record["content_json"]).content == "新字"

    def test_content_unchanged_when_message_omitted(self, client):
        m = put_message(client, 30, content="原文")
        r = attach(client, 30, [btn(ROLE_OK)], None)
        assert r.status_code == 200, r.text
        assert m.content == "原文"
        assert from_json(client.repo.messages[30]["content_json"]).content == "原文"

    def test_locked_content_only_buttons_and_json_null(self, client):
        m = embed_message(30, n=2)
        client.guild.channel.messages[30] = m
        r = attach(client, 30, [btn(ROLE_OK)], None)
        assert r.status_code == 200, r.text
        assert set(m.edits[-1]) == {"view"}  # 不動內容
        assert len(m.embeds) == 2
        assert client.repo.messages[30]["content_json"] is None

    def test_locked_content_with_message_400(self, client):
        client.guild.channel.messages[30] = embed_message(30, n=2)
        r = attach(client, 30, [btn(ROLE_OK)], {"content": "改", "embed": None})
        assert r.status_code == 400
        assert r.json() == {"error": "content_locked", "reason": "multiple_embeds"}
        assert 30 not in client.repo.messages

    def test_attachments_locked_400(self, client):
        put_message(client, 30, attachments=[object()])
        r = attach(client, 30, [btn(ROLE_OK)], {"content": "改", "embed": None})
        assert r.json() == {"error": "content_locked", "reason": "has_attachments"}

    def test_not_bot_message(self, client):
        put_message(client, 30, author_id=OTHER)
        r = attach(client, 30, [btn(ROLE_OK)], {"content": "x", "embed": None})
        assert r.status_code == 400 and r.json()["error"] == "not_bot_message"
        assert client.repo.replace_calls == 0

    def test_other_components_rejected(self, client):
        put_message(client, 30, components=[object()])
        assert attach(client, 30, [btn(ROLE_OK)]).json()["error"] == "has_components"

    def test_already_reaction_role_rejected(self, client):
        seed_registered(client, 20)
        r = attach(client, 20, [btn(ROLE_OK)])
        assert r.status_code == 400
        assert r.json()["error"] == "already_reaction_role" and r.json()["message_id"] == "20"

    def test_channel_not_in_guild(self, client):
        r = attach(client, 30, [btn(ROLE_OK)], channel=999)
        assert r.status_code == 400 and r.json()["error"] == "wrong_guild"

    def test_missing_message(self, client):
        r = attach(client, 404, [btn(ROLE_OK)])
        assert r.status_code == 404 and r.json()["error"] == "message_not_found"

    def test_buttons_still_validated(self, client):
        put_message(client, 30)
        assert attach(client, 30, []).status_code == 400
        assert attach(client, 30, [btn(ROLE_MISSING)]).status_code == 400
        assert client.repo.replace_calls == 0

    def test_db_failure_restores_message_without_buttons(self, client):
        m = put_message(client, 30, content="原文")
        client.repo.fail_replace = True
        r = attach(client, 30, [btn(ROLE_OK)], {"content": "新字", "embed": None})
        assert r.status_code == 500 and r.json()["error"] == "save_failed"
        assert m.content == "原文"
        assert m.edits[-1]["view"] is None

    def test_discord_edit_failure_502(self, client):
        m = put_message(client, 30)
        m.fail_edit = True
        r = attach(client, 30, [btn(ROLE_OK)], {"content": "x", "embed": None})
        assert r.status_code == 502 and client.repo.replace_calls == 0

    def test_new_target_still_needs_message(self, client):
        r = client.post(
            URL,
            json={"target": {"kind": "new", "channel_id": "501"}, "message": None, "buttons": [btn(ROLE_OK)]},
            headers={"Origin": FRONTEND},
        )
        assert r.status_code == 400
        assert fields(r) == [("message", "新訊息必須有內容")]
