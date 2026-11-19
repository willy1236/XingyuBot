"""伺服器管理後台 R-02：發新的反應身分組訊息、編輯按鈕與內容（假 Discord；端點用假 repository，repository 本身用真實 PostgreSQL）。"""

from __future__ import annotations

import discord
import pytest

from starlib.database import ReactionRoleMessage, ReactionRoleOption
from starlib.message_content import EmbedContent, MessageContent, from_json, to_json
from tests.helpers.dashboard_auth import FRONTEND
from tests.helpers.dashboard_guilds import MANAGE_CHANNELS, g
from tests.helpers.dashboard_notifies import GUILD_ID
from tests.reaction_roles.dashboard_helpers import (
    EVERYONE,
    ROLE_ABOVE,
    ROLE_GONE,
    ROLE_MANAGED,
    ROLE_OK,
)
from tests.reaction_roles.write_helpers import (
    ACTOR_ID,
    EMOJI_GONE,
    EMOJI_OK,
    EXTRA_ROLE_BASE,
    ROLE_ADMIN,
    ROLE_B,
    ROLE_HIGH,
    TEXT,
    URL,
    FakeMessage,
    btn,
    client,  # noqa: F401  (fixture)
    fields,
    original,
    seed,
)

pytestmark = pytest.mark.usefixtures("dashboard_env")


def put(client, mid: int, buttons: list[dict], message: dict | None = TEXT, orig: dict | None = None):
    return client.put(
        f"{URL}/{mid}",
        json={"message": message, "buttons": buttons, "original": orig or original(client, mid)},
        headers={"Origin": FRONTEND},
    )


def post(client, buttons: list[dict], message: dict = TEXT, channel: int | str = 501):
    return client.post(
        URL,
        json={"target": {"kind": "new", "channel_id": str(channel)}, "message": message, "buttons": buttons},
        headers={"Origin": FRONTEND},
    )


# ====== GET /options ======
class TestOptions:
    def test_roles_disabled_reasons(self, client):
        data = client.get(f"{URL}/options").json()
        reasons = {r["id"]: r["disabled_reason"] for r in data["roles"]}
        assert reasons[str(ROLE_OK)] is None
        assert "低於你最高身分組" in reasons[str(ROLE_HIGH)]
        assert "不低於我的最高身分組" in reasons[str(ROLE_ABOVE)]
        assert "@everyone" in reasons[str(ROLE_MANAGED)]
        assert "@everyone" in reasons[str(EVERYONE)]

    def test_owner_only_limited_by_bot(self, client):
        client.guild.owner_id = ACTOR_ID
        reasons = {r["id"]: r["disabled_reason"] for r in client.get(f"{URL}/options").json()["roles"]}
        assert reasons[str(ROLE_HIGH)] is None
        assert "不低於我的最高身分組" in reasons[str(ROLE_ABOVE)]

    def test_dangerous(self, client):
        roles = {r["id"]: r for r in client.get(f"{URL}/options").json()["roles"]}
        assert roles[str(ROLE_ADMIN)]["dangerous"] is True
        assert roles[str(ROLE_ADMIN)]["dangerous_permissions"] == ["administrator", "manage_roles"]
        assert roles[str(ROLE_OK)]["dangerous"] is False
        assert roles[str(ROLE_OK)]["dangerous_permissions"] == []

    def test_channels_and_emojis(self, client):
        client.guild.other_channel.perms["send_messages"] = False
        data = client.get(f"{URL}/options").json()
        assert [c["id"] for c in data["channels"]] == ["501", "502"]
        assert [i["permission"] for i in data["channels"][1]["permission_issues"]] == ["Send Messages"]
        assert data["emojis"] == [{"id": "700000000000001", "name": "ok", "animated": False, "value": EMOJI_OK}]

    def test_requires_manage_roles(self, client):
        client.discord_env.guilds = [g(str(GUILD_ID), "guild", MANAGE_CHANNELS)]
        assert client.get(f"{URL}/options").status_code == 403


# ====== GET /{message_id} ======
class TestDetail:
    def test_stored_content(self, client):
        seed(client, 900, [btn(ROLE_OK, "活動", "🎉")], content=MessageContent(content="歡迎"))
        d = client.get(f"{URL}/900").json()
        assert d["content"]["content"] == "歡迎"
        assert d["content_json"] == client.repo.messages[900]["content_json"]
        assert d["content_locked"] is None
        assert d["channel"] == {"id": "501", "name": "身分組", "invalid": False}
        assert d["buttons"][0]["role_id"] == str(ROLE_OK)
        assert d["buttons"][0]["locked"] is False

    def test_reads_back_from_message_when_not_stored(self, client):
        embed = discord.Embed(title="標題", description="內文")
        seed(client, 900, [btn(ROLE_OK)], message=FakeMessage(900, "文字", [embed]))
        d = client.get(f"{URL}/900").json()
        assert d["content_json"] is None
        assert d["content"]["content"] == "文字"
        assert d["content"]["embed"]["title"] == "標題"
        assert d["content_locked"] is None

    def test_multiple_embeds_locks_content(self, client):
        embeds = [discord.Embed(title="一"), discord.Embed(title="二")]
        seed(client, 900, [btn(ROLE_OK)], message=FakeMessage(900, "", embeds))
        d = client.get(f"{URL}/900").json()
        assert d["content"] is None
        assert d["content_locked"] == "multiple_embeds"

    def test_attachments_lock_content(self, client):
        seed(client, 900, [btn(ROLE_OK)], message=FakeMessage(900, "有圖", attachments=[object()]))
        assert client.get(f"{URL}/900").json()["content_locked"] == "has_attachments"

    def test_unreadable_message_locks_content(self, client):
        seed(client, 900, [btn(ROLE_OK)])
        del client.guild.channel.messages[900]
        d = client.get(f"{URL}/900").json()
        assert d["content"] is None
        assert d["content_locked"] == "message_unavailable"

    def test_button_flags(self, client):
        seed(
            client,
            900,
            [btn(ROLE_HIGH, "高"), btn(ROLE_GONE, "失效"), btn(ROLE_OK, "有", EMOJI_GONE)],
            content=MessageContent(content="x"),
        )
        high, gone, emoji = client.get(f"{URL}/900").json()["buttons"]
        assert high["locked"] is True and "低於你最高身分組" in high["locked_reason"]
        assert gone["role"] == {"id": str(ROLE_GONE), "name": None, "invalid": True} and gone["locked"] is False
        assert emoji["emoji_invalid"] is True

    def test_locked_reason_is_operator_rank_when_role_also_above_bot(self, client):
        seed(client, 900, [btn(ROLE_ABOVE, "管理")], content=MessageContent(content="x"))
        (button,) = client.get(f"{URL}/900").json()["buttons"]
        assert button["locked"] is True
        assert button["locked_reason"] == "只能設定低於你最高身分組的身分組"

    def test_not_found_or_other_guild(self, client):
        assert client.get(f"{URL}/12345").status_code == 404
        seed(client, 900, [btn(ROLE_OK)], content=MessageContent(content="x"))
        client.repo.messages[900]["guild_id"] = GUILD_ID + 1
        assert client.get(f"{URL}/900").status_code == 404


# ====== POST ======
class TestCreate:
    def test_creates_message_view_and_record(self, client):
        embed = MessageContent(content="歡迎", embed=EmbedContent(title="選身分組", description="按一下取得"))
        r = post(
            client,
            [btn(ROLE_OK, "活動", "🎉"), btn(ROLE_B, "遊戲", EMOJI_OK, 3), btn(ROLE_ADMIN, "管理", None, None)],
            embed.model_dump(),
        )
        assert r.status_code == 200, r.text
        [sent] = client.guild.channel.sent
        assert r.json() == {"message_id": str(sent.id), "jump_url": sent.jump_url}
        assert sent.content == "歡迎" and sent.embeds[0].title == "選身分組"
        assert client.guild.channel.send_kwargs[0]["allowed_mentions"].everyone is False

        [(view_message_id, view)] = client.bot.views
        assert view_message_id == sent.id
        assert [c.custom_id for c in view.children] == [
            f"ReactionRole_{sent.id}_{rid}" for rid in (ROLE_OK, ROLE_B, ROLE_ADMIN)
        ]
        assert [c.label for c in view.children] == ["活動", "遊戲", "管理"]
        assert sent.edits[-1]["view"] is view

        record = client.repo.messages[sent.id]
        assert (record["guild_id"], record["channel_id"]) == (GUILD_ID, 501)
        assert from_json(record["content_json"]) == embed
        assert record["buttons"] == [
            {"role_id": ROLE_OK, "title": "活動", "emoji": "🎉", "style": 1},
            {"role_id": ROLE_B, "title": "遊戲", "emoji": EMOJI_OK, "style": 3},
            {"role_id": ROLE_ADMIN, "title": "管理", "emoji": None, "style": None},
        ]

    def test_sixth_button_goes_to_second_row(self, client):
        r = post(client, [btn(EXTRA_ROLE_BASE + i, f"b{i}") for i in range(6)])
        assert r.status_code == 200, r.text
        view = client.bot.views[0][1]
        assert [len(row["components"]) for row in view.to_components()] == [5, 1]

    def test_25_buttons_ok_26_rejected(self, client):
        assert post(client, [btn(EXTRA_ROLE_BASE + i, f"b{i}") for i in range(25)]).status_code == 200
        client.guild.channel.sent.clear()
        r = post(client, [btn(EXTRA_ROLE_BASE + i, f"b{i}") for i in range(26)])
        assert r.status_code == 400
        assert fields(r) == [("buttons", "按鈕不能超過 25 顆")]
        assert client.guild.channel.sent == []

    def test_at_least_one_button(self, client):
        r = post(client, [])
        assert r.status_code == 400
        assert fields(r) == [("buttons", "至少要有一顆按鈕")]
        assert client.guild.channel.sent == []

    def test_duplicate_role(self, client):
        r = post(client, [btn(ROLE_OK, "一"), btn(ROLE_OK, "二")])
        assert r.status_code == 400
        assert fields(r) == [("buttons.1.role_id", "同一個身分組只能出現一次")]

    @pytest.mark.parametrize("role", [ROLE_ABOVE, ROLE_MANAGED, EVERYONE, ROLE_GONE])
    def test_bot_cannot_assign(self, client, role):
        r = post(client, [btn(role)])
        assert r.status_code == 400
        assert r.json()["error"] == "invalid_request"
        assert fields(r)[0][0] == "buttons.0.role_id"
        assert client.guild.channel.sent == []

    def test_operator_rank(self, client):
        r = post(client, [btn(ROLE_HIGH)])
        assert r.status_code == 400
        assert "低於你最高身分組" in fields(r)[0][1]
        assert client.guild.channel.sent == []

    def test_owner_only_limited_by_bot_rank(self, client):
        client.guild.owner_id = ACTOR_ID
        assert post(client, [btn(ROLE_HIGH)]).status_code == 200
        r = post(client, [btn(ROLE_ABOVE)])
        assert r.status_code == 400
        assert "不低於我的最高身分組" in fields(r)[0][1]

    def test_dangerous_role_is_allowed(self, client):
        assert post(client, [btn(ROLE_ADMIN)]).status_code == 200

    def test_foreign_emoji_rejected(self, client):
        r = post(client, [btn(ROLE_OK, emoji=EMOJI_GONE)])
        assert r.status_code == 400
        assert fields(r)[0][0] == "buttons.0.emoji"
        assert client.guild.channel.sent == []

    def test_own_custom_emoji_ok(self, client):
        assert post(client, [btn(ROLE_OK, emoji=EMOJI_OK)]).status_code == 200

    @pytest.mark.parametrize("title", ["", "  ", "字" * 81])
    def test_bad_title(self, client, title):
        r = post(client, [btn(ROLE_OK, title)])
        assert r.status_code == 400
        assert fields(r)[0][0] == "buttons.0.title"

    def test_bad_style(self, client):
        r = post(client, [btn(ROLE_OK, style=5)])
        assert r.status_code == 400
        assert fields(r)[0][0] == "buttons.0.style"

    def test_empty_message_rejected(self, client):
        r = post(client, [btn(ROLE_OK)], {"content": "  ", "embed": {"color": 255}})
        assert r.status_code == 400
        assert r.json()["error"] == "invalid_request"
        assert fields(r)[0][0] == "content"
        assert client.guild.channel.sent == []

    def test_overlong_message_rejected(self, client):
        r = post(client, [btn(ROLE_OK)], {"content": "字" * 2001, "embed": None})
        assert r.status_code == 400
        assert fields(r)[0][0] == "content"
        r = post(client, [btn(ROLE_OK)], {"content": None, "embed": {"title": "字" * 257}})
        assert r.status_code == 400
        assert fields(r)[0][0] == "embed.title"
        assert client.guild.channel.sent == []

    def test_channel_must_be_guild_text_channel(self, client):
        assert post(client, [btn(ROLE_OK)], channel=999).status_code == 400
        assert post(client, [btn(ROLE_OK)], channel="abc").status_code == 400

    def test_bot_missing_send_permission(self, client):
        client.guild.channel.perms["send_messages"] = False
        r = post(client, [btn(ROLE_OK)])
        assert r.status_code == 400
        assert r.json()["error"] == "bot_missing_permission"
        assert client.guild.channel.sent == []

    def test_send_failure(self, client):
        client.guild.channel.fail_send = True
        r = post(client, [btn(ROLE_OK)])
        assert r.status_code == 502
        assert r.json()["error"] == "discord_error"
        assert client.repo.messages == {}

    def test_view_attach_failure_deletes_message(self, client):
        client.guild.channel.fail_edit_new = True
        r = post(client, [btn(ROLE_OK)])
        assert r.status_code == 502
        assert client.guild.channel.sent[0].deleted is True
        assert client.repo.messages == {} and client.bot.views == []

    def test_db_failure_deletes_sent_message(self, client):
        client.repo.fail_replace = True
        r = post(client, [btn(ROLE_OK)])
        assert r.status_code == 500
        assert r.json()["error"] == "save_failed"
        assert client.guild.channel.sent[0].deleted is True
        assert client.repo.messages == {}

    def test_requires_manage_roles(self, client):
        client.discord_env.guilds = [g(str(GUILD_ID), "guild", MANAGE_CHANNELS)]
        assert post(client, [btn(ROLE_OK)]).status_code == 403
        assert client.guild.channel.sent == []


# ====== PUT ======
OLD = MessageContent(content="舊內容")


class TestUpdate:
    def test_updates_message_buttons_and_record(self, client):
        message = seed(client, 900, [btn(ROLE_OK, "活動"), btn(ROLE_B, "遊戲")], content=OLD)
        new = {"content": "新內容", "embed": {"title": "新標題"}}
        r = put(client, 900, [btn(ROLE_B, "遊戲"), btn(ROLE_OK, "活動改"), btn(ROLE_ADMIN, "新增")], new)
        assert r.status_code == 200, r.text
        assert message.content == "新內容" and message.embeds[0].title == "新標題"
        view = message.edits[-1]["view"]
        assert [c.custom_id for c in view.children] == [
            f"ReactionRole_900_{rid}" for rid in (ROLE_B, ROLE_OK, ROLE_ADMIN)
        ]
        assert client.bot.views[-1] == (900, view)
        record = client.repo.messages[900]
        assert [b["role_id"] for b in record["buttons"]] == [ROLE_B, ROLE_OK, ROLE_ADMIN]
        assert from_json(record["content_json"]).embed.title == "新標題"
        assert r.json()["content_json"] == record["content_json"]
        assert [b["title"] for b in r.json()["buttons"]] == ["遊戲", "活動改", "新增"]

    def test_content_json_filled_when_stored_was_empty(self, client):
        seed(client, 900, [btn(ROLE_OK)])  # 沒有 content_json，從訊息即時讀回
        assert put(client, 900, [btn(ROLE_OK)], {"content": "新", "embed": None}).status_code == 200
        assert from_json(client.repo.messages[900]["content_json"]).content == "新"

    def test_requires_at_least_one_button(self, client):
        seed(client, 900, [btn(ROLE_OK)], content=OLD)
        r = put(client, 900, [])
        assert r.status_code == 400
        assert fields(r) == [("buttons", "至少要有一顆按鈕")]

    def test_limits_and_duplicates(self, client):
        seed(client, 900, [btn(ROLE_OK)], content=OLD)
        assert put(client, 900, [btn(EXTRA_ROLE_BASE + i, f"b{i}") for i in range(26)]).status_code == 400
        assert put(client, 900, [btn(ROLE_OK, "一"), btn(ROLE_OK, "二")]).status_code == 400
        assert put(client, 900, [btn(EXTRA_ROLE_BASE + i, f"b{i}") for i in range(25)]).status_code == 200

    def test_invalid_message_rejected(self, client):
        seed(client, 900, [btn(ROLE_OK)], content=OLD)
        r = put(client, 900, [btn(ROLE_OK)], {"content": "字" * 2001, "embed": None})
        assert r.status_code == 400 and fields(r)[0][0] == "content"

    def test_new_button_checks_apply(self, client):
        seed(client, 900, [btn(ROLE_OK)], content=OLD)
        for role in (ROLE_ABOVE, ROLE_MANAGED, EVERYONE, ROLE_GONE, ROLE_HIGH):
            r = put(client, 900, [btn(ROLE_OK), btn(role, "新")])
            assert r.status_code == 400, role
            assert fields(r)[0][0] == "buttons.1.role_id"
        assert put(client, 900, [btn(ROLE_OK), btn(ROLE_ADMIN, "危險")]).status_code == 200

    def test_foreign_emoji_on_changed_button_rejected(self, client):
        seed(client, 900, [btn(ROLE_OK)], content=OLD)
        r = put(client, 900, [btn(ROLE_OK, emoji=EMOJI_GONE)])
        assert r.status_code == 400 and fields(r)[0][0] == "buttons.0.emoji"

    # --- 衝突 ---
    def test_conflict_on_content(self, client):
        message = seed(client, 900, [btn(ROLE_OK)], content=OLD)
        stale = original(client, 900)
        client.repo.messages[900]["content_json"] = to_json(MessageContent(content="別人改的"))
        r = put(client, 900, [btn(ROLE_OK)], {"content": "我的", "embed": None}, orig=stale)
        assert r.status_code == 409
        body = r.json()
        assert body["error"] == "conflict" and body["deleted"] is False
        assert body["current"]["content"]["content"] == "別人改的"
        assert message.edits == [] and client.repo.replace_calls == 0

    def test_conflict_on_buttons(self, client):
        message = seed(client, 900, [btn(ROLE_OK)], content=OLD)
        stale = original(client, 900)
        client.repo.messages[900]["buttons"].append({"role_id": ROLE_B, "title": "別人加的", "emoji": None, "style": 1})
        r = put(client, 900, [btn(ROLE_OK)], orig=stale)
        assert r.status_code == 409
        assert [b["title"] for b in r.json()["current"]["buttons"]] == ["按鈕", "別人加的"]
        assert message.edits == []

    def test_conflict_when_record_deleted(self, client):
        seed(client, 900, [btn(ROLE_OK)], content=OLD)
        stale = original(client, 900)
        del client.repo.messages[900]
        r = put(client, 900, [btn(ROLE_OK)], orig=stale)
        assert r.status_code == 409
        assert r.json()["deleted"] is True and r.json()["current"] is None

    def test_same_values_round_trip_no_conflict(self, client):
        seed(client, 900, [btn(ROLE_OK, "活動", "🎉", None)], content=OLD)
        assert put(client, 900, [btn(ROLE_OK, "活動", "🎉", None)]).status_code == 200

    # --- 失敗處理 ---
    def test_db_failure_restores_message(self, client):
        embed = discord.Embed(title="舊標題")
        message = seed(client, 900, [btn(ROLE_OK, "活動")], content=OLD, message=FakeMessage(900, "舊內容", [embed]))
        client.repo.fail_replace = True
        r = put(client, 900, [btn(ROLE_B, "換掉")], {"content": "新內容", "embed": None})
        assert r.status_code == 500 and r.json()["error"] == "save_failed"
        assert len(message.edits) == 2
        restore = message.edits[1]
        assert restore["content"] == "舊內容" and restore["embeds"] == [embed]
        assert [c.custom_id for c in restore["view"].children] == [f"ReactionRole_900_{ROLE_OK}"]
        assert client.bot.views[-1][1] is restore["view"]
        assert client.repo.messages[900]["buttons"][0]["role_id"] == ROLE_OK

    def test_db_failure_and_restore_failure_still_reports_error(self, client):
        message = seed(client, 900, [btn(ROLE_OK)], content=OLD)
        client.repo.fail_replace = True
        original_edit = message.edit

        async def edit_then_break(**kwargs):
            await original_edit(**kwargs)
            message.fail_edit = True

        message.edit = edit_then_break  # type: ignore[method-assign]
        r = put(client, 900, [btn(ROLE_B)])
        assert r.status_code == 500 and r.json()["error"] == "save_failed"

    def test_discord_edit_failure_keeps_db(self, client):
        message = seed(client, 900, [btn(ROLE_OK)], content=OLD)
        message.fail_edit = True
        r = put(client, 900, [btn(ROLE_B)])
        assert r.status_code == 502 and r.json()["error"] == "discord_error"
        assert client.repo.replace_calls == 0

    def test_message_gone(self, client):
        seed(client, 900, [btn(ROLE_OK)], content=OLD)
        stale = original(client, 900)
        del client.guild.channel.messages[900]
        r = put(client, 900, [btn(ROLE_OK)], orig=stale)
        assert r.status_code == 404 and r.json()["error"] == "message_not_found"

    # --- content_locked ---
    def test_content_locked_rejects_message(self, client):
        embeds = [discord.Embed(title="一"), discord.Embed(title="二")]
        message = seed(client, 900, [btn(ROLE_OK)], message=FakeMessage(900, "", embeds))
        r = put(client, 900, [btn(ROLE_OK)], {"content": "想改", "embed": None})
        assert r.status_code == 400
        assert r.json() == {"error": "content_locked", "reason": "multiple_embeds"}
        assert message.edits == [] and client.repo.replace_calls == 0

    def test_content_locked_allows_buttons_only(self, client):
        embeds = [discord.Embed(title="一"), discord.Embed(title="二")]
        message = seed(client, 900, [btn(ROLE_OK)], message=FakeMessage(900, "", embeds))
        r = put(client, 900, [btn(ROLE_OK), btn(ROLE_B, "新")], message=None)
        assert r.status_code == 200, r.text
        assert set(message.edits[0]) == {"view"}  # 只動按鈕，不碰內容與 embed
        assert message.embeds == embeds
        assert client.repo.messages[900]["content_json"] is None
        assert len(client.repo.messages[900]["buttons"]) == 2

    # --- 位階與失效 ---
    def test_locked_button_cannot_be_modified_but_can_be_deleted_or_kept(self, client):
        message = seed(client, 900, [btn(ROLE_HIGH, "幹部"), btn(ROLE_OK, "活動")], content=OLD)
        # 修改
        for changed in (btn(ROLE_HIGH, "改標題"), btn(ROLE_HIGH, "幹部", "🎉"), btn(ROLE_HIGH, "幹部", None, 3)):
            r = put(client, 900, [changed, btn(ROLE_OK, "活動")])
            assert r.status_code == 400 and r.json()["error"] == "locked_button", changed
            assert fields(r)[0][0] == "buttons.0.role_id"
        assert message.edits == []
        # 原樣保留（含調整順序）
        assert put(client, 900, [btn(ROLE_OK, "活動"), btn(ROLE_HIGH, "幹部")]).status_code == 200
        # 刪除
        assert put(client, 900, [btn(ROLE_OK, "活動")]).status_code == 200
        assert [b["role_id"] for b in client.repo.messages[900]["buttons"]] == [ROLE_OK]

    def test_command_button_without_style_round_trips_as_unchanged(self, client):
        # /reactrole add 沒指定樣式時 DB 為 None；網頁表單載入時顯示成 1 並原樣送回，不能算有變動
        seed(
            client,
            900,
            [
                btn(ROLE_GONE, "已刪除", None, None),
                btn(ROLE_HIGH, "幹部", None, None),
                btn(ROLE_OK, "活動", None, None),
            ],
            content=OLD,
        )
        orig = original(client, 900)
        assert [b["style"] for b in orig["buttons"]] == [None, None, None]
        same = [btn(ROLE_GONE, "已刪除", None, 1), btn(ROLE_HIGH, "幹部", None, 1), btn(ROLE_OK, "活動", None, 1)]
        r = put(client, 900, same, {"content": "只改內容", "embed": None}, orig=orig)
        assert r.status_code == 200, r.text
        # 失效與高位階按鈕都沒被當成修改；之後只刪別顆也一樣
        assert put(client, 900, same[:2]).status_code == 200
        # 真的改樣式仍會被擋
        r = put(client, 900, [btn(ROLE_HIGH, "幹部", None, 3)])
        assert r.status_code == 400 and r.json()["error"] == "locked_button"

    def test_owner_can_modify_high_button(self, client):
        client.guild.owner_id = ACTOR_ID
        seed(client, 900, [btn(ROLE_HIGH, "幹部")], content=OLD)
        assert put(client, 900, [btn(ROLE_HIGH, "改標題")]).status_code == 200

    def test_invalid_buttons_can_stay_change_or_be_deleted(self, client):
        seed(
            client, 900, [btn(ROLE_GONE, "失效", EMOJI_GONE), btn(ROLE_ABOVE, "過高"), btn(ROLE_OK, "好")], content=OLD
        )
        keep = [btn(ROLE_GONE, "失效", EMOJI_GONE), btn(ROLE_ABOVE, "過高"), btn(ROLE_OK, "好")]
        assert put(client, 900, keep).status_code == 200  # 全部原樣仍可存
        # 只改失效按鈕的標題，身分組仍無效 → 擋下
        r = put(client, 900, [btn(ROLE_GONE, "改名", EMOJI_GONE), *keep[1:]])
        assert r.status_code == 400 and fields(r)[0][0] == "buttons.0.role_id"
        # 換成有效身分組
        assert put(client, 900, [btn(ROLE_B, "換成有效"), *keep[1:]]).status_code == 200
        # 刪除失效按鈕
        assert put(client, 900, [btn(ROLE_OK, "好")]).status_code == 200

    def test_requires_manage_roles(self, client):
        seed(client, 900, [btn(ROLE_OK)], content=OLD)
        orig = {"content_json": client.repo.messages[900]["content_json"], "buttons": [btn(ROLE_OK)]}
        client.discord_env.guilds = [g(str(GUILD_ID), "guild", MANAGE_CHANNELS)]
        assert put(client, 900, [btn(ROLE_OK)], orig=orig).status_code == 403
        assert client.repo.replace_calls == 0


# ====== repository（真實 PostgreSQL） ======
R_GUILD = 8_800_000_000_000_001
R_CHANNEL = 8_800_000_000_000_002
R_OTHER_GUILD = 8_800_000_000_000_003


def option(
    mid: int, rid: int, title: str = "t", position: int = 0, emoji: str | None = None, style: int | None = 1
) -> ReactionRoleOption:
    return ReactionRoleOption(
        message_id=mid, role_id=rid, title=title, description=None, emoji=emoji, style=style, position=position
    )


class TestRepository:
    def test_position_ordering(self, repo):
        mid = 8_800_000_000_000_100
        repo.merge(ReactionRoleMessage(guild_id=R_GUILD, channel_id=R_CHANNEL, message_id=mid))
        for rid, position in [(30, 2), (10, 0), (20, 1), (40, 1)]:
            repo.merge(option(mid, rid, f"r{rid}", position))
        assert [o.role_id for o in repo.get_reaction_roles_by_message(mid)] == [
            10,
            20,
            40,
            30,
        ]  # 同 position 依 role_id
        [(message, options)] = repo.list_guild_reaction_roles(R_GUILD)
        assert message.message_id == mid
        assert [o.role_id for o in options] == [10, 20, 40, 30]

    def test_list_guild_orders_by_message_and_filters_guild(self, repo):
        for mid, guild in [
            (8_800_000_000_000_202, R_GUILD),
            (8_800_000_000_000_201, R_GUILD),
            (8_800_000_000_000_203, R_OTHER_GUILD),
        ]:
            repo.merge(ReactionRoleMessage(guild_id=guild, channel_id=R_CHANNEL, message_id=mid))
            repo.merge(option(mid, 1))
        assert [m.message_id for m, _ in repo.list_guild_reaction_roles(R_GUILD)] == [
            8_800_000_000_000_201,
            8_800_000_000_000_202,
        ]
        assert repo.list_guild_reaction_roles(8_800_000_000_999_999) == []

    def test_new_columns_default(self, repo):
        mid = 8_800_000_000_000_300
        repo.merge(ReactionRoleMessage(guild_id=R_GUILD, channel_id=R_CHANNEL, message_id=mid))
        repo.merge(ReactionRoleOption(message_id=mid, role_id=1, title="t", description=None, emoji=None, style=None))
        assert repo.get_reaction_role_message(mid).content_json is None
        assert repo.get_reaction_roles_by_message(mid)[0].position == 0

    def test_snapshot(self, repo):
        mid = 8_800_000_000_000_400
        assert repo.get_reaction_role_snapshot(mid) is None
        repo.replace_reaction_role_message(
            R_GUILD,
            R_CHANNEL,
            mid,
            '{"content": "x"}',
            [option(mid, 2, "b", emoji="🎉", style=None), option(mid, 1, "a")],
        )
        assert repo.get_reaction_role_snapshot(mid) == {
            "guild_id": R_GUILD,
            "channel_id": R_CHANNEL,
            "content_json": '{"content": "x"}',
            "buttons": [
                {"role_id": 2, "title": "b", "emoji": "🎉", "style": None},
                {"role_id": 1, "title": "a", "emoji": None, "style": 1},
            ],
        }

    def test_replace_creates_then_replaces_options(self, repo):
        mid = 8_800_000_000_000_500
        repo.replace_reaction_role_message(
            R_GUILD, R_CHANNEL, mid, "v1", [option(mid, 1, "a"), option(mid, 2, "b"), option(mid, 3, "c")]
        )
        repo.replace_reaction_role_message(R_GUILD, R_CHANNEL, mid, "v2", [option(mid, 3, "c2"), option(mid, 4, "d")])
        snap = repo.get_reaction_role_snapshot(mid)
        assert snap["content_json"] == "v2"
        assert [(b["role_id"], b["title"]) for b in snap["buttons"]] == [(3, "c2"), (4, "d")]
        assert [(o.role_id, o.position) for o in repo.get_reaction_roles_by_message(mid)] == [(3, 0), (4, 1)]

    def test_replace_renumbers_position_by_list_order(self, repo):
        mid = 8_800_000_000_000_600
        repo.replace_reaction_role_message(
            R_GUILD,
            R_CHANNEL,
            mid,
            "v",
            [option(mid, 9, position=7), option(mid, 5, position=7), option(mid, 7, position=0)],
        )
        assert [(o.role_id, o.position) for o in repo.get_reaction_roles_by_message(mid)] == [(9, 0), (5, 1), (7, 2)]

    def test_replace_keeps_content_when_none(self, repo):
        mid = 8_800_000_000_000_700
        repo.replace_reaction_role_message(R_GUILD, R_CHANNEL, mid, "keep", [option(mid, 1)])
        repo.replace_reaction_role_message(R_GUILD, R_CHANNEL, mid, None, [option(mid, 2)])
        snap = repo.get_reaction_role_snapshot(mid)
        assert snap["content_json"] == "keep" and [b["role_id"] for b in snap["buttons"]] == [2]

    def test_replace_only_touches_that_message(self, repo):
        a, b = 8_800_000_000_000_800, 8_800_000_000_000_801
        repo.replace_reaction_role_message(R_GUILD, R_CHANNEL, a, "a", [option(a, 1)])
        repo.replace_reaction_role_message(R_GUILD, R_CHANNEL, b, "b", [option(b, 1)])
        repo.replace_reaction_role_message(R_GUILD, R_CHANNEL, a, "a2", [option(a, 2)])
        assert [x["role_id"] for x in repo.get_reaction_role_snapshot(b)["buttons"]] == [1]

    def test_replace_is_atomic(self, repo):
        mid = 8_800_000_000_000_900
        repo.replace_reaction_role_message(R_GUILD, R_CHANNEL, mid, "old", [option(mid, 1, "a"), option(mid, 2, "b")])
        with pytest.raises(Exception):  # noqa: B017  重複主鍵 (message_id, role_id) 使 commit 失敗
            repo.replace_reaction_role_message(
                R_GUILD, R_CHANNEL, mid, "new", [option(mid, 3, "x"), option(mid, 3, "y")]
            )
        snap = repo.get_reaction_role_snapshot(mid)
        assert snap["content_json"] == "old"
        assert [b["role_id"] for b in snap["buttons"]] == [1, 2]
