# type: ignore
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock

import pytest

import sentry_bootstrap
from starlib.exceptions import APINetworkError
from starlib.providers import base as providers_base
from starlib.providers.social import platforms

SECRET = "a2R0PVRjNTdUbWc2UVRH"

# ─── CLIInterface._run：例外不帶金鑰 ───────────────────────────────────────────


@pytest.fixture
def cli():
    obj = platforms.CLIInterface.__new__(platforms.CLIInterface)
    obj.rettiwt_api_key = SECRET
    obj.rettiwt_path = "/usr/bin/rettiwt"
    return obj


def _exception_text(exc: BaseException) -> str:
    return f"{exc} {exc!r} {exc.cmd} {exc.__cause__} {exc.__context__}"


def test_run_timeout_hides_key(cli, monkeypatch):
    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, 30)

    monkeypatch.setattr(platforms.subprocess, "run", fake_run)
    with pytest.raises(subprocess.TimeoutExpired) as info:
        cli._run("user", "timeline", "1", "10")
    assert SECRET not in _exception_text(info.value)
    assert info.value.__context__ is None


def test_run_nonzero_exit_hides_key(cli, monkeypatch):
    monkeypatch.setattr(platforms.subprocess, "run", lambda cmd, **kwargs: subprocess.CompletedProcess(cmd, 1, "", "err"))
    with pytest.raises(subprocess.CalledProcessError) as info:
        cli._run("user", "details", "abc")
    assert SECRET not in _exception_text(info.value)


def test_run_passes_key_to_cli(cli, monkeypatch):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, "{}", "")

    monkeypatch.setattr(platforms.subprocess, "run", fake_run)
    cli._run("user", "details", "abc")
    assert seen["cmd"][:3] == ["/usr/bin/rettiwt", "-k", SECRET]


# ─── sentry before_send：指令列表 repr 中的金鑰 ────────────────────────────────


@pytest.mark.parametrize(
    "text",
    [
        f"Command '['/usr/bin/rettiwt', '-k', '{SECRET}', 'user']' timed out after 30 seconds",
        f'Command ["rettiwt", "--key", "{SECRET}"] failed',
        f"rettiwt -k {SECRET} user",
    ],
)
def test_sanitize_hides_key_in_command(text):
    sanitized = sentry_bootstrap._sanitize_data(text)
    assert SECRET not in sanitized
    assert "[Filtered]" in sanitized


# ─── TwitchAPI：token 過期時換新後重試 ─────────────────────────────────────────


def _response(status: int, payload=None):
    return MagicMock(status_code=status, reason="", text="", json=MagicMock(return_value=payload or {}))


@pytest.fixture
def twitch(monkeypatch):
    monkeypatch.setattr(platforms.sqldb, "get_identifier_secret", lambda _: MagicMock(client_id="cid", client_secret="cs"))
    tokens = iter(["old", "new"])
    calls = []

    def fake_request(method, url, headers=None, **kwargs):
        calls.append((method, url, headers))
        if url == platforms.TwitchAPI._TOKEN_URL:
            return _response(200, {"access_token": next(tokens)})
        if headers["Authorization"] == "Bearer old":
            return _response(401)
        return _response(200, {"data": []})

    monkeypatch.setattr(providers_base._session, "request", fake_request)
    api = platforms.TwitchAPI()
    return api, calls


def test_twitch_refreshes_token_on_401(twitch):
    api, calls = twitch
    assert api.get_clips("123") is None
    assert api.headers["Authorization"] == "Bearer new"
    helix_calls = [c for c in calls if c[1] != platforms.TwitchAPI._TOKEN_URL]
    assert [c[2]["Authorization"] for c in helix_calls] == ["Bearer old", "Bearer new"]


def test_twitch_raises_when_still_unauthorized(monkeypatch):
    monkeypatch.setattr(platforms.sqldb, "get_identifier_secret", lambda _: MagicMock(client_id="cid", client_secret="cs"))

    def fake_request(method, url, headers=None, **kwargs):
        if url == platforms.TwitchAPI._TOKEN_URL:
            return _response(200, {"access_token": "t"})
        return _response(401)

    monkeypatch.setattr(providers_base._session, "request", fake_request)
    api = platforms.TwitchAPI()
    with pytest.raises(APINetworkError) as info:
        api.get_clips("123")
    assert info.value.status_code == 401
