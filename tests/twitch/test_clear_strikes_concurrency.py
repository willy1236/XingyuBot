import asyncio

from starServer.twitch_bot import state
from tests.dashboard.test_channel_moderation import ALICE, channel_id, configure, host, start_chat  # noqa: F401
from tests.twitch.test_moderation_enforcement_rpc import handlers  # noqa: F401


def test_clear_strikes_waits_for_in_flight_enforcement(configure, start_chat, handlers, channel_id, monkeypatch):
    configure()
    chat = start_chat()
    chat.send()  # 第一次犯規，下一次應 timeout

    async def run():
        entered = asyncio.Event()
        release = asyncio.Event()

        async def ban(*args, **kwargs):
            entered.set()
            await release.wait()
            await chat.ban(*args, **kwargs)

        monkeypatch.setattr(state.twitch, "ban_user", ban)
        async with asyncio.timeout(5), asyncio.TaskGroup() as group:
            group.create_task(chat.send_async())
            await entered.wait()
            clear = group.create_task(
                handlers["moderation.clear_strikes"]({"twitch_id": int(channel_id), "user_id": int(ALICE)})
            )
            await asyncio.sleep(0)
            assert not clear.done()
            release.set()
        await chat.send_async()

    asyncio.run(run())

    assert len(chat.timeouts) == 1
    assert len(chat.deletions) == 2
