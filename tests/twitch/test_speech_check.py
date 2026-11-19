"""starlib.twitch_speech_check：變數代入與頻道 AutoMod 檢查（mock Twitch Helix）。"""

import asyncio
import json

import httpx
import pytest

from starlib import twitch_speech_check as check
from starlib.twitch_tokens import TokenInvalid
from starServer.dashboard import twitch_control

TWITCH_ID = 2000000031


class FakeHelix:
    """記錄收到的請求，依 handler 回應。"""

    def __init__(self, monkeypatch, handler):
        self.requests: list[httpx.Request] = []

        def respond(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return handler(request)

        real = httpx.AsyncClient
        monkeypatch.setattr(check.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(respond), **kw))


def permitted(value: bool):
    return lambda request: httpx.Response(200, json={"data": [{"msg_id": "1", "is_permitted": value}]})


async def credentials(twitch_id: int):
    return "token-1", "client-1"


def run(coro):
    return asyncio.run(coro)


def test_substitute_代入已知變數_未知的原樣保留():
    assert check.substitute("感謝 {user}，已經 {count} 次 {nope} {", {"user": "A", "count": "3"}) == (
        "感謝 A，已經 3 次 {nope} {"
    )


def test_substitute_代入的文字不再展開():
    assert check.substitute("{args}", {"args": "{user}", "user": "X"}) == "{user}"


@pytest.mark.parametrize(
    ("template", "expected"),
    [("hi {touser}", True), ("{args}", True), ("hi {user} {count}", False), ("{{args}", True), ("no vars", False)],
)
def test_uses_viewer_input(template, expected):
    assert check.uses_viewer_input(template) is expected


def test_正常的模板回_ok_並帶正確的請求(monkeypatch):
    helix = FakeHelix(monkeypatch, permitted(True))
    assert run(check.check_template(TWITCH_ID, "感謝 {user} {args}", get_credentials=credentials)) == "ok"
    [request] = helix.requests
    assert request.url.params["broadcaster_id"] == str(TWITCH_ID)
    assert request.headers["Authorization"] == "Bearer token-1"
    assert request.headers["Client-Id"] == "client-1"
    text = json.loads(request.content)["data"][0]["msg_text"]
    assert text == "感謝 觀眾 內容" and "{" not in text  # 變數換成中性文字


def test_被擋下的模板回_blocked(monkeypatch):
    FakeHelix(monkeypatch, permitted(False))
    assert run(check.check_template(TWITCH_ID, "bad", get_credentials=credentials)) == "blocked"


@pytest.mark.parametrize("status", [400, 401, 429, 500])
def test_Twitch_回錯誤或超出限制回_unavailable(monkeypatch, status):
    FakeHelix(monkeypatch, lambda request: httpx.Response(status, json={"message": "x"}))
    assert run(check.check_text(TWITCH_ID, "x", get_credentials=credentials)) == "unavailable"


def test_連線逾時回_unavailable(monkeypatch):
    def timeout(request):
        raise httpx.ConnectTimeout("slow")

    FakeHelix(monkeypatch, timeout)
    assert run(check.check_text(TWITCH_ID, "x", get_credentials=credentials)) == "unavailable"


def test_回應沒有結果回_unavailable(monkeypatch):
    FakeHelix(monkeypatch, lambda request: httpx.Response(200, json={"data": []}))
    assert run(check.check_text(TWITCH_ID, "x", get_credentials=credentials)) == "unavailable"


def test_拿不到_token_回_unavailable_且不打_API(monkeypatch):
    helix = FakeHelix(monkeypatch, permitted(True))

    async def invalid(twitch_id: int):
        return TokenInvalid("revoked")

    assert run(check.check_text(TWITCH_ID, "x", get_credentials=invalid)) == "unavailable"
    assert helix.requests == []


def test_web_端包裝用後台專屬_executor_取_token(monkeypatch):
    seen: list[str] = []

    async def fake_token(twitch_id: int):
        seen.append("token")
        return "token-2"

    monkeypatch.setattr(twitch_control, "broadcaster_token", fake_token)
    monkeypatch.setattr(check, "broadcaster_client_id_blocking", lambda: "client-2")
    helix = FakeHelix(monkeypatch, permitted(True))
    assert run(twitch_control.check_template(TWITCH_ID, "hi")) == "ok"
    assert seen == ["token"]
    assert helix.requests[0].headers["Client-Id"] == "client-2"
