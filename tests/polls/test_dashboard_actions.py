"""伺服器管理後台 V-02：結算與刪除投票（假 Discord，真實 PostgreSQL）。"""

from __future__ import annotations

import asyncio

import discord
import pytest
from apscheduler.jobstores.base import JobLookupError

from starDiscord.uiElement.view import PollView
from starlib import sclient
from starlib.database import PollRole, UserPoll
from starServer.dashboard import polls_actions
from tests.helpers.dashboard_auth import FRONTEND
from tests.helpers.dashboard_notifies import GUILD_ID
from tests.polls.core_helpers import (
    fake_chart,  # noqa: F401  (fixture)
    http_error,
)
from tests.polls.dashboard_helpers import (
    MEMBER,
    OTHER_GUILD,
    VIEWER,
    add_poll,
    client,  # noqa: F401  (fixture)
)

pytestmark = pytest.mark.usefixtures("dashboard_env")

URL = f"/dashboard/guilds/{GUILD_ID}/polls"
HEADERS = {"Origin": FRONTEND}


class FakeMessage:
    def __init__(self, error: Exception | None = None):
        self.edits: list[dict] = []
        self.deleted = 0
        self.error = error

    async def edit(self, **kwargs):
        if self.error:
            raise self.error
        self.edits.append(kwargs)

    async def delete(self):
        if self.error:
            raise self.error
        self.deleted += 1


class FakeChannel:
    name = "投票頻道"

    def __init__(self, message: FakeMessage):
        self.message = message

    def permissions_for(self, member):
        return discord.Permissions(view_channel=True, read_message_history=True, send_messages=True)

    async def fetch_message(self, mid: int):
        if self.message.error:
            raise self.message.error
        return self.message

    def get_partial_message(self, mid: int):
        return self.message


class FakeScheduler:
    """V-04 才有 poll_end_ job；這裡的 job 一律不存在"""

    def __init__(self):
        self.removed: list[str] = []

    def remove_job(self, job_id: str):
        self.removed.append(job_id)
        raise JobLookupError(job_id)


@pytest.fixture
def acl(client, monkeypatch):
    monkeypatch.setattr(polls_actions, "sqldb", client.repo)
    client.message = FakeMessage()
    client.guild.channels[500] = FakeChannel(client.message)
    client.bot.scheduler = FakeScheduler()

    async def fetch_channel(cid: int):
        raise http_error(discord.NotFound, 404)

    client.bot.fetch_channel = fetch_channel
    assert sclient.bot is client.bot
    return client


def end(c, poll_id: int):
    return c.post(f"{URL}/{poll_id}/end", headers=HEADERS)


def delete(c, poll_id: int):
    return c.delete(f"{URL}/{poll_id}", headers=HEADERS)


def as_creator(c, poll):
    """把投票的發起人換成操作者"""
    poll.creator_id = VIEWER
    c.repo.merge(poll)


def stored(c, poll_id: int):
    c.repo.session.expire_all()
    return c.repo.get_poll(poll_id)


class TestEnd:
    def test_creator_ends_and_message_is_updated(self, acl):
        poll = add_poll(acl)
        as_creator(acl, poll)
        r = end(acl, poll.poll_id)
        assert r.status_code == 200
        assert r.json() == {"status": "ok", "message_failure": None, "message_failure_text": None}
        assert stored(acl, poll.poll_id).end_at is not None
        assert len(acl.message.edits) == 1

    def test_non_creator_manager_gets_403(self, acl):
        poll = add_poll(acl)  # 發起人在伺服器裡
        r = end(acl, poll.poll_id)
        assert r.status_code == 403
        assert r.json() == {"error": "not_poll_manager"}
        assert stored(acl, poll.poll_id).end_at is None

    def test_manager_can_end_when_creator_left(self, acl):
        poll = add_poll(acl, creator_id=7999)  # 不在伺服器
        assert end(acl, poll.poll_id).status_code == 200
        assert stored(acl, poll.poll_id).end_at is not None

    def test_bot_owner_can_end_any_poll(self, acl):
        poll = add_poll(acl)
        acl.bot.owner_ids.add(VIEWER)
        assert end(acl, poll.poll_id).status_code == 200

    def test_already_ended_is_success(self, acl):
        poll = add_poll(acl)
        as_creator(acl, poll)
        end(acl, poll.poll_id)
        r = end(acl, poll.poll_id)
        assert r.status_code == 200
        assert r.json()["status"] == "already_ended"
        assert len(acl.message.edits) == 1

    def test_message_deleted_still_ends_and_tells_why(self, acl):
        poll = add_poll(acl)
        as_creator(acl, poll)
        acl.message.error = http_error(discord.NotFound, 404)
        r = end(acl, poll.poll_id)
        assert r.status_code == 200
        assert r.json() == {
            "status": "ok",
            "message_failure": "message_missing",
            "message_failure_text": "投票訊息已被刪除",
        }
        assert stored(acl, poll.poll_id).end_at is not None
        assert stored(acl, poll.poll_id).message_failure == "message_missing"

    def test_old_poll_without_channel_ends_with_reason(self, acl):
        poll = add_poll(acl, channel_id=None)
        as_creator(acl, poll)
        r = end(acl, poll.poll_id)
        assert r.json()["message_failure"] == "message_unknown"
        assert stored(acl, poll.poll_id).end_at is not None

    def test_unknown_or_other_guild_poll_is_404(self, acl):
        other = add_poll(acl, guild_id=OTHER_GUILD)
        assert end(acl, other.poll_id).status_code == 404
        assert end(acl, 999999).json() == {"error": "poll_not_found"}

    def test_deleted_while_ending_is_404(self, acl, monkeypatch):
        """結算更新訊息時投票被刪掉：回 404 poll_not_found，不是 500"""
        from sqlalchemy.orm.exc import StaleDataError

        poll = add_poll(acl)
        as_creator(acl, poll)
        real_merge = acl.repo.merge

        def merge(obj):
            if acl.repo.get_poll(obj.poll_id) is None:
                raise StaleDataError("UPDATE matched 0 rows")
            return real_merge(obj)

        async def edit(**kwargs):
            acl.repo.delete_poll(poll.poll_id)
            raise http_error(discord.NotFound, 404)

        acl.message.edit = edit
        monkeypatch.setattr(acl.repo, "merge", merge)
        r = end(acl, poll.poll_id)
        assert r.status_code == 404
        assert r.json() == {"error": "poll_not_found"}

    def test_requires_manage_messages(self, acl):
        acl.discord_env.guilds = []
        poll = add_poll(acl)
        assert end(acl, poll.poll_id).status_code == 403


class TestDelete:
    def test_creator_deletes_message_and_all_data(self, acl):
        poll = add_poll(acl)
        as_creator(acl, poll)
        acl.repo.add_user_poll(poll.poll_id, MEMBER, 1, poll.created_at, 1)
        acl.repo.merge(PollRole(poll_id=poll.poll_id, role_id=600, is_only_role=True, role_magnification=1))
        r = delete(acl, poll.poll_id)
        assert r.status_code == 200
        assert r.json() == {"status": "ok", "message_failure": None, "message_failure_text": None}
        assert acl.message.deleted == 1
        acl.repo.session.expire_all()
        assert acl.repo.get_poll(poll.poll_id) is None
        assert acl.repo.get_poll_options(poll.poll_id) == []
        assert acl.repo.get_poll_role(poll.poll_id) == []
        assert not acl.repo.session.query(UserPoll).filter(UserPoll.poll_id == poll.poll_id).all()
        assert f"poll_end_{poll.poll_id}" in acl.bot.scheduler.removed

    def test_non_creator_manager_gets_403_and_nothing_is_deleted(self, acl):
        poll = add_poll(acl)
        r = delete(acl, poll.poll_id)
        assert r.status_code == 403
        assert r.json() == {"error": "not_poll_manager"}
        assert acl.message.deleted == 0
        assert stored(acl, poll.poll_id) is not None

    def test_bot_owner_can_delete_any_poll(self, acl):
        poll = add_poll(acl)
        acl.bot.owner_ids.add(VIEWER)
        assert delete(acl, poll.poll_id).json()["status"] == "ok"
        assert stored(acl, poll.poll_id) is None

    def test_message_already_gone_is_success(self, acl):
        poll = add_poll(acl)
        as_creator(acl, poll)
        acl.message.error = http_error(discord.NotFound, 404)
        r = delete(acl, poll.poll_id)
        assert r.json() == {"status": "ok", "message_failure": None, "message_failure_text": None}
        assert stored(acl, poll.poll_id) is None

    def test_channel_gone_is_success(self, acl):
        poll = add_poll(acl)
        as_creator(acl, poll)
        del acl.guild.channels[500]
        r = delete(acl, poll.poll_id)
        assert r.json()["message_failure"] is None
        assert stored(acl, poll.poll_id) is None

    def test_missing_permission_still_deletes_data_and_tells_why(self, acl):
        poll = add_poll(acl)
        as_creator(acl, poll)
        acl.message.error = http_error(discord.Forbidden, 403)
        r = delete(acl, poll.poll_id)
        assert r.status_code == 200
        assert r.json()["message_failure"] == "no_permission"
        assert r.json()["message_failure_text"] == "星羽在頻道缺少權限，無法讀取或編輯投票訊息"
        assert stored(acl, poll.poll_id) is None

    def test_other_http_error_reports_failed(self, acl):
        poll = add_poll(acl)
        as_creator(acl, poll)
        acl.message.error = http_error(discord.HTTPException, 500)
        assert delete(acl, poll.poll_id).json()["message_failure"] == "failed"
        assert stored(acl, poll.poll_id) is None

    def test_old_poll_without_channel_deletes_data(self, acl):
        poll = add_poll(acl, channel_id=None)
        as_creator(acl, poll)
        r = delete(acl, poll.poll_id)
        assert r.json()["message_failure"] == "message_unknown"
        assert acl.message.deleted == 0
        assert stored(acl, poll.poll_id) is None

    def test_deleting_twice_is_success(self, acl):
        poll = add_poll(acl)
        as_creator(acl, poll)
        delete(acl, poll.poll_id)
        r = delete(acl, poll.poll_id)
        assert r.status_code == 200
        assert r.json() == {"status": "already_deleted", "message_failure": None, "message_failure_text": None}

    def test_unknown_and_other_guild_poll_is_already_deleted(self, acl):
        other = add_poll(acl, guild_id=OTHER_GUILD)
        assert delete(acl, other.poll_id).json()["status"] == "already_deleted"
        assert stored(acl, other.poll_id) is not None
        assert delete(acl, 999999).json()["status"] == "already_deleted"

    def test_ended_poll_can_be_deleted(self, acl):
        poll = add_poll(acl, ended=True)
        as_creator(acl, poll)
        assert delete(acl, poll.poll_id).json()["status"] == "ok"
        assert stored(acl, poll.poll_id) is None

    def test_registered_view_is_kept_and_sees_the_poll_gone(self, acl):
        """刪除後 view 不停掉：留在 Discord 上的按鈕 callback 讀不到投票，才會回「此投票已不存在」"""
        poll = add_poll(acl)
        as_creator(acl, poll)

        async def make():
            return PollView(poll, acl.repo, acl.bot)

        view = asyncio.run(make())
        delete(acl, poll.poll_id)
        assert view.reload() is False
        assert not view.is_finished()
