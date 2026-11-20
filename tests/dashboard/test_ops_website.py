"""營運入口的網站部分：每週連結率。"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from starlib import sclient, website_stats
from starlib.website_stats import WeekStats
from starServer.dashboard import ops_website
from tests.helpers.dashboard_auth import FRONTEND, USER_ID, make_app, make_session

pytestmark = pytest.mark.usefixtures("dashboard_env")

BASE = "/dashboard/ops/website"


@pytest.fixture
def owners(monkeypatch):
    owners = {int(USER_ID)}

    async def is_owner(user):
        return user.id in owners

    monkeypatch.setattr(sclient, "bot", SimpleNamespace(is_owner=is_owner))
    return owners


@pytest.fixture
def calls(monkeypatch):
    calls: list[int] = []

    def weekly_report(weeks: int):
        calls.append(weeks)
        return [WeekStats(date(2026, 11, 16), 4, 0, 4, 2), WeekStats(date(2026, 11, 9), 4, 1, 0, 3)]

    monkeypatch.setattr(website_stats, "weekly_report", weekly_report)
    return calls


def client(repo) -> TestClient:
    c = TestClient(make_app(), base_url="https://testserver")
    c.cookies.set("dashboard_session", make_session(repo))
    c.headers["Origin"] = FRONTEND
    return c


def test_non_owner_is_forbidden(repo, owners, calls):
    owners.clear()
    r = client(repo).get(BASE)
    assert (r.status_code, r.json()["error"]) == (403, "not_bot_owner")


def test_returns_weeks_with_rate(repo, owners, calls):
    weeks = client(repo).get(BASE).json()["weeks"]
    assert calls == [ops_website.WEEKS_DEFAULT]
    assert weeks == [
        {"week_start": "2026-11-16", "accounts": 4, "linked": 0, "pending": 4, "clicks": 2, "rate": None},
        {"week_start": "2026-11-09", "accounts": 4, "linked": 1, "pending": 0, "clicks": 3, "rate": 0.25},
    ]


@pytest.mark.parametrize(("asked", "used"), [(0, 1), (52, 52), (100, 52)])
def test_weeks_is_clamped(repo, owners, calls, asked, used):
    client(repo).get(BASE, params={"weeks": asked})
    assert calls == [used]
