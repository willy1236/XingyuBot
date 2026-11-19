"""後台的析域登入：OIDC 登入、多個 Discord 的選擇、析域登入 session 的失效規則（假 Hydra、假 auth server、假 bot，真實 PostgreSQL）。"""

from __future__ import annotations

import base64
import json
from dataclasses import replace
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest
from authlib.integrations.httpx_client._compat import httpx2 as httpx
from fastapi.testclient import TestClient
from sqlmodel import select

from starlib import sclient
from starlib.database import DashboardSession
from starlib.identity import Account, LinkedPassport, ResolvedAccount
from starServer.dashboard import auth, config, domalyze_login, session
from tests.helpers.accounts import OTHER_ID, FakeBot, account
from tests.helpers.dashboard_auth import FRONTEND, ORIGINS, USER_ID, make_app, make_session, set_cookies

pytestmark = pytest.mark.usefixtures("dashboard_env")

ISSUER = "https://auth.test"
HEADERS = {"Origin": FRONTEND}


class FakeHydra:
    def __init__(self):
        self.account_id = uuid4()
        self.discovery_calls = 0
        self.discovery_fail = False
        self.token_fail = False
        self.token_requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/.well-known/openid-configuration":
            self.discovery_calls += 1
            if self.discovery_fail:
                return httpx.Response(503)
            return httpx.Response(
                200,
                json={
                    "issuer": ISSUER,
                    "authorization_endpoint": f"{ISSUER}/oauth2/auth",
                    "token_endpoint": f"{ISSUER}/oauth2/token",
                    "userinfo_endpoint": f"{ISSUER}/userinfo",
                },
            )
        if path == "/oauth2/token":
            self.token_requests.append(request)
            if self.token_fail:
                return httpx.Response(500)
            return httpx.Response(200, json={"access_token": "at", "token_type": "bearer", "expires_in": 3600})
        if path == "/userinfo":
            assert request.headers["authorization"] == "Bearer at"
            return httpx.Response(200, json={"sub": str(self.account_id)})
        return httpx.Response(404)


class Clock:
    def __init__(self):
        self.now = 1000.0

    def monotonic(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch) -> Clock:
    c = Clock()
    fake = SimpleNamespace(monotonic=c.monotonic)
    monkeypatch.setattr(session, "time", fake)
    monkeypatch.setattr(domalyze_login, "time", fake)
    return c


@pytest.fixture
def hydra(monkeypatch, dashboard_env, repo, clock) -> FakeHydra:
    fake = FakeHydra()
    monkeypatch.setattr(
        config, "oidc_settings", lambda: (ISSUER, "xingyu-website", "s3cret", "https://api.test/oauth/domalyze")
    )
    monkeypatch.setattr(domalyze_login, "_http_transport", httpx.MockTransport(fake))
    monkeypatch.setattr(domalyze_login, "_discovery", None)
    monkeypatch.setattr(domalyze_login, "_pending", {})
    monkeypatch.setattr(sclient, "bot", FakeBot({int(USER_ID): ("Some One", "abc"), int(OTHER_ID): ("Other", None)}))
    return fake


@pytest.fixture
def directory(dashboard_env):
    return dashboard_env.directory


def link(directory, hydra, **kwargs) -> Account:
    acc = account(hydra.account_id, **kwargs)
    directory.by_account_id[hydra.account_id] = ResolvedAccount(acc)
    return acc


def new_client() -> TestClient:
    return TestClient(make_app(), base_url="https://testserver", follow_redirects=False)


def start(client: TestClient, next="/dashboard/guilds/1", origin="https://www.domalyze.net"):
    return client.get("/to/dashboard-domalyze-login", params={"next": next, "origin": origin})


def callback(client: TestClient, **params):
    """先走入口拿到 cookie 與 state，再帶 params 回到 /oauth/domalyze（預設成功授權）。"""
    res = start(client)
    state = parse_qs(urlparse(res.headers["location"]).query)["state"][0]
    return client.get("/oauth/domalyze", params={"code": "c", "state": state, **params})


def login_page(res) -> tuple[str, dict]:
    loc = urlparse(res.headers["location"])
    return f"{loc.scheme}://{loc.netloc}{loc.path}", parse_qs(loc.query)


def oidc_cookie(res) -> dict:
    raw = next(c for c in set_cookies(res) if c.startswith("dashboard_oidc="))
    return json.loads(base64.urlsafe_b64decode(raw.split("dashboard_oidc=")[1].split(";")[0].encode()))


def sessions(repo):
    """這些測試用到的 Discord 的 session（本機資料庫可能有真實的 session）。"""
    repo.session.expire_all()
    ids = [USER_ID, OTHER_ID, "333"]
    return repo.session.exec(select(DashboardSession).where(DashboardSession.discord_user_id.in_(ids))).all()  # pyright: ignore[reportAttributeAccessIssue]


# ====== 入口 ======
class TestEntry:
    def test_redirects_to_auth_server_with_pkce(self, hydra):
        res = start(new_client())
        assert res.status_code == 307
        url = urlparse(res.headers["location"])
        assert f"{url.scheme}://{url.netloc}{url.path}" == f"{ISSUER}/oauth2/auth"
        q = parse_qs(url.query)
        assert q["client_id"] == ["xingyu-website"]
        assert q["redirect_uri"] == ["https://api.test/oauth/domalyze"]
        assert q["scope"] == ["openid profile"]
        assert q["code_challenge_method"] == ["S256"] and q["code_challenge"][0]
        cookie = oidc_cookie(res)
        assert cookie["state"] == q["state"][0] and cookie["verifier"]
        assert (cookie["next"], cookie["origin"]) == ("/dashboard/guilds/1", "https://www.domalyze.net")
        assert any("Max-Age=600" in c and "HttpOnly" in c for c in set_cookies(res) if c.startswith("dashboard_oidc="))

    def test_sanitizes_next_and_origin(self, hydra):
        cookie = oidc_cookie(start(new_client(), next="https://evil.example", origin="https://evil.example"))
        assert (cookie["next"], cookie["origin"]) == ("/dashboard", FRONTEND)

    def test_discovery_failure_back_to_login_and_not_cached(self, hydra):
        hydra.discovery_fail = True
        res = start(new_client())
        assert login_page(res) == (
            "https://www.domalyze.net/dashboard-login",
            {"notice": ["domalyze_unavailable"], "next": ["/dashboard/guilds/1"]},
        )
        hydra.discovery_fail = False
        assert urlparse(start(new_client()).headers["location"]).path == "/oauth2/auth"

    def test_discovery_cached_after_success(self, hydra):
        c = new_client()
        start(c)
        start(c)
        assert hydra.discovery_calls == 1


# ====== 回到 /oauth/domalyze ======
class TestCallback:
    def test_single_discord_logs_in_directly(self, hydra, directory, repo):
        link(directory, hydra)
        c = new_client()
        res = callback(c)
        assert res.headers["location"] == "https://www.domalyze.net/dashboard/guilds/1"
        [row] = sessions(repo)
        assert (row.discord_user_id, row.name, row.avatar) == (USER_ID, "Some One", "abc")
        assert row.account_id == hydra.account_id and row.via_domalyze is True
        assert any(x.startswith("dashboard_oidc=") and "Max-Age=0" in x for x in set_cookies(res))
        assert c.get("/dashboard/me").json()["account"] == {"username": "willy"}
        assert directory.account_calls == 1  # 登入時查過，第一個請求不必再查

    def test_token_request_uses_basic_auth_and_verifier(self, hydra, directory):
        link(directory, hydra)
        c = new_client()
        res = start(c)
        verifier = oidc_cookie(res)["verifier"]
        state = parse_qs(urlparse(res.headers["location"]).query)["state"][0]
        c.get("/oauth/domalyze", params={"code": "c", "state": state})
        [req] = hydra.token_requests
        assert req.headers["authorization"] == "Basic " + base64.b64encode(b"xingyu-website:s3cret").decode()
        body = parse_qs(req.content.decode())
        assert body["grant_type"] == ["authorization_code"] and body["code"] == ["c"]
        assert body["code_verifier"] == [verifier]

    def test_replaces_existing_session(self, hydra, directory, repo):
        link(directory, hydra)
        make_session(repo, user_id=OTHER_ID)
        c = new_client()
        c.cookies.set("dashboard_session", "sid")
        callback(c)
        assert [r.discord_user_id for r in sessions(repo)] == [USER_ID]

    def test_discord_never_seen_uses_id_as_name(self, hydra, directory, repo):
        sclient.bot = FakeBot({})
        link(directory, hydra)
        callback(new_client())
        [row] = sessions(repo)
        assert (row.name, row.avatar) == (USER_ID, None)

    def test_no_discord(self, hydra, directory, repo):
        link(directory, hydra, discord_ids=())
        res = callback(new_client())
        assert login_page(res)[1] == {"notice": ["domalyze_no_discord"], "next": ["/dashboard/guilds/1"]}
        assert sessions(repo) == []

    @pytest.mark.parametrize(("username", "expected_name"), [("willy", "willy"), (None, "析域帳號")])
    def test_twitch_only_account_logs_in_without_discord(self, hydra, directory, repo, username, expected_name):
        acc = replace(
            account(hydra.account_id, discord_ids=(), username=username),
            twitch_passports=(LinkedPassport("7001", "Alpha"),),
        )
        directory.by_account_id[hydra.account_id] = ResolvedAccount(acc)
        c = new_client()

        res = callback(c)

        assert res.headers["location"] == "https://www.domalyze.net/dashboard/guilds/1"
        repo.session.expire_all()
        [row] = repo.session.exec(select(DashboardSession).where(DashboardSession.account_id == hydra.account_id)).all()
        assert (row.discord_user_id, row.twitch_user_id, row.login_method, row.via_domalyze) == (
            None,
            None,
            "domalyze",
            True,
        )
        assert (row.name, row.avatar) == (expected_name, None)
        me = c.get("/dashboard/me").json()
        assert (me["id"], me["discord"], me["twitch"], me["name"], me["avatar_url"], me["has_channels"]) == (
            f"domalyze:{hydra.account_id}",
            None,
            None,
            expected_name,
            None,
            True,
        )
        assert c.get("/dashboard/guilds").json() == {"error": "discord_required"}

    @pytest.mark.parametrize("case", ["suspended", "not_found"])
    def test_denied(self, hydra, directory, repo, case):
        if case == "suspended":
            link(directory, hydra, suspended=True)
        res = callback(new_client())
        assert login_page(res)[1]["notice"] == ["domalyze_denied"]
        assert sessions(repo) == []

    def test_merged_account_uses_survivor(self, hydra, directory, repo):
        survivor = account(uuid4())
        directory.by_account_id[hydra.account_id] = ResolvedAccount(survivor, merged_from=hydra.account_id)
        callback(new_client())
        [row] = sessions(repo)
        assert row.account_id == survivor.account_id

    @pytest.mark.parametrize(
        "params,notice",
        [
            ({"error": "access_denied", "code": None}, "domalyze_denied"),
            ({"error": "server_error", "code": None}, "domalyze_unavailable"),
            ({"code": None}, "domalyze_unavailable"),
        ],
    )
    def test_error_params(self, hydra, directory, params, notice):
        link(directory, hydra)
        res = callback(new_client(), **params)
        page, q = login_page(res)
        assert page == "https://www.domalyze.net/dashboard-login"
        assert q == {"notice": [notice], "next": ["/dashboard/guilds/1"]}

    def test_token_failure(self, hydra, directory):
        link(directory, hydra)
        hydra.token_fail = True
        assert login_page(callback(new_client()))[1]["notice"] == ["domalyze_unavailable"]

    def test_directory_unavailable(self, hydra, directory):
        directory.account_unavailable = True
        assert login_page(callback(new_client()))[1]["notice"] == ["domalyze_unavailable"]

    def test_state_mismatch_keeps_next(self, hydra):
        c = new_client()
        start(c)
        res = c.get("/oauth/domalyze", params={"code": "c", "state": "wrong"})
        assert login_page(res) == (
            "https://www.domalyze.net/dashboard-login",
            {"notice": ["domalyze_expired"], "next": ["/dashboard/guilds/1"]},
        )
        assert any(x.startswith("dashboard_oidc=") and "Max-Age=0" in x for x in set_cookies(res))

    def test_cookie_expired(self, hydra):
        res = new_client().get("/oauth/domalyze", params={"code": "c", "state": "s"})
        assert login_page(res) == (f"{FRONTEND}/dashboard-login", {"notice": ["domalyze_expired"]})

    def test_cookie_values_rechecked(self, hydra, directory):
        link(directory, hydra)
        raw = json.dumps({"state": "s", "verifier": "v", "next": "//evil.example", "origin": "https://evil.example"})
        c = new_client()
        c.cookies.set("dashboard_oidc", base64.urlsafe_b64encode(raw.encode()).decode())
        res = c.get("/oauth/domalyze", params={"code": "c", "state": "s"})
        assert res.headers["location"] == f"{FRONTEND}/dashboard"


# ====== 多個 Discord 的選擇 ======
class TestSelect:
    @pytest.fixture
    def picking(self, hydra, directory) -> TestClient:
        link(directory, hydra, discord_ids=(int(USER_ID), int(OTHER_ID), 333))
        c = new_client()
        res = callback(c)
        assert (
            res.headers["location"] == "https://www.domalyze.net/dashboard-login/select?next=%2Fdashboard%2Fguilds%2F1"
        )
        assert any(x.startswith("dashboard_pick=") and "HttpOnly" in x for x in set_cookies(res))
        return c

    def test_candidates(self, picking, repo):
        assert picking.get("/dashboard/login/candidates").json() == {
            "candidates": [
                {"id": "333", "name": "333", "avatar_url": None},  # 取不到 Discord 使用者
                {
                    "id": USER_ID,
                    "name": "Some One",
                    "avatar_url": f"https://cdn.discordapp.com/avatars/{USER_ID}/abc.png",
                },
                {"id": OTHER_ID, "name": "Other", "avatar_url": auth.avatar_url(OTHER_ID, None)},
            ]
        }
        assert sessions(repo) == []

    def test_select(self, picking, hydra, repo):
        res = picking.post("/dashboard/login/select", json={"discord_user_id": OTHER_ID}, headers=HEADERS)
        assert res.json() == {"redirect": "https://www.domalyze.net/dashboard/guilds/1"}
        assert any(x.startswith("dashboard_pick=") and "Max-Age=0" in x for x in set_cookies(res))
        [row] = sessions(repo)
        assert (row.discord_user_id, row.name, row.account_id, row.via_domalyze) == (
            OTHER_ID,
            "Other",
            hydra.account_id,
            True,
        )
        assert picking.get("/dashboard/me").json()["id"] == OTHER_ID
        # 待選資料用過即刪
        assert picking.get("/dashboard/login/candidates").json() == {"error": "pick_expired"}

    def test_invalid_candidate(self, picking, repo):
        res = picking.post("/dashboard/login/select", json={"discord_user_id": "444"}, headers=HEADERS)
        assert (res.status_code, res.json()) == (400, {"error": "invalid_candidate"})
        assert sessions(repo) == []
        assert picking.get("/dashboard/login/candidates").status_code == 200

    def test_requires_origin(self, picking):
        res = picking.post("/dashboard/login/select", json={"discord_user_id": USER_ID})
        assert res.json() == {"error": "invalid_request"}

    def test_expires_after_10_minutes(self, picking, clock):
        clock.now += 601
        assert picking.get("/dashboard/login/candidates").json() == {"error": "pick_expired"}
        res = picking.post("/dashboard/login/select", json={"discord_user_id": USER_ID}, headers=HEADERS)
        assert (res.status_code, res.json()) == (401, {"error": "pick_expired"})

    def test_without_pick_cookie(self, hydra):
        assert new_client().get("/dashboard/login/candidates").json() == {"error": "pick_expired"}


# ====== 析域登入 session 的失效規則 ======
class TestFollow:
    @pytest.fixture
    def logged_in(self, hydra, directory) -> TestClient:
        link(directory, hydra, discord_ids=(int(USER_ID), int(OTHER_ID)))
        c = new_client()
        callback(c)
        c.post("/dashboard/login/select", json={"discord_user_id": USER_ID}, headers=HEADERS)
        return c

    def me(self, client):
        return client.get("/dashboard/me")

    def test_stays_while_valid(self, logged_in, clock):
        clock.now += 61
        res = self.me(logged_in)
        assert res.status_code == 200 and res.json()["account"] == {"username": "willy"}

    @pytest.mark.parametrize("change", ["suspended", "unlinked", "not_found"])
    def test_invalidated(self, logged_in, hydra, directory, clock, repo, change):
        if change == "suspended":
            link(directory, hydra, discord_ids=(int(USER_ID),), suspended=True)
        elif change == "unlinked":
            link(directory, hydra, discord_ids=(int(OTHER_ID),))
        else:
            directory.by_account_id.clear()
        assert self.me(logged_in).status_code == 200  # 60 秒內不重新確認
        clock.now += 61
        res = self.me(logged_in)
        assert (res.status_code, res.json()) == (401, {"error": "session_expired"})
        assert any(x.startswith("dashboard_session=") and "Max-Age=0" in x for x in set_cookies(res))
        assert sessions(repo) == []

    def test_merge_rewrites_account(self, logged_in, hydra, directory, clock, repo):
        survivor = account(uuid4(), username="survivor")
        directory.by_account_id[hydra.account_id] = ResolvedAccount(survivor, merged_from=hydra.account_id)
        clock.now += 61
        assert self.me(logged_in).json()["account"] == {"username": "survivor"}
        [row] = sessions(repo)
        assert row.account_id == survivor.account_id
        # 之後以存續帳號查詢
        directory.by_account_id[survivor.account_id] = ResolvedAccount(survivor)
        clock.now += 61
        assert self.me(logged_in).status_code == 200

    def test_unavailable_keeps_session(self, logged_in, directory, clock):
        directory.account_unavailable = True
        clock.now += 61
        res = self.me(logged_in)
        assert res.status_code == 200 and res.json()["account"] == {"username": "willy"}

    def test_restart_with_unavailable_uses_db(self, logged_in, directory, clock, monkeypatch):
        monkeypatch.setattr(session, "_followed", {})
        directory.account_unavailable = True
        res = self.me(logged_in)
        assert res.status_code == 200 and res.json()["account"] == {"username": None}


def test_origins_fixture_sanity():
    assert FRONTEND in ORIGINS
