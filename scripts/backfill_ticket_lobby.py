"""
一次性回填：把測試版建立的私人頻道歸屬到大廳（任務卡 P-01）。

用法（先對資料庫執行任務卡 P-01 的 ALTER，再手動跑一次，不在每次啟動跑）：
    python scripts/backfill_ticket_lobby.py --dry-run
    python scripts/backfill_ticket_lobby.py

- 只處理 `ticket_channel.lobby_channel_id` 為空的列；已歸屬的不動，重跑是安全的。
- 依 Discord 現況的頻道所在分類，對應到同一伺服器、`ticket_category_id` 相同、尚未移除、且唯一的大廳；
  對不到或對到多個的維持空（後台會列在「未歸屬的私人頻道」）。
- 用 bot token 走 HTTP 讀頻道（不連 gateway，不影響正在執行的 bot）；token 從資料庫的 access_token 取，
  `--bot-code` 預設為 BOT_CODE 設定。已在 Discord 被刪除的頻道略過，不改紀錄。
- `--dry-run` 只列出會寫入的內容，不寫入。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import defaultdict
from collections.abc import Iterable, Mapping
from pathlib import Path

import discord

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from starlib.database import APIType, TicketChannel, TicketChannelLobby, sqldb
from starlib.settings import get_settings


def plan_backfill(
    lobbies: Iterable[TicketChannelLobby],
    tickets: Iterable[TicketChannel],
    category_of: Mapping[int, int | None],
) -> dict[int, int]:
    """私人頻道 ID -> 應歸屬的大廳頻道 ID。

    category_of 是各私人頻道在 Discord 現況的分類 ID（頻道已刪或無分類為 None 或不在其中）；
    同一伺服器內 `ticket_category_id` 相同的大廳恰好一個才歸屬。
    """
    by_category: dict[tuple[int, int], list[int]] = defaultdict(list)
    for lobby in lobbies:
        if lobby.removed_at is None and lobby.ticket_category_id is not None:
            by_category[(lobby.guild_id, lobby.ticket_category_id)].append(lobby.channel_id)

    plan: dict[int, int] = {}
    for ticket in tickets:
        if ticket.lobby_channel_id is not None:
            continue
        category_id = category_of.get(ticket.channel_id)
        if category_id is None:
            continue
        candidates = by_category.get((ticket.guild_id, category_id), [])
        if len(candidates) == 1:
            plan[ticket.channel_id] = candidates[0]
    return plan


async def fetch_categories(token: str, channel_ids: list[int]) -> dict[int, int | None]:
    """用 HTTP 讀頻道所在的分類 ID；頻道不存在或讀不到的不放進結果。"""
    client = discord.Client(intents=discord.Intents.none())
    await client.login(token)
    result: dict[int, int | None] = {}
    try:
        for channel_id in channel_ids:
            try:
                channel = await client.fetch_channel(channel_id)
            except discord.NotFound:
                print(f"略過 {channel_id}：頻道已不存在")
            except (discord.Forbidden, discord.HTTPException) as e:
                print(f"略過 {channel_id}：讀不到頻道（{e}）")
            else:
                result[channel_id] = getattr(channel, "category_id", None)
    finally:
        await client.close()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="只列出會寫入的內容，不寫入")
    parser.add_argument("--bot-code", default=None, help="用哪個 bot 的 token，預設為 BOT_CODE 設定")
    args = parser.parse_args()

    bot_code = int(args.bot_code or get_settings().BOT_CODE)
    tickets = sqldb.list_unassigned_ticket_channels()
    lobbies = sqldb.list_all_active_ticket_lobbies()
    print(f"待回填的私人頻道 {len(tickets)} 個，大廳 {len(lobbies)} 個")
    if not tickets:
        return 0

    token = sqldb.get_access_token(APIType.Discord, bot_code).access_token
    categories = asyncio.run(fetch_categories(token, [t.channel_id for t in tickets]))
    plan = plan_backfill(lobbies, tickets, categories)

    for ticket in tickets:
        target = plan.get(ticket.channel_id)
        print(f"{ticket.channel_id} -> {target if target is not None else '未歸屬'}")
    if args.dry_run:
        print(f"dry-run：會歸屬 {len(plan)} 個，不寫入")
        return 0
    for channel_id, lobby_channel_id in plan.items():
        sqldb.set_ticket_channel_lobby(channel_id, lobby_channel_id)
    print(f"已歸屬 {len(plan)} 個，{len(tickets) - len(plan)} 個維持未歸屬")
    return 0


if __name__ == "__main__":
    sys.exit(main())
