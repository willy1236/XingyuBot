"""dashboard 情境：Playwright 操作 domalyze_frontend，先在瀏覽器設好 session cookie，用畫面上的文字與 role 定位元素。"""

from __future__ import annotations

from playwright.sync_api import expect

from e2e.context import Ctx
from e2e.fakes import GUILD_ID, GUILD_NAME
from e2e.scenarios import scenario

#: 情境會走到的路由，啟動後先請求一次讓 next dev 編譯
PREWARM = [
    "/dashboard",
    "/dashboard/guilds",
    f"/dashboard/guilds/{GUILD_ID}",
    f"/dashboard/guilds/{GUILD_ID}/polls/new",
    f"/dashboard/guilds/{GUILD_ID}/polls/1",
]


@scenario("dashboard")
def guild_list(ctx: Ctx) -> None:
    ctx.step("開啟伺服器清單")
    ctx.goto("/dashboard/guilds")
    ctx.step("清單顯示伺服器名稱")
    expect(ctx.page.get_by_role("link", name=GUILD_NAME)).to_be_visible()


@scenario("dashboard")
def notify_save(ctx: Ctx) -> None:
    ctx.step("進入伺服器的通知頁")
    ctx.goto("/dashboard/guilds")
    ctx.page.get_by_role("link", name=GUILD_NAME).click()
    ctx.step("新增成員離開日誌通知")
    ctx.page.get_by_label("新增頻道通知").select_option(label="成員離開日誌")
    ctx.page.get_by_label("頻道（必填）").select_option(label="# 一般")
    ctx.step("儲存通知設定")
    ctx.page.get_by_role("button", name="儲存", exact=True).click()
    ctx.step("清單顯示剛儲存的通知")
    expect(ctx.page.get_by_role("heading", name="頻道通知")).to_be_visible()
    expect(ctx.page.get_by_role("heading", name="成員離開日誌", level=3)).to_be_visible()
    expect(ctx.page.get_by_text("編輯：成員離開日誌")).to_be_hidden()


@scenario("dashboard")
def poll_create(ctx: Ctx) -> None:
    ctx.step("開啟發起投票表單")
    ctx.goto(f"/dashboard/guilds/{GUILD_ID}/polls/new")
    ctx.step("填寫頻道、標題與選項")
    ctx.page.get_by_label("頻道", exact=True).select_option(label="# 一般")
    ctx.page.get_by_label("標題").fill("畫面午餐")
    ctx.page.get_by_label("選項 1", exact=True).fill("拉麵")
    ctx.page.get_by_label("選項 2", exact=True).fill("咖哩")
    ctx.step("送出投票")
    ctx.page.get_by_role("button", name="發起", exact=True).click()
    ctx.step("導向投票詳細頁並顯示標題")
    ctx.page.wait_for_url(f"**/dashboard/guilds/{GUILD_ID}/polls/*")
    expect(ctx.page.get_by_text("畫面午餐").first).to_be_visible()


@scenario("dashboard")
def personal_voice(ctx: Ctx) -> None:
    ctx.step("開啟個人區")
    ctx.goto("/dashboard")
    ctx.step("顯示語音時數與名次")
    expect(ctx.page.get_by_text("2 小時 5 分・第 2／3 名")).to_be_visible()
