import asyncio
from types import SimpleNamespace

from starlib.twitch_audit import AuditActor
from starServer.dashboard import channel_settings
from starServer.twitch_bot import state
from tests.dashboard.test_channel_moderation import channel_id, configure, enforcement, host, start_chat  # noqa: F401


def test_in_flight_moderation_cannot_write_deleted_channel_data(configure, start_chat, repo, channel_id, monkeypatch):
    configure()
    chat = start_chat()
    monkeypatch.setattr(state, "join_channels", {int(channel_id): SimpleNamespace(state="enabled")})

    async def run():
        entered = asyncio.Event()
        resume = asyncio.Event()

        async def delete_message(*args):
            entered.set()
            await resume.wait()
            await chat.delete(*args)

        monkeypatch.setattr(state.twitch, "delete_chat_message", delete_message)
        async with asyncio.timeout(5), asyncio.TaskGroup() as group:
            group.create_task(chat.send_async())
            await entered.wait()
            await asyncio.to_thread(
                channel_settings._delete_data, int(channel_id), AuditActor("twitch", channel_id, "Host")
            )
            # Bot 仍看得到舊的 enabled cache，驗證 DB 端也會拒絕寫回。
            assert state.join_channels[int(channel_id)].state == "enabled"
            resume.set()

    asyncio.run(run())

    assert len(chat.deletions) == 1
    assert chat.notices == []
    assert enforcement(repo, channel_id) == []
