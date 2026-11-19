"""session.audit_actor：Twitch、Discord、沒有 Discord 的析域三種 session 各自記成哪個操作者。"""

from uuid import UUID

import pytest

from starlib.twitch_audit import AuditActor
from starServer.dashboard.session import SessionInfo, TwitchIdentity, audit_actor

ACCOUNT_ID = UUID("6f1c2a9e-0000-4000-8000-000000000001")
TWITCH = TwitchIdentity("777", "streamer", "Streamer", None)


def test_twitch_login_is_twitch_account():
    info = SessionInfo("s", None, "Streamer", None, login_method="twitch", twitch=TWITCH, twitch_channels=(TWITCH,))
    assert audit_actor(info) == AuditActor("twitch", "777", "Streamer")


def test_discord_login_is_discord_account():
    assert audit_actor(SessionInfo("s", "111", "Some One", None)) == AuditActor("discord", "111", "Some One")


def test_domalyze_login_with_discord_is_discord_account():
    info = SessionInfo(
        "s", "111", "Some One", None, account_id=ACCOUNT_ID, account_username="willy", login_method="domalyze"
    )
    assert audit_actor(info) == AuditActor("discord", "111", "Some One")


def test_domalyze_login_without_discord_is_domalyze_account():
    info = SessionInfo(
        "s", None, "willy", None, account_id=ACCOUNT_ID, account_username="willy", login_method="domalyze"
    )
    assert audit_actor(info) == AuditActor("domalyze", str(ACCOUNT_ID), "willy")


def test_domalyze_name_falls_back_to_session_name_when_username_unknown():
    info = SessionInfo("s", None, "析域帳號", None, account_id=ACCOUNT_ID, login_method="domalyze")
    assert audit_actor(info) == AuditActor("domalyze", str(ACCOUNT_ID), "析域帳號")


def test_session_without_any_identity_is_rejected():
    with pytest.raises(ValueError):
        audit_actor(SessionInfo("s", None, "x", None))
