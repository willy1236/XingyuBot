import pytest

from tests.dashboard.test_channel_blocked_terms import audit_entries, bot, host, twitch  # noqa: F401
from tests.twitch.test_blocked_terms_rpc import channel_id, handlers, helix, start_chat  # noqa: F401


@pytest.mark.parametrize("text", ["", "a b*", "a *", "ba*d", "字" * 501])
def test_invalid_blocked_term_returns_field_hint(host, bot, text):
    response = host.post("blocked-terms", json={"text": text})
    assert response.status_code == 422
    assert response.json()["field"] == "text"
    assert response.json()["reason"]
    assert bot.methods == []


def test_duplicate_and_missing_blocked_terms_are_noops(host, bot, twitch):
    twitch.terms["t-1"] = "bad*"

    assert host.post("blocked-terms", json={"text": "bad*"}).json() == {"term": {"id": "t-1", "text": "bad*"}}
    assert host.delete("blocked-terms/missing").status_code == 204
    assert [method for method, _, _ in twitch.requests] == ["GET", "GET"]
    assert audit_entries(host) == []


def test_twitch_blocked_term_rejection_returns_422(host, bot, twitch, monkeypatch):
    send = twitch.request

    async def reject_add(method, url, **kwargs):
        if method == "POST":
            return twitch._ok(400, {"message": "rejected"})
        return await send(method, url, **kwargs)

    # The Helix session binds the stub method when the RPC starts.
    monkeypatch.setattr(twitch, "request", reject_add)
    response = host.post("blocked-terms", json={"text": "abc"})

    assert response.status_code == 422
    assert response.json()["error"] == "invalid_term"
    assert audit_entries(host) == []
