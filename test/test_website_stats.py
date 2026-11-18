"""網站個人區的連結率統計與連結入口點擊（T-10）：假 auth server，真實 PostgreSQL，交易結束後 rollback。"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import select
from test_dashboard_auth import FRONTEND, USER_ID, dashboard_env, make_app, make_session  # noqa: F401
from test_dashboard_domalyze_login import account
from test_identity import repo  # noqa: F401

from starlib import website_stats
from starlib.database import WebsiteLinkClick, WebsiteWeeklyActivity

HEADERS = {"Origin": FRONTEND}
TW = timezone(timedelta(hours=8))
# 2026-11-18 是週三，該週的週一是 11-16
MON = date(2026, 11, 16)
LAST = MON - timedelta(weeks=1)
DID = int(USER_ID)


@pytest.fixture
def now(monkeypatch):
    state = {"value": datetime(2026, 11, 18, 12, 0, tzinfo=TW)}
    monkeypatch.setattr(website_stats, "nowtz", lambda: state["value"])
    return state


def _rows(repo):
    return {(r.week_start, r.discord_id): r.linked for r in repo.session.exec(select(WebsiteWeeklyActivity)).all()}


class TestWeek:
    def test_boundaries_in_taiwan_time(self, now):
        now["value"] = datetime(2026, 11, 16, 0, 0, tzinfo=TW)
        assert website_stats.current_week_start() == MON
        now["value"] = datetime(2026, 11, 22, 23, 59, 59, tzinfo=TW)
        assert website_stats.current_week_start() == MON
        now["value"] = datetime(2026, 11, 23, 0, 0, tzinfo=TW)
        assert website_stats.current_week_start() == MON + timedelta(weeks=1)


class TestRecord:
    def test_two_days_same_week_one_account(self, now, repo):
        website_stats.record_activity(DID)
        now["value"] = datetime(2026, 11, 20, 9, 0, tzinfo=TW)
        website_stats.record_activity(DID)
        assert _rows(repo) == {(MON, DID): None}

    def test_new_week_new_row(self, now, repo):
        website_stats.record_activity(DID)
        now["value"] = datetime(2026, 11, 23, 9, 0, tzinfo=TW)
        website_stats.record_activity(DID)
        assert set(_rows(repo)) == {(MON, DID), (MON + timedelta(weeks=1), DID)}

    def test_existing_row_keeps_linked(self, now, repo):
        repo.record_website_activity(MON, DID)
        repo.set_website_activity_linked(MON, DID, True)
        website_stats.record_activity(DID)  # 重啟後記憶體是空的，資料庫已有的列不被覆蓋
        assert _rows(repo) == {(MON, DID): True}

    def test_request_records_activity(self, now, repo, dashboard_env):
        sid = make_session(repo)
        client = TestClient(make_app())
        client.cookies.set("dashboard_session", sid)
        assert client.get("/dashboard/me").status_code == 200
        assert client.get("/dashboard/me").status_code == 200
        assert _rows(repo) == {(MON, DID): None}

    def test_unauthenticated_request_not_recorded(self, now, repo, dashboard_env):
        assert TestClient(make_app()).get("/dashboard/me").status_code == 401
        assert _rows(repo) == {}


class TestLinkClick:
    def test_click_adds_one(self, now, repo, dashboard_env):
        sid = make_session(repo)
        client = TestClient(make_app())
        client.cookies.set("dashboard_session", sid)
        for _ in range(2):
            assert client.post("/dashboard/personal/link-click", headers=HEADERS).status_code == 204
        assert repo.session.get(WebsiteLinkClick, MON).count == 2

    def test_requires_session(self, now, repo, dashboard_env):
        r = TestClient(make_app()).post("/dashboard/personal/link-click", headers=HEADERS)
        assert r.status_code == 401


class TestSettle:
    def test_settles_finished_weeks_only(self, now, repo, dashboard_env):
        directory = dashboard_env.directory
        directory.accounts[1] = account(uuid4(), discord_ids=(1,))
        directory.accounts[2] = account(uuid4(), discord_ids=(2,), suspended=True)
        for week, did in [(LAST, 1), (LAST, 2), (LAST, 3), (MON, 1)]:
            repo.record_website_activity(week, did)
        assert asyncio.run(website_stats.settle_weeks()) == 3
        assert _rows(repo) == {(LAST, 1): True, (LAST, 2): False, (LAST, 3): False, (MON, 1): None}

    def test_later_link_does_not_change_past(self, now, repo, dashboard_env):
        repo.record_website_activity(LAST, 3)
        asyncio.run(website_stats.settle_weeks())
        dashboard_env.directory.accounts[3] = account(uuid4(), discord_ids=(3,))
        asyncio.run(website_stats.settle_weeks())
        assert _rows(repo) == {(LAST, 3): False}

    def test_directory_unavailable_leaves_null_then_backfills(self, now, repo, dashboard_env):
        directory = dashboard_env.directory
        directory.accounts[1] = account(uuid4(), discord_ids=(1,))
        repo.record_website_activity(LAST, 1)
        directory.unavailable = True
        assert asyncio.run(website_stats.settle_weeks()) == 0
        assert _rows(repo) == {(LAST, 1): None}
        directory.unavailable = False
        assert asyncio.run(website_stats.settle_weeks()) == 1
        assert _rows(repo) == {(LAST, 1): True}


class TestSessionRelease:
    @pytest.mark.parametrize("pending", [False, True])
    def test_session_released_after_settle(self, now, repo, dashboard_env, monkeypatch, pending):
        calls = []
        monkeypatch.setattr(repo, "release_session", lambda: calls.append(1))
        if pending:
            repo.record_website_activity(LAST, 1)
        asyncio.run(website_stats.settle_weeks())
        assert calls  # 沒有待結算列時也要釋放讀取開的交易

    def test_session_released_when_error(self, now, repo, dashboard_env, monkeypatch):
        calls = []
        monkeypatch.setattr(repo, "release_session", lambda: calls.append(1))
        repo.record_website_activity(LAST, 1)
        dashboard_env.directory.unavailable = False

        async def boom(discord_id):
            raise RuntimeError("boom")

        monkeypatch.setattr(dashboard_env.directory, "find_by_discord", boom)
        with pytest.raises(RuntimeError):
            asyncio.run(website_stats.settle_weeks())
        assert calls


class TestReport:
    def test_rate_clicks_and_pending(self, now, repo):
        for did, linked in [(1, True), (2, False), (3, True)]:
            repo.record_website_activity(LAST, did)
            repo.set_website_activity_linked(LAST, did, linked)
        repo.record_website_activity(MON, 1)
        repo.add_website_link_click(MON)
        repo.add_website_link_click(MON)
        old = MON - timedelta(weeks=20)
        repo.record_website_activity(old, 1)
        report = website_stats.weekly_report(8)
        assert [w.week_start for w in report] == [MON, LAST]
        last, current = report[1], report[0]
        assert (last.accounts, last.linked, last.pending, last.clicks) == (3, 2, 0, 0)
        assert last.rate == pytest.approx(2 / 3)
        assert (current.accounts, current.pending, current.clicks) == (1, 1, 2)
        assert current.rate is None

    def test_click_only_week_listed(self, now, repo):
        repo.add_website_link_click(LAST)
        (week,) = website_stats.weekly_report(8)
        assert (week.accounts, week.clicks, week.rate) == (0, 1, None)
