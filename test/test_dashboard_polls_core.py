"""投票核心 V-00：結算（鎖、重讀、訊息更新）、建立並發送、刪除（假 Discord，真實 PostgreSQL）。"""

from __future__ import annotations

import asyncio
import io
from datetime import timedelta
from types import SimpleNamespace

import discord
import pytest
from sqlmodel import select
from test_identity import repo  # noqa: F401

from starDiscord.uiElement import view as view_module
from starDiscord.uiElement.view import PollEndButton, PollSendError, PollView
from starlib.database import Poll, PollOption, PollRole
from starlib.utils import nowtz

GUILD_ID = 1001
CHANNEL_ID = 500
MESSAGE_ID = 900
CREATOR = 7001


@pytest.fixture(autouse=True)
def fake_chart(monkeypatch):
    """圓餅圖的繪製不在這裡測；matplotlib 的視窗後端在無 Tk 的環境會失敗"""
    monkeypatch.setattr(PollView, "generate_chart", lambda self, labels, sizes: io.BytesIO(b"png"))


def http_error(cls, status: int):
    return cls(SimpleNamespace(status=status, reason="error"), "error")


class FakeMessage:
    def __init__(self, error: Exception | None = None):
        self.id = MESSAGE_ID
        self.edits: list[dict] = []
        self.error = error

    async def edit(self, **kwargs):
        if self.error:
            raise self.error
        self.edits.append(kwargs)


class FakeChannel:
    def __init__(self, message: FakeMessage | None, fetch_error: Exception | None = None):
        self.message = message
        self.fetch_error = fetch_error

    async def fetch_message(self, mid: int):
        if self.fetch_error:
            raise self.fetch_error
        if self.message is None:
            raise http_error(discord.NotFound, 404)
        return self.message


class FakeGuild:
    def __init__(self, channel: FakeChannel | None):
        self.channel = channel

    def get_member(self, uid: int):
        return None

    def get_channel_or_thread(self, cid: int):
        return self.channel if cid == CHANNEL_ID else None


class FakeBot:
    def __init__(self, channel: FakeChannel | None):
        self.guild = FakeGuild(channel)
        self.fetched = 0

    def get_guild(self, gid: int):
        return self.guild if gid == GUILD_ID else None

    async def fetch_channel(self, cid: int):
        self.fetched += 1
        raise http_error(discord.NotFound, 404)


def add_poll(repo, *, channel_id: int | None = CHANNEL_ID, created_days_ago=1, votes=True) -> Poll:  # noqa: F811
    poll = Poll(
        title="投票",
        creator_id=CREATOR,
        created_at=nowtz().replace(microsecond=0) - timedelta(days=created_days_ago),
        guild_id=GUILD_ID,
        channel_id=channel_id,
        message_id=MESSAGE_ID,
        end_at=None,
        number_of_user_votes=1,
        ban_alternate_account_voting=False,
        show_name=True,
        check_results_in_advance=True,
        results_only_initiator=False,
        can_change_vote=None,
    )
    repo.add(poll)
    repo.add_poll_option(poll.poll_id, ["甲", "乙"])
    if votes:
        repo.add_user_poll(poll.poll_id, 1, 1, nowtz().replace(microsecond=0), 2)
        repo.add_user_poll(poll.poll_id, 2, 2, nowtz().replace(microsecond=0), 1)
    return poll


def stored(repo, poll_id: int) -> Poll:  # noqa: F811
    repo.session.expire_all()
    return repo.get_poll(poll_id)


def run_finish(repo, poll: Poll, bot: FakeBot, edit=None, times: int = 1):  # noqa: F811
    async def go():
        views = [PollView(poll, repo, bot) for _ in range(times)]  # type: ignore[arg-type]
        return await asyncio.gather(*(v.finish(edit=edit) for v in views))

    return asyncio.run(go())


class TestFinish:
    def test_edits_message_and_ends(self, repo):  # noqa: F811
        message = FakeMessage()
        poll = add_poll(repo)
        (outcome,) = run_finish(repo, poll, FakeBot(FakeChannel(message)))
        assert (outcome.status, outcome.message_failure) == ("ok", None)
        row = stored(repo, poll.poll_id)
        assert row.end_at is not None
        assert row.message_failure is None
        [edit] = message.edits
        assert "甲： 2票" in edit["embed"].description
        assert edit["file"].filename == "pie.png"
        assert len(edit["view"].children) == 0

    def test_unknown_channel_records_message_unknown(self, repo):  # noqa: F811
        poll = add_poll(repo, channel_id=None)
        (outcome,) = run_finish(repo, poll, FakeBot(FakeChannel(FakeMessage())))
        assert (outcome.status, outcome.message_failure) == ("ok", "message_unknown")
        assert outcome.message_failure_text
        row = stored(repo, poll.poll_id)
        assert row.end_at is not None
        assert row.message_failure == "message_unknown"

    def test_message_deleted(self, repo):  # noqa: F811
        poll = add_poll(repo)
        (outcome,) = run_finish(repo, poll, FakeBot(FakeChannel(None)))
        assert outcome.message_failure == "message_missing"
        assert stored(repo, poll.poll_id).end_at is not None

    def test_channel_deleted(self, repo):  # noqa: F811
        poll = add_poll(repo)
        (outcome,) = run_finish(repo, poll, FakeBot(None))
        assert outcome.message_failure == "channel_missing"

    @pytest.mark.parametrize(
        ("error", "code"),
        [(http_error(discord.Forbidden, 403), "no_permission"), (http_error(discord.HTTPException, 500), "failed")],
    )
    def test_edit_errors(self, repo, error, code):  # noqa: F811
        poll = add_poll(repo)
        (outcome,) = run_finish(repo, poll, FakeBot(FakeChannel(FakeMessage(error))))
        assert outcome.message_failure == code
        assert stored(repo, poll.poll_id).message_failure == code

    def test_fetch_forbidden(self, repo):  # noqa: F811
        poll = add_poll(repo)
        channel = FakeChannel(None, fetch_error=http_error(discord.Forbidden, 403))
        (outcome,) = run_finish(repo, poll, FakeBot(channel))
        assert outcome.message_failure == "no_permission"

    def test_edit_callback_skips_fetch_and_works_for_unknown_channel(self, repo):  # noqa: F811
        poll = add_poll(repo, channel_id=None)
        calls: list[dict] = []

        async def edit(**kwargs):
            calls.append(kwargs)

        (outcome,) = run_finish(repo, poll, FakeBot(None), edit=edit)
        assert (outcome.status, outcome.message_failure) == ("ok", None)
        assert len(calls) == 1
        assert stored(repo, poll.poll_id).message_failure is None

    def test_edit_callback_error_is_recorded(self, repo):  # noqa: F811
        poll = add_poll(repo)

        async def edit(**kwargs):
            raise http_error(discord.NotFound, 404)

        (outcome,) = run_finish(repo, poll, FakeBot(None), edit=edit)
        assert outcome.message_failure == "message_missing"

    def test_second_finish_is_already_ended(self, repo):  # noqa: F811
        poll = add_poll(repo)
        bot = FakeBot(FakeChannel(FakeMessage()))
        run_finish(repo, poll, bot)
        (outcome,) = run_finish(repo, poll, bot)
        assert outcome.status == "already_ended"

    def test_concurrent_finish_ends_once(self, repo):  # noqa: F811
        message = FakeMessage()
        poll = add_poll(repo)
        outcomes = run_finish(repo, poll, FakeBot(FakeChannel(message)), times=2)
        assert sorted(o.status for o in outcomes) == ["already_ended", "ok"]
        assert len(message.edits) == 1

    def test_stale_instance_is_reloaded(self, repo):  # noqa: F811
        poll = add_poll(repo)
        bot = FakeBot(FakeChannel(FakeMessage()))
        stale = PollView

        async def go():
            old = stale(poll, repo, bot)  # type: ignore[arg-type]
            other = stale(poll, repo, bot)  # type: ignore[arg-type]
            await other.finish()
            return await old.finish()

        assert asyncio.run(go()).status == "already_ended"

    def test_not_found(self, repo):  # noqa: F811
        poll = add_poll(repo)
        repo.delete_poll(poll.poll_id)
        (outcome,) = run_finish(repo, poll, FakeBot(None))
        assert outcome.status == "not_found"


class TestDeletePoll:
    def test_removes_all_related_rows_only_for_that_poll(self, repo):  # noqa: F811
        poll = add_poll(repo)
        other = add_poll(repo)
        repo.merge(PollRole(poll_id=poll.poll_id, role_id=1, is_only_role=True, role_magnification=1))
        repo.merge(PollRole(poll_id=other.poll_id, role_id=1, is_only_role=True, role_magnification=1))
        repo.delete_poll(poll.poll_id)
        repo.session.expire_all()
        assert repo.get_poll(poll.poll_id) is None
        assert repo.get_poll_options(poll.poll_id) == []
        assert repo.get_poll_role(poll.poll_id) == []
        assert repo.get_users_poll(poll.poll_id) == []
        assert repo.get_poll(other.poll_id) is not None
        assert len(repo.get_poll_options(other.poll_id)) == 2
        assert len(repo.get_poll_role(other.poll_id)) == 1
        assert len(repo.get_users_poll(other.poll_id)) == 2

    def test_missing_poll_is_noop(self, repo):  # noqa: F811
        repo.delete_poll(99999999)


def create_kwargs(**overrides):
    kwargs = {
        "bot": FakeBot(FakeChannel(FakeMessage())),
        "creator_id": CREATOR,
        "guild_id": GUILD_ID,
        "title": "標題",
        "options": ["甲", "乙", "丙"],
        "show_name": False,
        "check_results_in_advance": True,
        "results_only_initiator": False,
        "number_of_user_votes": 2,
        "ban_alternate_account_voting": False,
        "only_roles": [10],
        "role_weights": {10: 3, 11: 5},
    }
    kwargs.update(overrides)
    return kwargs


class TestCreateAndSend:
    def make(self, repo, monkeypatch, send, **overrides):  # noqa: F811
        monkeypatch.setattr(view_module, "sqldb", repo)

        async def go():
            guild = SimpleNamespace(get_member=lambda uid: None, get_role=lambda rid: None)
            kwargs = create_kwargs(**overrides)
            kwargs["bot"].get_guild = lambda gid: guild
            return await PollView.create_and_send(send, CHANNEL_ID, **kwargs)

        return asyncio.run(go())

    def test_stores_message_channel_options_and_roles(self, repo, monkeypatch):  # noqa: F811
        sent = []

        async def send(embed, view):
            sent.append((embed, view))
            return SimpleNamespace(id=777)

        poll = self.make(repo, monkeypatch, send)
        repo.session.expire_all()
        row = repo.get_poll(poll.poll_id)
        assert (row.message_id, row.channel_id) == (777, CHANNEL_ID)
        assert (row.title, row.creator_id, row.number_of_user_votes, row.can_change_vote) == ("標題", CREATOR, 2, None)
        assert [o.option_name for o in repo.get_poll_options(poll.poll_id)] == ["甲", "乙", "丙"]
        roles = {r.role_id: (r.is_only_role, r.role_magnification) for r in repo.get_poll_role(poll.poll_id)}
        assert roles == {10: (True, 3), 11: (False, 5)}
        assert len(sent) == 1

    @pytest.mark.parametrize(
        ("error", "code"),
        [
            (http_error(discord.Forbidden, 403), "no_permission"),
            (http_error(discord.NotFound, 404), "channel_missing"),
            (http_error(discord.HTTPException, 500), "failed"),
        ],
    )
    def test_send_failure_removes_poll(self, repo, monkeypatch, error, code):  # noqa: F811
        before = len(repo.session.exec(select(Poll)).all())

        async def send(embed, view):
            raise error

        with pytest.raises(PollSendError) as exc:
            self.make(repo, monkeypatch, send)
        assert exc.value.code == code
        repo.session.expire_all()
        assert len(repo.session.exec(select(Poll)).all()) == before
        assert repo.session.exec(select(PollOption).where(PollOption.option_name == "丙")).all() == []


class TestEndButton:
    def click(self, repo, poll, *, edit=None, user_id=CREATOR):  # noqa: F811
        followups: list[tuple[str, bool]] = []

        async def defer():
            pass

        async def default_edit(**kwargs):
            pass

        async def followup(text, ephemeral=False):
            followups.append((text, ephemeral))

        interaction = SimpleNamespace(
            user=SimpleNamespace(id=user_id),
            response=SimpleNamespace(defer=defer),
            edit_original_response=edit or default_edit,
            followup=SimpleNamespace(send=followup),
        )

        async def go():
            view = PollView(poll, repo, FakeBot(None))  # type: ignore[arg-type]
            button = next(c for c in view.children if isinstance(c, PollEndButton))
            await button.callback(interaction)

        asyncio.run(go())
        return followups

    def test_success_has_no_followup(self, repo):  # noqa: F811
        assert self.click(repo, add_poll(repo)) == []

    def test_message_failure_is_told_to_the_clicker(self, repo):  # noqa: F811
        async def edit(**kwargs):
            raise http_error(discord.NotFound, 404)

        poll = add_poll(repo)
        assert self.click(repo, poll, edit=edit) == [("投票已結算，但投票訊息已被刪除", True)]
        assert stored(repo, poll.poll_id).end_at is not None

    def test_already_ended(self, repo):  # noqa: F811
        poll = add_poll(repo)
        self.click(repo, poll)
        assert self.click(repo, poll) == [("此投票已結算", True)]


class TestCreateAndSendOrphan:
    @pytest.mark.parametrize("delete_error", [None, http_error(discord.Forbidden, 403)])
    def test_db_failure_after_send_deletes_message_and_poll(self, repo, monkeypatch, delete_error):  # noqa: F811
        monkeypatch.setattr(view_module, "sqldb", repo)
        message = SimpleNamespace(id=777, deleted=False)

        async def delete():
            if delete_error:
                raise delete_error
            message.deleted = True

        message.delete = delete

        async def send(embed, view):
            return message

        real_merge = repo.merge

        def merge(obj):
            if isinstance(obj, Poll):
                raise RuntimeError("db down")
            return real_merge(obj)

        monkeypatch.setattr(repo, "merge", merge)
        before = len(repo.session.exec(select(Poll)).all())

        async def go():
            kwargs = create_kwargs()
            kwargs["bot"].get_guild = lambda gid: SimpleNamespace(
                get_member=lambda uid: None, get_role=lambda rid: None
            )
            await PollView.create_and_send(send, CHANNEL_ID, **kwargs)

        with pytest.raises(RuntimeError, match="db down"):
            asyncio.run(go())
        assert message.deleted is (delete_error is None)
        repo.session.expire_all()
        assert len(repo.session.exec(select(Poll)).all()) == before


class TestMissingPermissions:
    def test_text_channel(self):
        perms = discord.Permissions(view_channel=True)
        assert PollView.missing_permissions(SimpleNamespace(), perms) == ["讀取訊息歷史", "發送訊息"]

    def test_thread_uses_thread_send_permission(self):
        perms = discord.Permissions(view_channel=True, read_message_history=True, send_messages=True)
        thread = discord.Thread.__new__(discord.Thread)
        assert PollView.missing_permissions(thread, perms) == ["在討論串發送訊息"]
