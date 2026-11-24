"""聊天室共用管理權限的回覆行為。"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from starServer.twitch_bot import commands


def test_觀眾無權管理且要求回覆時收到帶操作名稱的權限提示():
    cmd = SimpleNamespace(
        room=SimpleNamespace(room_id="1"),
        user=SimpleNamespace(id="2", mod=False),
        reply=AsyncMock(),
    )

    assert asyncio.run(commands.may_manage(cmd, "管理常客", reply_viewer=True)) is False
    cmd.reply.assert_awaited_once_with("權限不足：只有實況主或 mod 能管理常客")
