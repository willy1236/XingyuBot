# type: ignore
from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest
import requests

from starlib.exceptions import APINetworkError, StarException
from starlib.providers.game.models import ApexMapRotation
from starlib.providers.social import platforms
from starlib.providers.social.platforms import YoutubePush

# ─── StarException ────────────────────────────────────────────────────────────


def test_star_exception_does_not_log_on_creation(caplog):
    with caplog.at_level(logging.DEBUG):
        StarException("boom", original=ValueError("x"))
    assert caplog.records == []


def test_api_network_error_status_code():
    response = MagicMock(status_code=503)
    err = APINetworkError("x", original=requests.HTTPError("HTTP 503", response=response))
    assert err.status_code == 503
    assert APINetworkError("x", original=requests.ConnectionError("reset")).status_code is None


# ─── YoutubePush.add_push ─────────────────────────────────────────────────────


def _response(status: int):
    return MagicMock(status_code=status, reason="", text="")


@pytest.fixture
def push(monkeypatch):
    monkeypatch.setattr(platforms.time, "sleep", lambda _: None)
    return YoutubePush()


def test_add_push_retries_until_success(push, monkeypatch):
    request = MagicMock(side_effect=[_response(503), _response(503), _response(202)])
    monkeypatch.setattr(requests, "request", request)
    assert push.add_push("UC1", "https://cb", "s3cret") is True
    assert request.call_count == 3


def test_add_push_gives_up_without_leaking_secret(push, monkeypatch, caplog):
    request = MagicMock(return_value=_response(503))
    monkeypatch.setattr(requests, "request", request)
    with caplog.at_level(logging.DEBUG):
        assert push.add_push("UC1", "https://cb", "s3cret") is False
    assert request.call_count == push.push_retries
    assert [r.levelno for r in caplog.records] == [logging.WARNING]
    assert all("s3cret" not in str(r.__dict__) for r in caplog.records)


def test_add_push_does_not_retry_client_error(push, monkeypatch):
    request = MagicMock(return_value=_response(400))
    monkeypatch.setattr(requests, "request", request)
    assert push.add_push("UC1", "https://cb") is False
    assert request.call_count == 1


# ─── ApexMapRotation ──────────────────────────────────────────────────────────


def _map(name: str, start: int):
    return {
        "start": start,
        "end": start + 3600,
        "readableDate_start": "",
        "readableDate_end": "",
        "map": name,
        "code": name.lower(),
        "DurationInSecs": 3600,
        "DurationInMinutes": 60,
        "asset": "https://example.com/map.png",
        "eventName": "Mixtape",
    }


def test_map_rotation_without_battle_royale():
    now = 1_790_000_000
    payload = {"ltm": {"current": _map("Kings Canyon", now), "next": _map("Olympus", now + 3600)}}
    rotation = ApexMapRotation(**payload)
    assert rotation.battle_royale is None
    embeds = rotation.embeds()
    assert len(embeds) == 1
