"""MessageBus.state：由 Redis 連線的設定與連線狀態推出 up、down、unconfigured（不需要 Redis）。"""

from types import SimpleNamespace

import pytest

from starlib.messaging import MessageBus
from starlib.settings import get_settings


@pytest.fixture
def bus(monkeypatch):
    monkeypatch.setattr(get_settings(), "REDIS_URL", None)
    created = MessageBus(key_prefix="test-state")
    yield created
    created.close()


def test_unset_redis_url_is_unconfigured(bus):
    assert bus.state == "unconfigured"


@pytest.mark.parametrize(("is_up", "expected"), [(True, "up"), (False, "down")])
def test_configured_connection_reports_up_or_down(bus, monkeypatch, is_up, expected):
    monkeypatch.setattr(bus, "_conn", SimpleNamespace(configured=True, is_up=is_up))
    assert bus.state == expected
