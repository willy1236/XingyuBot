"""channel_mods（M-01）：候選頻道、60 秒快取、無法確認與暫時無法回應、排除 bot 與實況主、Helix 回應的分類（真實 PostgreSQL，假 Helix）。"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import httpx
import pytest

from starlib.database import TwitchBotJoinChannel
from starlib.twitch_tokens import TokenInvalid
from starServer.dashboard import channel_mods
from starServer.dashboard.channel_mods import ModChannel, Moderator
from starServer.dashboard.session import TwitchIdentity
from tests.helpers.dashboard_auth import BOT_TWITCH_ID

pytestmark = pytest.mark.usefixtures("dashboard_env")

#: dashboard_env 換掉 _fetch 之前的真實版本，給 Helix 回應分類的測試用
REAL_FETCH = channel_mods._fetch

A = "5001"  # 登入者
B, C, D = 6001, 6002, 6003  # 頻道


@pytest.fixture(autouse=True)
def _clean(repo):
    repo.session.query(TwitchBotJoinChannel).filter(
        TwitchBotJoinChannel.twitch_id.in_([B, C, D, int(A)])  # pyright: ignore[reportAttributeAccessIssue]
    ).delete()
    repo.session.flush()


def channel(repo, twitch_id: int, name: str, state="enabled", **kw) -> None:
    repo.add(TwitchBotJoinChannel(twitch_id=twitch_id, state=state, login=name.lower(), display_name=name, **kw))


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def clock(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(channel_mods, "monotonic", lambda: now[0])
    return now


class TestCandidates:
    def test_lists_mod_channels_sorted_by_name(self, repo, twitch_mods):
        channel(repo, B, "bravo")
        channel(repo, C, "Alpha", state="disabled")
        twitch_mods.set(B, (A, "Ann"))
        twitch_mods.set(C, (A, "Ann"))

        found = run(channel_mods.mod_channels([A]))

        assert found == [
            ModChannel(TwitchIdentity(str(C), "alpha", "Alpha", None), Moderator(A, "Ann")),
            ModChannel(TwitchIdentity(str(B), "bravo", "bravo", None), Moderator(A, "Ann")),
        ]

    def test_inactive_channel_is_not_listed_nor_queried(self, repo, twitch_mods):
        channel(repo, B, "bravo", state="inactive")
        twitch_mods.set(B, (A, "Ann"))

        assert run(channel_mods.mod_channels([A])) == []
        assert run(channel_mods.mod_channel(B, [A])) is None
        assert B not in twitch_mods.calls

    def test_banned_channel_is_listed_even_after_data_deleted(self, repo, twitch_mods):
        channel(repo, B, "bravo", state="inactive", banned_at=datetime(2026, 1, 1, tzinfo=UTC))
        twitch_mods.set(B, (A, "Ann"))

        assert [m.channel.id for m in run(channel_mods.mod_channels([A]))] == [str(B)]

    def test_collab_disabled_channel_is_not_listed(self, repo, twitch_mods):
        channel(repo, B, "bravo", mod_collab_enabled=False)
        twitch_mods.set(B, (A, "Ann"))

        assert run(channel_mods.mod_channels([A])) == []
        assert run(channel_mods.mod_channel(B, [A])) is None

    def test_own_channel_is_never_a_mod_channel(self, repo, twitch_mods):
        channel(repo, int(A), "self")
        twitch_mods.set(int(A), (A, "Ann"))

        assert run(channel_mods.mod_channels([A])) == []
        assert run(channel_mods.mod_channel(int(A), [A])) is None

    def test_no_ids_means_no_query(self, repo, twitch_mods):
        channel(repo, B, "bravo")

        assert run(channel_mods.mod_channels([])) == []
        assert twitch_mods.calls == []


class TestModerator:
    def test_bot_account_is_never_a_moderator(self, repo, twitch_mods):
        channel(repo, B, "bravo")
        twitch_mods.set(B, (BOT_TWITCH_ID, "xingyu"))

        assert run(channel_mods.mod_channels([BOT_TWITCH_ID])) == []

    def test_picks_smallest_linked_id(self, repo, twitch_mods):
        channel(repo, B, "bravo")
        twitch_mods.set(B, ("900", "Late"), ("80", "Early"))

        found = run(channel_mods.mod_channel(B, ["900", "80"]))

        assert found is not None and found.moderator == Moderator("80", "Early")


class TestCache:
    def test_cached_for_60_seconds_and_shared(self, repo, twitch_mods, clock):
        channel(repo, B, "bravo")
        twitch_mods.set(B, (A, "Ann"))
        run(channel_mods.mod_channels([A]))

        twitch_mods.set(B)  # 被拿掉 mod
        clock[0] += 59
        assert run(channel_mods.mod_channel(B, [A])) is not None
        assert twitch_mods.calls == [B]

        clock[0] += 2
        assert run(channel_mods.mod_channel(B, [A])) is None
        assert twitch_mods.calls == [B, B]

    def test_new_mod_appears_after_expiry(self, repo, twitch_mods, clock):
        channel(repo, B, "bravo")
        assert run(channel_mods.mod_channels([A])) == []

        twitch_mods.set(B, (A, "Ann"))
        clock[0] += 61

        assert len(run(channel_mods.mod_channels([A]))) == 1

    def test_concurrent_queries_share_one_fetch(self, repo, twitch_mods):
        channel(repo, B, "bravo")
        twitch_mods.set(B, (A, "Ann"))
        original = twitch_mods.fetch

        async def slow(twitch_id):
            await asyncio.sleep(0.05)
            return await original(twitch_id)

        channel_mods._fetch = slow  # dashboard_env 已用 monkeypatch 換過，測完會還原

        # 測試的 DB session 不能跨 thread 並行，只並行到名單查詢這一層
        async def both():
            return await asyncio.gather(channel_mods._mod_lists([B]), channel_mods._mod_lists([B]))

        first, second = run(both())
        assert first == second == {B: {A: "Ann"}}
        assert twitch_mods.calls == [B]


class TestTwitchFailures:
    def test_unconfirmable_blocks_everyone(self, repo, twitch_mods, clock):
        channel(repo, B, "bravo")
        twitch_mods.set(B, (A, "Ann"))
        run(channel_mods.mod_channels([A]))

        twitch_mods.lists[B] = channel_mods._Unconfirmable()
        clock[0] += 61
        assert run(channel_mods.mod_channel(B, [A])) is None

        # 實況主修復授權後，下一次過期重查就恢復
        twitch_mods.set(B, (A, "Ann"))
        clock[0] += 61
        assert run(channel_mods.mod_channel(B, [A])) is not None

    def test_unavailable_keeps_last_result(self, repo, twitch_mods, clock):
        channel(repo, B, "bravo")
        twitch_mods.set(B, (A, "Ann"))
        run(channel_mods.mod_channels([A]))

        twitch_mods.lists[B] = channel_mods._Unavailable()
        clock[0] += 61
        assert run(channel_mods.mod_channel(B, [A])) is not None
        assert run(channel_mods.mod_channel(B, ["123"])) is None

    def test_unavailable_without_history_blocks(self, repo, twitch_mods):
        channel(repo, B, "bravo")
        twitch_mods.lists[B] = channel_mods._Unavailable()

        assert run(channel_mods.mod_channel(B, [A])) is None

    def test_exception_counts_as_unavailable(self, repo, twitch_mods, clock):
        channel(repo, B, "bravo")
        twitch_mods.set(B, (A, "Ann"))
        run(channel_mods.mod_channels([A]))

        async def boom(twitch_id):
            raise RuntimeError("boom")

        channel_mods._fetch = boom
        clock[0] += 61
        assert run(channel_mods.mod_channel(B, [A])) is not None

    def test_timeout_uses_last_result_and_late_answer_fills_cache(self, repo, twitch_mods, monkeypatch, clock):
        channel(repo, B, "bravo")
        channel(repo, C, "charlie")
        twitch_mods.set(B, (A, "Ann"))
        twitch_mods.set(C, (A, "Ann"))
        run(channel_mods.mod_channels([A]))
        monkeypatch.setattr(channel_mods, "QUERY_TIMEOUT", 0.05)
        original = twitch_mods.fetch

        async def slow_for_c(twitch_id):
            if twitch_id == C:
                await asyncio.sleep(0.2)
            return await original(twitch_id)

        channel_mods._fetch = slow_for_c
        twitch_mods.set(B)
        twitch_mods.set(C)
        clock[0] += 61

        async def scenario():
            # B 準時回來（已不是 mod），C 逾時沿用上次（仍是 mod）
            found = await channel_mods.mod_channels([A])
            await asyncio.sleep(0.3)
            return found

        assert [m.channel.id for m in run(scenario())] == [str(C)]
        assert channel_mods._cache[C].mods == {}


class TestFetch:
    """真實的 _fetch：token 狀態與 Helix 回應的分類、翻頁。"""

    @pytest.fixture
    def helix(self, monkeypatch):
        responses: list[httpx.Response] = []
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return responses.pop(0)

        real_client = httpx.AsyncClient
        monkeypatch.setattr(
            channel_mods.httpx,
            "AsyncClient",
            lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw),
        )
        monkeypatch.setattr(channel_mods.twitch_tokens, "broadcaster_token_blocking", lambda twitch_id: "tok")
        monkeypatch.setattr(channel_mods.twitch_speech_check, "broadcaster_client_id_blocking", lambda: "cid")
        return responses, requests

    def test_pages_through_moderators(self, helix):
        responses, requests = helix
        responses += [
            httpx.Response(200, json={"data": [{"user_id": "1", "user_name": "One"}], "pagination": {"cursor": "x"}}),
            httpx.Response(200, json={"data": [{"user_id": "2", "user_name": "Two"}], "pagination": {}}),
        ]

        assert run(REAL_FETCH(B)) == {"1": "One", "2": "Two"}
        assert requests[0].url.params["broadcaster_id"] == str(B)
        assert "user_id" not in requests[0].url.params
        assert requests[1].url.params["after"] == "x"
        assert requests[0].headers["Authorization"] == "Bearer tok"

    @pytest.mark.parametrize("status", [401, 403])
    def test_auth_rejection_is_unconfirmable(self, helix, status):
        helix[0].append(httpx.Response(status))
        assert isinstance(run(REAL_FETCH(B)), channel_mods._Unconfirmable)

    @pytest.mark.parametrize("status", [429, 500, 503])
    def test_other_status_is_unavailable(self, helix, status):
        helix[0].append(httpx.Response(status))
        assert isinstance(run(REAL_FETCH(B)), channel_mods._Unavailable)

    def test_malformed_body_is_unavailable(self, helix):
        helix[0].append(httpx.Response(200, json={"nope": []}))
        assert isinstance(run(REAL_FETCH(B)), channel_mods._Unavailable)

    @pytest.mark.parametrize(
        ("reason", "expected"),
        [
            ("missing", channel_mods._Unconfirmable),
            ("revoked", channel_mods._Unconfirmable),
            ("unavailable", channel_mods._Unavailable),
        ],
    )
    def test_invalid_token(self, monkeypatch, reason, expected):
        monkeypatch.setattr(
            channel_mods.twitch_tokens, "broadcaster_token_blocking", lambda twitch_id: TokenInvalid(reason)
        )
        assert isinstance(run(REAL_FETCH(B)), expected)

    def test_network_error_is_unavailable(self, monkeypatch):
        def handler(request):
            raise httpx.ConnectError("down")

        real_client = httpx.AsyncClient
        monkeypatch.setattr(
            channel_mods.httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw)
        )
        monkeypatch.setattr(channel_mods.twitch_tokens, "broadcaster_token_blocking", lambda twitch_id: "tok")
        monkeypatch.setattr(channel_mods.twitch_speech_check, "broadcaster_client_id_blocking", lambda: "cid")
        assert isinstance(run(REAL_FETCH(B)), channel_mods._Unavailable)
