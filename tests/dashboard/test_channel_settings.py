"""實況主後台的頻道設定頁（W-09）：刪除所有資料（真實 PostgreSQL，測完 rollback）。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlmodel import col, func, select

from starlib import twitch_audit, twitch_moderation, twitch_regulars, twitch_tokens
from starlib.database import (
    APIType,
    OAuthToken,
    TwitchAutomodBlock,
    TwitchBotJoinChannel,
    TwitchChannelAudit,
    TwitchChatCommand,
    TwitchEnforcementLog,
    TwitchEventResponse,
    TwitchModerationFilter,
    TwitchModerationSetting,
    TwitchPoint,
    TwitchRegular,
    TwitchTimer,
)
from starlib.messaging import cache_invalidation
from starlib.messaging.rpc import RpcHandlerError
from starlib.twitch_audit import AuditActor, list_changes
from starServer.dashboard import channel_activation, channel_enforcement, channel_settings, channels, twitch_control
from tests.helpers.dashboard_auth import FRONTEND, make_app, make_twitch_session

pytestmark = pytest.mark.usefixtures("dashboard_env")

CHANNEL_ID = 2000000091
OTHER_ID = 2000000092
LOGIN = "Host"
URL = f"/dashboard/channels/{CHANNEL_ID}/delete-data"
HEADERS = {"Origin": FRONTEND}
CACHES = [
    "twitch_channel",
    "twitch_cmd",
    "twitch_timer",
    "twitch_event_response",
    "twitch_moderation",
    "twitch_regular",
]
SEEDED = [1, 1, 1, 1, 1, 1]
EMPTY = [0, 0, 0, 0, 0, 0]


class Spy:
    def __init__(self):
        self.sync_calls: list[int] = []
        self.sync_result: object = twitch_control.SyncResult(joined=False)
        self.invalidated: list[tuple[str, str | None]] = []


@pytest.fixture
def spy(monkeypatch, repo) -> Spy:
    spy = Spy()
    for module in (
        channels,
        channel_settings,
        channel_activation,
        channel_enforcement,
        twitch_audit,
        twitch_moderation,
        twitch_regulars,
    ):
        monkeypatch.setattr(module, "sqldb", repo)

    async def sync_channel(twitch_id):
        spy.sync_calls.append(twitch_id)
        if isinstance(spy.sync_result, Exception):
            raise spy.sync_result
        return spy.sync_result

    monkeypatch.setattr(twitch_control, "sync_channel", sync_channel)
    monkeypatch.setattr(
        cache_invalidation, "invalidate", lambda cache, key=None, **_: spy.invalidated.append((cache, key))
    )
    monkeypatch.setattr(twitch_control, "check_template", AsyncMock(return_value="ok"))
    return spy


@pytest.fixture(autouse=True)
def _fresh_channels(repo):
    # 本機 DB 可能留有手動測試的資料；在外層交易內清掉，測完隨 rollback 還原
    for channel_id in (CHANNEL_ID, OTHER_ID):
        existing = repo.session.get(TwitchBotJoinChannel, channel_id)
        if existing is not None:
            repo.session.delete(existing)
    repo.session.flush()


@pytest.fixture
def credential_id(repo) -> int:
    return repo.get_oauth_client(APIType.Twitch, twitch_tokens.BROADCASTER_CLIENT_SEQ).credential_id


@pytest.fixture
def client(repo) -> TestClient:
    sid = make_twitch_session(repo, twitch_id=str(CHANNEL_ID), login=LOGIN, name="Host")
    c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False)
    c.cookies.set("dashboard_session", sid)
    return c


def _token(repo, credential_id: int, twitch_id: int) -> None:
    repo.merge(
        OAuthToken(
            user_id=str(twitch_id),
            client_credential_id=credential_id,
            access_token="a",
            refresh_token="r",
            scope=["moderation:read"],
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )


def _seed(repo, credential_id: int, twitch_id: int) -> None:
    """一個頻道在各表都有資料。"""
    repo.add(
        TwitchBotJoinChannel(
            twitch_id=twitch_id,
            state="enabled",
            login="host",
            display_name="Host",
            avatar_url="https://example.invalid/a.png",
            first_seen_at=datetime(2026, 1, 1, tzinfo=UTC),
            action_channel_id=99,
            action_guild_id=88,
            point_name="pt",
        )
    )
    repo.add(TwitchChatCommand(twitch_id=twitch_id, name="hi", response="hello"))
    repo.add(TwitchTimer(twitch_id=twitch_id, message="m", interval_minutes=10))
    repo.add(TwitchEventResponse(twitch_id=twitch_id, event_kind="follow", template="t"))
    repo.add(
        TwitchAutomodBlock(twitch_id=twitch_id, source_kind="command", source_key="hi", text="x", reason="automod")
    )
    repo.add(TwitchPoint(twitch_id=1, broadcaster_id=twitch_id, point=5))
    _token(repo, credential_id, twitch_id)


def _count(repo, model, column, value) -> int:
    return repo.session.exec(select(func.count()).select_from(model).where(col(column) == value)).one()


def _data_counts(repo, twitch_id: int) -> list[int]:
    return [
        _count(repo, TwitchChatCommand, TwitchChatCommand.twitch_id, twitch_id),
        _count(repo, TwitchTimer, TwitchTimer.twitch_id, twitch_id),
        _count(repo, TwitchEventResponse, TwitchEventResponse.twitch_id, twitch_id),
        _count(repo, TwitchAutomodBlock, TwitchAutomodBlock.twitch_id, twitch_id),
        _count(repo, TwitchPoint, TwitchPoint.broadcaster_id, twitch_id),
        _count(repo, OAuthToken, OAuthToken.user_id, str(twitch_id)),
    ]


def _moderation_data_counts(repo, twitch_id: int) -> dict[str, int]:
    return {
        model.__tablename__: _count(repo, model, model.twitch_id, twitch_id)
        for model in (TwitchModerationFilter, TwitchModerationSetting, TwitchRegular, TwitchEnforcementLog)
    }


def _get_moderation_data(client, page):
    response = client.get(f"/dashboard/channels/{CHANNEL_ID}/{page}", headers=HEADERS)
    assert response.status_code == 200, response.text
    return response.json()


def _row(repo, twitch_id: int = CHANNEL_ID) -> TwitchBotJoinChannel | None:
    return repo.session.get(TwitchBotJoinChannel, twitch_id, populate_existing=True)


def _state(repo) -> str:
    row = _row(repo)
    assert row is not None
    return row.state


def delete(client, confirm: str = LOGIN):
    return client.post(URL, json={"confirm_login": confirm}, headers=HEADERS)


@pytest.mark.parametrize("confirm", ["", "other", "Host2", "  "])
def test_名稱不符回_400_且資料不變(client, spy, repo, credential_id, confirm):
    _seed(repo, credential_id, CHANNEL_ID)

    response = delete(client, confirm)

    assert response.status_code == 400
    assert response.json() == {"error": "confirm_mismatch"}
    assert _data_counts(repo, CHANNEL_ID) == SEEDED
    assert _state(repo) == "enabled"
    assert list_changes(CHANNEL_ID) == []
    assert spy.sync_calls == []
    assert spy.invalidated == []


def test_已停權的頻道刪除資料後仍是已停權_停權欄位與紀錄保留(client, spy, repo, credential_id):
    _seed(repo, credential_id, CHANNEL_ID)
    banned_at = datetime(2026, 2, 1, tzinfo=UTC)
    row = _row(repo)
    row.banned_at = banned_at
    row.banned_reason = "濫用"
    repo.merge(row)

    assert delete(client).status_code == 200

    after = _row(repo)
    assert (after.banned_at, after.banned_reason, after.state) == (banned_at, "濫用", "inactive")
    assert [e.target_key for e in list_changes(CHANNEL_ID)] == ["all_data"]


@pytest.mark.parametrize("confirm", ["host", "HOST", " Host "])
def test_大小寫與前後空白不影響比對(client, spy, repo, credential_id, confirm):
    _seed(repo, credential_id, CHANNEL_ID)

    assert delete(client, confirm).status_code == 200


def test_刪除後資料清空_頻道列保留顯示欄位(client, spy, repo, credential_id):
    _seed(repo, credential_id, CHANNEL_ID)

    response = delete(client)

    assert response.status_code == 200
    assert response.json() == {"state": "inactive", "bot_offline": False}
    assert _data_counts(repo, CHANNEL_ID) == EMPTY
    row = _row(repo)
    assert row is not None
    assert (row.state, row.action_channel_id, row.action_guild_id, row.point_name) == ("inactive", None, None, None)
    # 其他欄位（W-12 的 banned_at 同理）不動
    assert (row.login, row.display_name, row.avatar_url) == ("host", "Host", "https://example.invalid/a.png")
    assert row.first_seen_at == datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def moderation_defaults(client, spy, repo, credential_id):
    _seed(repo, credential_id, CHANNEL_ID)
    defaults = _get_moderation_data(client, "moderation")
    link = next(row for row in defaults["filters"] if row["kind"] == "link")
    repo.add(
        TwitchModerationFilter(
            twitch_id=CHANNEL_ID, kind="link", enabled=True, exempt_level="regular", params=link["params"], silent=False
        )
    )
    repo.add(
        TwitchModerationSetting(
            twitch_id=CHANNEL_ID,
            stages=defaults["settings"]["stages"],
            strike_reset_minutes=30,
            raid_pause_seconds=90,
            permit_seconds=45,
        )
    )
    repo.add(TwitchRegular(twitch_id=CHANNEL_ID, user_id=11, user_login="viewer", user_name="Viewer"))
    repo.add(
        TwitchEnforcementLog(
            twitch_id=CHANNEL_ID,
            user_id=22,
            user_login="chatter",
            user_name="Chatter",
            filter="link",
            strike=1,
            action="delete",
            message="https://example.invalid",
            status="success",
        )
    )
    return defaults


def test_刪除聊天室管理資料後重新啟用從空白開始(client, repo, moderation_defaults):
    seeded = _moderation_data_counts(repo, CHANNEL_ID)
    assert set(seeded.values()) == {1}
    response = delete(client)

    assert response.status_code == 200, response.text
    assert _state(repo) == "inactive"
    assert _moderation_data_counts(repo, CHANNEL_ID) == dict.fromkeys(seeded, 0)

    # 授權流程已有獨立測試，這裡直接將測試頻道恢復為已啟用。
    row = _row(repo)
    assert row is not None
    row.state = "enabled"
    repo.merge(row)
    moderation = _get_moderation_data(client, "moderation")
    assert moderation == moderation_defaults
    assert all(item["enabled"] is False for item in moderation["filters"])
    assert _get_moderation_data(client, "regulars")["regulars"] == []
    assert _get_moderation_data(client, "enforcement")["entries"] == []


def test_不影響其他頻道的資料(client, spy, repo, credential_id):
    _seed(repo, credential_id, CHANNEL_ID)
    _seed(repo, credential_id, OTHER_ID)

    delete(client)

    assert _data_counts(repo, OTHER_ID) == SEEDED
    other = _row(repo, OTHER_ID)
    assert other is not None
    assert (other.state, other.action_channel_id, other.action_guild_id, other.point_name) == ("enabled", 99, 88, "pt")


def test_修改紀錄保留(client, repo, moderation_defaults):
    actor = AuditActor("twitch", str(CHANNEL_ID), "Host")
    twitch_audit.record_change(CHANNEL_ID, actor, "dashboard", "command", "hi", "create", None, {"response": "hello"})
    twitch_audit.record_change(CHANNEL_ID, actor, "dashboard", "moderation", "link", "update", None, {"enabled": True})
    twitch_audit.record_change(CHANNEL_ID, actor, "dashboard", "regular", "11", "create", None, {"login": "viewer"})
    repo.commit()

    assert delete(client).status_code == 200

    entries = list_changes(CHANNEL_ID)
    assert {(e.target_kind, e.target_key) for e in entries} == {
        ("channel", "all_data"),
        ("command", "hi"),
        ("moderation", "link"),
        ("regular", "11"),
    }
    assert _count(repo, TwitchChannelAudit, TwitchChannelAudit.twitch_id, CHANNEL_ID) == 4


def test_刪除本身記一筆頻道層級的紀錄(client, spy, repo, credential_id):
    _seed(repo, credential_id, CHANNEL_ID)

    delete(client)

    [entry] = list_changes(CHANNEL_ID)
    assert (entry.source, entry.target_kind, entry.target_key, entry.action) == (
        "dashboard",
        "channel",
        "all_data",
        "delete",
    )
    assert (entry.actor.platform, entry.actor.id, entry.actor.name) == ("twitch", str(CHANNEL_ID), "Host")
    assert entry.before == {"action_channel_id": 99, "action_guild_id": 88, "point_name": "pt"}
    assert entry.after is None
    assert entry.at is not None


def test_沒有頻道列時紀錄的_before_是空(client, spy, repo, credential_id):
    _token(repo, credential_id, CHANNEL_ID)

    delete(client)

    [entry] = list_changes(CHANNEL_ID)
    assert entry.before is None


def test_紀錄寫入後提交失敗時紀錄與刪除一併_rollback(client, spy, repo, credential_id, monkeypatch):
    """紀錄與刪除在同一個交易：到 commit 才失敗，紀錄不能單獨留下。"""
    _seed(repo, credential_id, CHANNEL_ID)

    def broken_commit():
        raise RuntimeError("commit failed")

    monkeypatch.setattr(repo, "commit", broken_commit)

    response = delete(client)

    assert response.status_code == 500
    assert list_changes(CHANNEL_ID) == []
    assert _data_counts(repo, CHANNEL_ID) == SEEDED
    assert _state(repo) == "enabled"


def test_讓_bot_離開並通知所有快取(client, spy, repo, credential_id):
    _seed(repo, credential_id, CHANNEL_ID)

    delete(client)

    assert spy.sync_calls == [CHANNEL_ID]
    assert sorted(spy.invalidated) == sorted((cache, str(CHANNEL_ID)) for cache in CACHES)


@pytest.mark.parametrize("state", ["inactive", "disabled", "enabled"])
def test_任何_state_都能刪(client, spy, repo, credential_id, state):
    _seed(repo, credential_id, CHANNEL_ID)
    row = _row(repo)
    assert row is not None
    row.state = state
    repo.merge(row)

    response = delete(client)

    assert response.json() == {"state": "inactive", "bot_offline": False}
    assert _state(repo) == "inactive"


def test_沒有頻道列時資料照刪(client, spy, repo, credential_id):
    repo.add(TwitchChatCommand(twitch_id=CHANNEL_ID, name="hi", response="hello"))
    _token(repo, credential_id, CHANNEL_ID)

    response = delete(client)

    assert response.status_code == 200
    assert _data_counts(repo, CHANNEL_ID) == EMPTY
    assert _row(repo) is None


def test_bot_離線時資料仍刪除(client, spy, repo, credential_id):
    _seed(repo, credential_id, CHANNEL_ID)
    spy.sync_result = twitch_control.BotOffline()

    response = delete(client)

    assert response.json() == {"state": "inactive", "bot_offline": True}
    assert _data_counts(repo, CHANNEL_ID) == EMPTY
    assert _state(repo) == "inactive"


def test_bot_內部出錯也回_bot_offline(client, spy, repo, credential_id):
    _seed(repo, credential_id, CHANNEL_ID)
    spy.sync_result = RpcHandlerError("boom")

    response = delete(client)

    assert response.status_code == 200
    assert response.json()["bot_offline"] is True
    assert _data_counts(repo, CHANNEL_ID) == EMPTY


def test_途中失敗整筆_rollback(client, spy, repo, credential_id, monkeypatch):
    _seed(repo, credential_id, CHANNEL_ID)

    def broken(*args, **kwargs):
        raise RuntimeError("db down")

    # 功能資料已刪之後才失敗：確認前面的刪除一併 rollback
    monkeypatch.setattr(repo, "get_oauth_client", broken)

    response = delete(client)

    assert response.status_code == 500
    assert _data_counts(repo, CHANNEL_ID) == SEEDED
    assert _state(repo) == "enabled"
    assert list_changes(CHANNEL_ID) == []
    assert spy.sync_calls == []


def test_不是自己的頻道回_403(spy, repo, credential_id, client):
    _seed(repo, credential_id, OTHER_ID)

    response = client.post(
        f"/dashboard/channels/{OTHER_ID}/delete-data", json={"confirm_login": LOGIN}, headers=HEADERS
    )

    assert response.status_code == 403
    assert response.json() == {"error": "channel_forbidden"}
    assert _data_counts(repo, OTHER_ID) == SEEDED


def test_未登入回_401(spy):
    c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False)

    response = c.post(URL, json={"confirm_login": LOGIN}, headers=HEADERS)

    assert response.status_code == 401
    assert response.json() == {"error": "session_expired"}


def test_刪除後頻道_GET_是未啟用(client, spy, repo, credential_id):
    _seed(repo, credential_id, CHANNEL_ID)

    delete(client)

    assert client.get(f"/dashboard/channels/{CHANNEL_ID}").json()["state"] == "inactive"
