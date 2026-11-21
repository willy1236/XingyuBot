"""API 情境：httpx 帶 session cookie 與 Origin，打後台的 HTTP 介面。"""

from __future__ import annotations

from e2e.context import Ctx, Failure
from e2e.fakes import CHANNEL_GENERAL, GUILD_ID, GUILD_NAME, USER
from e2e.scenarios import scenario
from starlib.database import NotifyChannelType
from starServer.dashboard.notify_fields import CHANNEL_SPECS

#: API 情境與 dashboard 情境各用不同的通知種類，免得第二個遇到「已存在」
API_NOTIFY = f"channel:{int(NotifyChannelType.JoinLog)}"


@scenario("api")
def guild_list(ctx: Ctx) -> None:
    ctx.step("取得伺服器清單")
    body = ctx.api("GET", "/dashboard/guilds")
    ctx.expect([g["name"] for g in body["guilds"]], [GUILD_NAME], "伺服器清單")


@scenario("api")
def notify_save(ctx: Ctx) -> None:
    if not any(s.key == API_NOTIFY for s in CHANNEL_SPECS):
        raise Failure(f"CHANNEL_SPECS 沒有 {API_NOTIFY}，情境用的通知種類已不存在")
    url = f"/dashboard/guilds/{GUILD_ID}"
    ctx.step("儲存新增加入紀錄頻道")
    saved = ctx.api(
        "PUT", f"{url}/channel-notifies/{API_NOTIFY}", json={"values": {"channel_id": str(CHANNEL_GENERAL)}}
    )
    ctx.expect(saved["values"]["channel_id"], str(CHANNEL_GENERAL), "儲存後回傳的頻道")
    ctx.step("重新讀取通知清單")
    items = ctx.api("GET", f"{url}/notifies")["channel_notifies"]
    item = next((i for i in items if i["key"] == API_NOTIFY), None)
    if item is None:
        raise Failure("通知清單裡找不到剛儲存的通知")
    ctx.expect(item["channel"]["name"], "一般", "通知清單的頻道名稱")


@scenario("api")
def poll_create(ctx: Ctx) -> None:
    url = f"/dashboard/guilds/{GUILD_ID}/polls"
    ctx.step("讀取發起表單的頻道選項")
    options = ctx.api("GET", f"{url}/options")
    ctx.expect(str(CHANNEL_GENERAL) in [c["id"] for c in options["channels"]], True, "選項含一般頻道")
    ctx.step("建立投票")
    created = ctx.api(
        "POST", url, json={"channel_id": str(CHANNEL_GENERAL), "title": "API 午餐", "options": ["拉麵", "咖哩"]}
    )
    ctx.step("投票出現在列表")
    polls = ctx.api("GET", url)
    ctx.expect(created["poll_id"] in [p["id"] for p in polls["polls"]], True, "投票列表含剛建立的投票")


@scenario("api")
def personal_voice(ctx: Ctx) -> None:
    ctx.step("讀取個人區語音時數")
    items = ctx.api("GET", f"/dashboard/personal/records/voice?discord_id={USER}")["items"]
    ctx.expect(len(items), 1, "有紀錄的伺服器數")
    item = items[0]
    ctx.expect((item["minutes"], item["rank"], item["ranked"]), (125, 2, 3), "語音分鐘、名次與排行人數")
