"""bot 的 token 只有 `moderator:manage:blocked_terms`（沒有 read）時仍能讀清單：Helix 兩者擇一，SDK 4.5.0 硬寫要 read。"""

import asyncio

from twitchAPI.type import AuthScope

from starServer.twitch_bot import state
from tests.dashboard.test_channel_moderation import (
    channel_id,  # noqa: F401 (fixture)
    host,  # noqa: F401 (fixture)
    start_chat,  # noqa: F401 (fixture)
)
from tests.twitch.test_blocked_terms_rpc import call, handlers, helix  # noqa: F401 (fixture)


def test_只有_manage_scope_也能讀清單(helix, channel_id):
    asyncio.run(
        state.twitch.set_user_authentication(
            "test-token", [AuthScope.MODERATOR_MANAGE_BLOCKED_TERMS], "test-refresh", validate=False
        )
    )
    helix.stub.terms["t-1"] = "壞詞"

    result = call(helix, "blocked_terms.list", {"twitch_id": int(channel_id)})

    assert result == {"terms": [{"id": "t-1", "text": "壞詞"}]}


def test_READY_把_Blocked_Terms_RPC_改綁到_Chat_的_loop(monkeypatch):
    import asyncio

    from starlib.messaging import rpc
    from starServer.twitch_bot import blocked_terms

    bound = {}
    monkeypatch.setattr(rpc, "handle", lambda method, _handler, loop: bound.__setitem__(method, loop))

    async def ready():
        await blocked_terms.on_ready(None)
        return asyncio.get_running_loop()

    loop = asyncio.run(ready())
    assert bound == dict.fromkeys(("blocked_terms.list", "blocked_terms.add", "blocked_terms.remove"), loop)
