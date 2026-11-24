from types import SimpleNamespace
from unittest.mock import Mock

from starlib import twitch_enforcement
from starlib.twitch_audit import AuditActor


def test_clearing_strikes_targets_the_viewer_and_keeps_the_log_id(monkeypatch):
    record = Mock()
    commit = Mock()
    monkeypatch.setattr(twitch_enforcement, "record_change", record)
    monkeypatch.setattr(twitch_enforcement, "sqldb", SimpleNamespace(commit=commit))
    row = SimpleNamespace(id=91, twitch_id=12, user_id=456, user_login="alice", user_name="Alice")
    actor = AuditActor("twitch", "12", "Host")

    twitch_enforcement.record_clear_strikes(row, actor)

    record.assert_called_once_with(
        12,
        actor,
        "dashboard",
        "enforcement",
        "456",
        "update",
        None,
        {"clear_strikes": True, "log_id": 91, "user_id": 456, "user_login": "alice", "user_name": "Alice"},
    )
    commit.assert_called_once()
