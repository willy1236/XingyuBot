"""C-08：`channel:manage:broadcast` 權限的判斷。新權限單獨放在 `STREAM_INFO_SCOPES`，不影響既有頻道的狀態判定與營運入口。"""

from datetime import UTC, datetime, timedelta

from starlib import twitch_tokens
from starlib.database import OAuthToken
from starlib.twitch_tokens import ENABLE_SCOPES, missing_scopes, token_state
from starServer.dashboard import channel_health as health
from starServer.dashboard.channel_health import ChannelHealth
from tests.twitch.test_channel_health import (
    run,
    twitch,  # noqa: F401 (fixture)
)

SCOPE = "channel:manage:broadcast"


def token(scope):
    return OAuthToken(
        user_id="1",
        client_credential_id=1,
        access_token="a",
        refresh_token="r",
        scope=list(scope),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


def test_STREAM_INFO_SCOPES_只有改標題的權限():
    assert twitch_tokens.STREAM_INFO_SCOPES == [SCOPE]


def test_改標題的權限不在_ENABLE_SCOPES():
    assert SCOPE not in ENABLE_SCOPES


def test_有改標題權限的_token_回_True():
    assert twitch_tokens.has_stream_info_scope(token([*ENABLE_SCOPES, SCOPE])) is True


def test_既有_token_沒有改標題權限回_False():
    assert twitch_tokens.has_stream_info_scope(token(ENABLE_SCOPES)) is False


def test_沒有_token_回_False():
    assert twitch_tokens.has_stream_info_scope(None) is False


def test_缺改標題權限的既有頻道不算_scope_missing():
    old = token(ENABLE_SCOPES)
    assert missing_scopes(old) == []
    assert token_state(old) == "ok"


def test_頻道狀態不因缺改標題權限顯示問題(twitch):
    assert SCOPE not in twitch.scopes
    assert run(health.channel_health(777)) == ChannelHealth("enabled")


def test_有改標題權限的頻道狀態同樣正常(twitch):
    twitch.scopes = [*twitch.scopes, SCOPE]
    assert run(health.channel_health(777)) == ChannelHealth("enabled")
