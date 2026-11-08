# 伺服器管理後台（自動通知）任務拆解

規格書：[docs/spec/server-dashboard-spec.md](../spec/server-dashboard-spec.md)

## 現況與前提

- 技術棧：
  - 後端是 XingyuBot 的 FastAPI（`starServer/bot_website.py`）。它在 Discord bot 同一個 process 的背景 thread 執行（`main.py` 的 `run_website`），可以透過 `sclient.bot.submit(coro)`（`starDiscord/bot.py:80`）把 coroutine 丟給 bot 的事件迴圈。
  - 資料庫是 PostgreSQL，透過 SQLModel 存取（`starlib/database/postgresql/`）。沒有 migration 工具，新資料表由啟動時的 `SQLModel.metadata.create_all` 建立（`client.py:1925`），改既有表要手動 ALTER。
  - 前端是 domalyze_frontend 的 `main` 分支：Next.js 16、Tailwind 4。目前只有 `/`、`/features` 兩頁，元件在 `components/`，API 網址的環境變數是 `NEXT_PUBLIC_BASE_API_URL`。
- 既有相關機制：
  - Discord OAuth：
    - `starlib/oauth/discord_oauth.py` 的 `DiscordOAuth`（繼承 `oauth_lib.OAuth2Base`），用 `sqldb.get_oauth_client(APIType.Discord, 4)` 的 client。
    - callback 是 `/oauth/discord`（`bot_website.py:179`）。缺 `code` 就先回 400；帶 `guild_id` 時走 bot 授權並把 token 存進 `OAuthToken`，不驗 state；不帶時回 503「網站登入暫停」。
  - token 存在 `OAuthToken`，主鍵是 `user_id` 加 `client_credential_id`。bot 授權流程存下的 token 目前沒有任何地方讀取。
  - 授權入口：
    - `/to/discordbot`（`permissions=8`，scope 是 `identify`、`applications.commands.permissions.update`、`bot`）用來邀請 bot。
    - `/to/discordauth` 是舊網站登入的入口，網站登入已停用。
  - 通知資料：
    - 頻道通知 `NotifyChannel`，主鍵是 guild × 種類，欄位有 channel_id、role_id、message。
    - 社群推播 `NotifyCommunity`，主鍵是種類 × 帳號 × guild。
    - 帳號名稱 `Community`，其中 `username` 不可為 null。
    - 輪詢紀錄 `CommunityCache`，YouTube 推播紀錄 `PushRecord`。
  - 寫入方法在 `client.py`：`add_notify_channel`、`remove_notify_channel`、`get_notify_channel_all`、`add_notify_community`、`remove_notify_community`、`get_notify_community_list`。新增和修改都用 `session.merge`，同一個主鍵後寫的會直接覆蓋。`remove_notify_community` 已經包含後續清理。
  - 現有指令的設定邏輯寫在 cog 裡：頻道通知在 `starDiscord/cmds/moderation.py` 的 `/channel set`；社群推播在 `starDiscord/cmds/system_community.py` 的 Twitch、YouTube、Twitter set／remove。YouTube 的推播訂閱也在 cog 裡（`yt_push.add_push`）。
  - 平台查詢（`starlib/providers/social/platforms.py`）：`tw_api.get_user`、`google_api.get_channel(channel_id=None, handle=None)`、`cli_api.get_user_details`。
    - Twitch：`APICaller` 遇到非 2xx 或網路錯誤會拋 `APINetworkError`（`starlib/providers/base.py:73-89`）。但 404 時 `self.get` 回 None，接著 `.json()` 會丟 AttributeError；login 格式不合法時 Twitch 回 400。
    - Twitter：subprocess 失敗會拋 `CalledProcessError`／`TimeoutExpired`；格式不合法與 JSON 解析失敗都回 None，跟「不存在」混在一起。
  - 通知怎麼發送：`starDiscord/bot.py` 的 `send_notify_channel`、`edit_notify_channel`、`send_notify_communities`，以及 `starDiscord/cmds/bot_event.py` 的成員加入、離開。
  - 路由：shark-ansible 的 `roles/shark_home/files/dynamic/routes.yml` 只把 `api.domalyze.net` 的 `/keep_alive`、`/youtube_push`、`/oauth/`、`/callback/`、`/to/` 轉給 XingyuBot，其餘轉給 domalyze-api。官網在 `domalyze.net`。
- 這次會動到的既有部位：
  - XingyuBot：`.env.example`、`starServer/bot_website.py`、`starlib/oauth/`、`starlib/settings.py`、`starlib/database/postgresql/models.py` 與 `client.py`、`starlib/providers/social/platforms.py`、`starDiscord/cmds/system_community.py`，另新增 `starServer/dashboard/`。T-05 只讀取預設文字的現有寫法，不改 `starDiscord/bot.py`、`starDiscord/cmds/task.py`、`owner.py`、`bot_event.py`。
  - domalyze_frontend：`components/header.tsx`、`lib/auth.ts`、`package.json`、`.env.example`，另新增 `app/dashboard/` 與 `components/dashboard/`。
  - shark-ansible：`routes.yml`、正式環境 domalyze-frontend 的 env（`NEXT_PUBLIC_BASE_API_URL`）、xingyubot 的 env（新增的 `DASHBOARD_*` 設定）。
- 已定案的技術前提：
  - 後台 API 放在 XingyuBot 自己的 web 服務。
  - 用 Discord 授權登入，不要求析域帳號。
  - 前端做在 domalyze_frontend 的 `main` 分支，沿用現有元件與樣式，不用 `feat/seiu-component-library`。注意：本機 domalyze_frontend 目前停在 `feat/seiu-component-library`，開工前要切回 `main`。
  - 析域登入帶入身分要等網站有析域登入才生效，不在這次的卡片內。
- 全部卡片共通的規則：
  - **跨 thread**：web thread 讀寫任何 Discord 物件，包括 `get_guild` 這類只讀快取的呼叫，一律包成 coroutine 經 `sclient.bot.submit(...)` 取結果。`submit` 回傳的是 `concurrent.futures.Future`，在 async 端點裡要寫成 `await asyncio.wrap_future(sclient.bot.submit(...))`，不可以直接 `.result()`，否則會卡住 uvicorn 的事件迴圈。
  - **bot 尚未 ready**：`main.py` 先啟動 website 再啟動 bot，剛啟動時 `sclient.bot` 可能是 None 或還沒 ready，`get_guild` 會回 None。所有需要 bot 的判斷先檢查 `sclient.bot is not None and bot.is_ready()`，不成立就回 503 `bot_unavailable`，前端顯示稍後再試、不導向，避免把所有伺服器誤判成 bot 不在。
  - **同步 I/O**：sqldb、平台查詢（rettiwt 是 subprocess，timeout 30 秒）都是同步呼叫，不能直接在 async 端點裡跑。
    - **DB**：一律走 T-01 提供的 `run_db(fn)`。它用一個專屬的小 executor（2～4 條 thread），每次執行完在 `finally` 呼叫 `sqldb.session.remove()`。原因：`sqldb` 是 thread-local 的 `scoped_session`，讀完不 commit 會一直佔住連線；engine 用預設連線池（5＋10，`client.py:1917`）且跟 bot 共用，交給 anyio 或 asyncio 預設 executor 的幾十條 thread 會把連線池吃光，bot 的 DB 呼叫會卡住。不寫 `def` 端點，也不用預設 executor 跑 DB。
    - **平台查詢**：用 `run_in_executor` 包起來，不碰 DB 的部分可以用預設 executor。
  - **種類鍵**：`NotifyChannelType`（1～13）和 `NotifyCommunityType`（1～5）的整數值會重疊，所以所有 API 與共用函式一律用 T-03 定義的字串種類鍵，例如 `channel:4`、`community:1`，不直接傳整數。有效的種類只有欄位對照表列出的那些：`NotifyChannelType` 的 9（DynamicVoice）已廢棄（`enums.py:21`），實際是 12 種；資料庫裡不在對照表的種類一律略過。
  - **router 檔**：每張卡的端點放在各自的模組，例如 `dashboard/auth.py`（T-01）、`guilds.py`（T-02）、`notifies.py`（T-03）、`options.py`（T-04）、`preview.py`（T-05）、`channel_notifies.py`（T-06）、`community_notifies.py`（T-07）、`test_notify.py`（T-08）、`invite.py`（T-09），避免並行時改到同一個檔案。T-01 建立 `starServer/dashboard/__init__.py`，自動掃描同一個 package 底下的模組，掛上各自的 `router`，各卡新增模組時不必改 `__init__.py` 或 `bot_website.py`。模組用固定名稱暴露 router：`router` 帶 `/dashboard` 前綴，`to_router` 不帶前綴、放 `/to/*`；兩個都可有可無，掃描器有就掛上。`client.py` 各卡只新增自己的方法，不改彼此的方法。
  - **錯誤格式**：由 T-01 定義，所有卡共用，見 T-01〈錯誤格式與 fetch wrapper〉。
  - **Discord ID 一律用字串**：guild、channel、role、user 的 ID 都大於 2^53，JS number 會失去精度。後台 API 的輸入與輸出一律用字串，後端在 pydantic schema 層轉成 int；`check_conflict` 比對前先把兩邊轉成同一種型別。
  - **讀到最新的資料**：`run_db` 每次結束都 `remove()` session，下一次就是新的 session，讀得到指令在 bot thread 寫入的值，也讀得到別的請求剛 refresh 的 token 與 session。一覽與衝突比對的讀取另外加 `.execution_options(populate_existing=True)`（做法同 `client.py:1095`）當補強。
  - **規格外的變更**：T-01 移除舊網站登入的殘留、T-07 修正 `remove_notify_community` 的清理範圍，這兩項規格沒有要求，是拆卡時順手納入的清理與修正，在卡片上另外標示。
  - **手機**：每張有畫面的卡，畫面都要在 360px 寬時能完成操作，不需要橫向捲動。

## 實作順序總覽

| # | 卡號 | 進度 | 標題 | 依賴 | 並行組 | 備註 |
|---|---|---|---|---|---|---|
| 1 | T-01 | 完成 | 管理員能用 Discord 登入、登出後台 | 無 | — | 骨架切片，含地基：路由、CORS、session、OAuth 分流、錯誤格式與 fetch wrapper |
| 2 | T-02 | 完成 | 管理員能看到可管理的伺服器清單 | T-01 | — | |
| 3 | T-03 | 完成 | 管理員能看到伺服器的通知一覽 | T-02 | — | 含存取檢查與有效性判斷，T-04～T-09 共用 |
| 4 | T-04 | 完成 | [共用] 通知編輯：選項、衝突比對、表單暫存 | T-03 | A | T-06、T-07 依賴 |
| 5 | T-05 | 完成 | [共用] 通知範例內容：預覽與測試共用 | T-03 | A | T-06、T-07、T-08 依賴 |
| 6 | T-09 | 完成 | 管理員能從清單邀請 bot 並回到後台 | T-02 | A | 依賴只到 T-02，可以提早與 T-03 並行 |
| 7 | T-06 | 未完成 | 管理員能新增、修改、刪除頻道通知 | T-04、T-05 | B | |
| 8 | T-07 | 未完成 | 管理員能新增、修改、刪除社群推播 | T-04、T-05 | B | |
| 9 | T-08 | 未完成 | 管理員能發送測試通知 | T-06、T-07 | — | |

並行組的部位切分：

- **A**：T-04 是 `options.py`、衝突比對、表單暫存介面；T-05 是 `preview.py`、範例產生器與預覽元件；T-09 是 `invite.py`、`/oauth/discord` 的 `purpose=invite` 分支，以及清單頁的提示。三者各自擁有自己的檔案。
- **B**：T-03 把通知頁切成兩個區塊元件。T-06 只改頻道通知區塊與 `channel_notifies.py`，T-07 只改社群推播區塊與 `community_notifies.py`；兩張卡在 `client.py` 各自新增不同的方法。
- **T-08** 要在兩個區塊與一覽 API 加東西，所以排在 T-06、T-07 之後。

## 任務卡

### T-01 管理員能用 Discord 登入、登出後台

**使用者價值**：管理員第一次能登入星羽的網站後台，後面每一張卡都建立在這個登入之上。這張卡同時打通官網 → `api.domalyze.net` → bot 的整條路，路由、CORS、cookie 有問題會在這裡就發現。

**範圍**
- 包含：
  - 官網 header 的「管理後台」入口，手機上也顯示。
  - Discord 授權登入與 30 天滑動 session。
  - 登出時撤銷授權並讓所有裝置失效。
  - 未登入打開後台頁先導向登入，完成後回到原頁；取消授權回首頁。
  - 後台頁的 header 顯示 Discord 頭像、名稱與登出按鈕。
  - 重新登入時換成另一個 Discord 帳號就以新帳號為準。
  - 伺服器清單頁與伺服器頁先做成佔位頁。
  - 規格外的清理：移除舊網站登入的殘留，包括 `/to/discordauth`，以及前端的 `lib/auth.ts`、`jose`、`JWT_SECRET`。
- 不包含：
  - 伺服器清單內容，留到 T-02。
  - 表單內容的暫存與還原，留到 T-04。
  - 析域登入帶入身分。

**驗收條件**
- [x] 官網 header 有「管理後台」入口，360px 寬也看得到。未登入點下去導向 Discord 授權，完成後進入後台，看到自己的 Discord 頭像與名稱。
- [x] 未登入時直接打開 `/dashboard/guilds/<任意 id>`，完成 Discord 授權後回到該網址的佔位頁。
- [x] 在 Discord 授權頁按取消，回到官網首頁。
- [x] 登出後回到網站需要重新登入，保存的 Discord 授權已向 Discord 撤銷。
- [x] 在兩台裝置登入，於其中一台登出後，另一台也需要重新登入。
- [x] 登入超過 30 天、但中間持續有使用，不需要重新登入；最後一次使用超過 30 天後需要重新登入。
- [x] 登出後改用另一個 Discord 帳號登入，後台顯示的是新帳號。
- [x] 沒設自訂頭像、也沒設顯示名稱的 Discord 帳號能登入，header 顯示 Discord 預設頭像與 username。
- [x] `/to/discordauth` 已不存在。
- [ ] 在 `www.domalyze.net` 與 `domalyze.net` 都能登入並使用後台。
- [x] 用官網首頁的邀請按鈕邀請 bot 之後，後台仍維持登入，`OAuthToken` 裡後台的 token 沒有被覆寫。

**實作設計**
- 資料：
  - 新增 `DashboardSession` 資料表，放在 `models.py`，繼承 `TokensSchema`，由 `create_all` 建立。
  - 欄位：session ID（隨機不可猜，主鍵）、discord_user_id、Discord 名稱、頭像 hash、建立時間、最後使用時間。名稱與頭像在登入時用 `get_me()` 取得後存下來，之後不再用使用者的授權去查。
  - 登出時刪掉該 discord_user_id 的所有列。
  - Discord token 沿用 `OAuthToken`，`user_id` 是 Discord user ID，credential 用 `get_oauth_client(APIType.Discord, 4)`。
- 後端：
  - `starlib/settings.py` 新增兩個設定：
    - 前端網址 `DASHBOARD_FRONTEND_URL`，正式環境是 `https://domalyze.net`，登入後的導回網址從這裡讀。
    - CORS 允許的 origin 清單 `DASHBOARD_ALLOWED_ORIGINS`，正式環境含 `https://domalyze.net` 與 `https://www.domalyze.net`，因為 routes.yml 把兩者都轉給前端。
    - 本機開發各自另設。
  - 新增 `starServer/dashboard/`，放後台的 router，由 `bot_website.py` 掛上去，路徑前綴 `/dashboard/`。在 FastAPI 加 CORS middleware：
    - `allow_origins=DASHBOARD_ALLOWED_ORIGINS`、`allow_credentials=True`、`allow_methods=["GET","POST","PUT","DELETE"]`、`allow_headers=["Content-Type"]`。Starlette 的預設只允許 GET、不允許任何 header，T-04 之後的 JSON 請求會在 preflight 被擋。
    - 在 `sentry_exception_middleware` 之後才 `add_middleware`，讓 CORS 在最外層，500 回應也帶得到 CORS header（`bot_website.py:48-60`）。
  - **CSRF**：`memory.`、`cup.`、`forgejo.domalyze.net` 等子網域跟後台同 site，SameSite=Lax 擋不住它們發出的請求。`/dashboard/*` 的非 GET 請求一律檢查 `Origin` 在 `DASHBOARD_ALLOWED_ORIGINS` 裡，不在就回 400 `invalid_request`，不用 `no_permission`，以免 wrapper 誤清表單暫存；有 body 的端點要求 `Content-Type: application/json`。
  - **OAuth 分流**：後台用一個獨立的短效 cookie `dashboard_oauth`（HttpOnly、Secure、SameSite=Lax、10 分鐘），存 `{state, purpose, next, origin}`。`purpose` 是 `login` 或 `invite`，`invite` 由 T-09 使用。既有 `/to/*` 的 `oauth_state` cookie 不受影響。
    - cookie 沒有簽章，同 site 的其他子網域可以寫入同名 cookie。所以 callback 讀出後，`next` 與 `origin` 要用跟寫入時相同的規則再驗一次，不合格就換成預設值，避免 open redirect。
  - `GET /to/dashboard-login?next=<path>&origin=<前端 origin>`：產生 state，把 `{state, purpose: login, next, origin}` 寫入 `dashboard_oauth`，導向 Discord 授權，scope 為 `identify guilds`。
    - `next` 只接受 `/dashboard` 開頭的站內相對路徑，其他一律改成 `/dashboard`。
    - `origin` 必須在 `DASHBOARD_ALLOWED_ORIGINS` 裡，不在或沒帶就用 `DASHBOARD_FRONTEND_URL`。登入完成後導回同一個 origin，因為 sessionStorage 以 origin 區分，從 `www.domalyze.net` 發起就要回到 `www.domalyze.net`，換帳號偵測與表單暫存才讀得到。
  - `/oauth/discord` 改寫：
    - **最前面**先處理 `dashboard_oauth`。有這個 cookie 時，回應一律清掉它。接著比對 state：
      - **state 不符**：視為不是後台流程，退回下面「沒有 `dashboard_oauth`」的原本處理。這種情況通常是 10 分鐘內又走了 `/to/discordbot` 或官網首頁的邀請。
      - **state 相符**：依 `purpose` 分流。分流寫在 `dashboard/auth.py` 的 `handle_dashboard_oauth(request) -> Response | None`，`bot_website.py` 的 `/oauth/discord` 先呼叫它，回 None 才走原本的處理。其他 purpose 用 `register_oauth_purpose(purpose, handler)` 註冊，T-09 在 `invite.py` 註冊 `invite`，不改 T-01 的檔案：
        - 帶 `error` 回來（取消）：`login` 導回 `origin` 的首頁；`invite` 由 T-09 處理。
        - 有 code 且 `purpose=login`：換 token、存 `OAuthToken`、建 session，導回 `origin + next`。
    - 沒有 `dashboard_oauth` 時：帶 `guild_id` 走原本的 bot 授權；帶 `error` 導回 `DASHBOARD_FRONTEND_URL` 首頁；其他情況導回 `DASHBOARD_FRONTEND_URL/dashboard`，由後台頁重新走登入。這涵蓋在 Discord 頁停超過 10 分鐘、cookie 已過期的情況，不再回 400 或 503「網站登入暫停」，因為舊網站登入已移除。
    - 帶 `guild_id` 的 bot 授權不再存 token。這個流程存下的 token 目前沒有任何地方讀取（`get_oauth_token` 只被 `oauth_lib` 使用），不存不影響既有功能，也不會蓋掉後台的 token。見〈決策紀錄〉第 3 題。
  - **session cookie**：名稱 `dashboard_session`，設在 `api.domalyze.net`，HttpOnly、Secure、SameSite=Lax，max-age 30 天。
  - 驗證 session 的 dependency：
    - 每次請求都更新資料表的最後使用時間，並重設 cookie 的 max-age，達成滑動 30 天。
    - dependency 只把要續期的 session 記在 `request.state`，由一個 middleware 在回應出去時統一補 `Set-Cookie`。端點拋例外時，exception handler 會產生新的 response，dependency 自己設的 cookie 會遺失，所以不在 dependency 裡設。
    - 最後使用超過 30 天，或查不到 session，回 401，錯誤碼 `session_expired`。
  - 換帳號：建立 session 時，如果 cookie 帶著另一個 Discord 帳號的舊 session，刪掉舊 session。前端從 `/dashboard/me` 得知帳號已經換了。
  - `GET /dashboard/me`：從 session 表回傳 Discord ID、名稱與頭像 URL。只會回 `session_expired`，不會回 `reauth_required`。
  - `POST /dashboard/logout`：向 Discord 的 token revoke 端點撤銷授權，刪除該使用者所有 session 與 `OAuthToken`，清 cookie。
  - `starlib/oauth/models.py:14-29` 的 `DiscordUser` 把 `avatar`、`global_name` 宣告成必填，沒設頭像或顯示名稱的帳號會讓 `get_me()` 驗證失敗、登入 500。改成 `str | None`，其他會是 null 的欄位如 `discriminator`、`flags` 一併檢查。`/dashboard/me` 在頭像為 null 時回傳 Discord 預設頭像的 URL，名稱依 `global_name` → `username` 退回。
  - `DiscordOAuth` 新增撤銷授權的方法。
  - 在 `starServer/dashboard/` 提供共通規則〈同步 I/O〉的 `run_db(fn)`，這張卡的 session 與 token 讀寫都走它。`oauth_lib.OAuth2Base` 目前沒有 revoke。
  - 刪除 `/to/discordauth`。
- 前端：
  - `components/header.tsx` 加「管理後台」入口。現有 nav 是 `hidden md:flex`，這個入口要放在手機也會顯示的位置。
  - 新增 `app/dashboard/layout.tsx`，寫成 client component（`"use client"`），因為 cookie 在 api 網域，Next 的 server 端轉送不了：
    - 載入時呼叫 `/dashboard/me`，收到 `session_expired` 就整頁導向登入。這時還沒有表單內容，所以不必提示。
    - **換帳號偵測**：導向登入前，一律把目前的 Discord user ID 存進 sessionStorage，還不知道時就不存。回來後 `/dashboard/me` 的 ID 跟存的不同，就丟棄所有暫存，導向 `/dashboard`，不回到 `next`。
    - 導向的網址是 `${NEXT_PUBLIC_BASE_API_URL}/to/dashboard-login?next=<目前路徑>&origin=<window.location.origin>`，一定用絕對 API 網址，因為 `domalyze.net/to/...` 不會轉給 XingyuBot。後面各卡導向登入時都用同一個寫法。
    - 後台另做一個 header 元件 `components/dashboard/dashboard-header.tsx`，顯示頭像、名稱與登出按鈕；官網的 `components/header.tsx` 只加入口，不放進後台。
  - 新增 `app/dashboard/page.tsx` 與 `app/dashboard/guilds/[id]/page.tsx` 兩個佔位頁。
  - 刪掉 `lib/auth.ts`，用 `npm uninstall jose` 移除套件，讓 `package-lock.json` 一起更新，因為 CI 跑 `npm ci`；從 `.env.example` 移除 `JWT_SECRET`。
- 錯誤格式與 fetch wrapper，後面所有卡共用：
  - 後台所有錯誤回應的格式統一為 `{"error": <錯誤碼>, ...}`。T-01 一次提供通用例外 `DashboardError(status, code, **extra)` 與 handler，後面的卡只 raise，不改共用的錯誤模組；FastAPI 預設的 RequestValidationError 也轉成 400 `invalid_request`，不用預設的 `{"detail": ...}`。exception handler 掛在 app 層，所以 RequestValidationError 的 handler 要依 `request.url.path` 分流：`/dashboard/` 開頭才轉換，其他路徑交回 FastAPI 預設的 `request_validation_exception_handler`，既有的 `/youtube_push`、`/callback/*` 不受影響。
  - 錯誤碼一覽：
    - 401：`session_expired`、`reauth_required`。
    - 403：`no_permission`。
    - 404：`bot_not_in_guild`。
    - 400：`invalid_request`，也用在 CSRF 的 Origin 檢查失敗；`invalid_field` 附欄位與原因，用在 T-06、T-07 的驗證失敗；`resolve_failed` 附 `reason`，值是 `not_found`、`unsupported_format` 或 `platform_unavailable`，用在 T-07；`scheduled_not_testable`，用在 T-08。
    - 409：`conflict` 附 `current` 或 `deleted: true`；`already_exists` 附已存在的項目，用在 T-06、T-07。
    - 429：`cooldown` 附 `retry_after`，用在 T-08。
    - 502：`send_failed` 附原因，用在 T-08；`discord_unavailable`，用在 T-02。
    - 503：`bot_unavailable`，見共通規則〈bot 尚未 ready〉。
  - 前端 fetch wrapper `lib/dashboard-api.ts`：後台所有 API 呼叫都經過它，一律帶 `credentials: "include"`；選項參數支援 `{timeoutMs?, signal?}`，後面的卡不必改這個檔；**依 `error` 碼分派，不依 HTTP 狀態碼**：
    - `session_expired`、`reauth_required`：顯示提示，按下後導向登入。導向前同步呼叫 `beforeLoginRedirect` 掛勾。
    - `no_permission`、`bot_not_in_guild`：提示並導回 `/dashboard`。`no_permission` 時先同步呼叫 `onNoPermission` 掛勾。
    - 掛勾由 wrapper 匯出 `setDashboardHooks({beforeLoginRedirect?: () => void, onNoPermission?: () => void})` 設定，都是同步函式，沒設就不做事。T-04 用它接上表單暫存。
    - `bot_unavailable`、`discord_unavailable`：顯示「稍後再試」，不導向。
    - 其他錯誤碼交給呼叫端處理。
    - 回應沒有 `error` 欄位的錯誤，例如路由不存在，一律當成一般錯誤顯示，不導向。
- 部署：
  - shark-ansible 的 `routes.yml` 在 XingyuBot 規則加上 `PathPrefix(`/dashboard/`)`。
  - 正式環境 domalyze-frontend 的 env：`NEXT_PUBLIC_BASE_API_URL` 改成 `https://api.domalyze.net`。build 讀的 env 可能來自兩處：`.github/workflows/deploy.yml` 用 GitHub Secret `PROJECT_ENV_FILE` 寫出的 `.env`，或 `docker-compose.yml` 的 `${DOMALYZE_FRONTEND_ENV_FILE:-.env}` 指到的 `/etc/domalyze-frontend/web.env`。shark-ansible 的備份 `secrets-backup/shark/etc/domalyze-frontend/web.env` 寫的是 `https://domalyze.net`。開工時先確認實際用的是哪一處，改那一處。這個變數在 build 時寫進產物，改完要重新 build。目前 main 沒有程式讀它，改值不影響現有頁面。
  - 正式環境 xingyubot 的 env 加上 `DASHBOARD_FRONTEND_URL`、`DASHBOARD_ALLOWED_ORIGINS`，XingyuBot 的 `.env.example` 也補上。`AppSettings` 也被 `twitch_main.py` 與本機 `.env` 共用，所以只在啟動 website（`API_WEBSITE=true`）時檢查這兩個設定，沒設就報錯，避免正式環境默默用錯網址。

**依賴**：無

**風險 / 實作注意**
- 官網和 API 同屬 `domalyze.net`，算同一個 site，SameSite=Lax 的 cookie 在帶 credentials 的 fetch 會送出。本機開發時前端與 API 都要用 https，例如前端用 `next dev --experimental-https`。scheme 不同在 schemeful same-site 下算 cross-site，只放寬 Secure 沒用，SameSite=Lax 的 cookie 仍不會送出。
- 沒有 `dashboard_oauth` 時，`/oauth/discord` 帶 `guild_id` 的行為保持不變；T-09 會再擴充這個分支。
- 開工時實測：Discord 對同一使用者發新 token 時，舊 token 會不會失效。會失效的話，用官網首頁邀請 bot 後，使用者下次操作後台會看到「需要重新授權」，這是〈決策紀錄〉第 3 題接受的代價；實測結果記在卡上。

**進度**：完成（2026-11-08），剩 Discord token 行為實測
- commit：XingyuBot `bfbde5e`、domalyze_frontend `f0f1f22`、shark-ansible `bdc57f7`，已 push 並部署。
- 正式環境已驗證：Discord 授權登入、未登入開 `/dashboard/guilds/<id>` 授權後回到該頁、`domalyze.net` 導向新網域。
- 正式環境的前端網域改為 `xingyu.domalyze.net`，`domalyze.net` 與 `www` 保留給之後的工作室網頁，目前由 Traefik 302 導向星羽網站；所以第 10 條驗收的 `www.domalyze.net`／`domalyze.net` 改由 `xingyu.domalyze.net` 取代，未勾，正式環境的 `DASHBOARD_FRONTEND_URL` 是 `https://xingyu.domalyze.net`，`DASHBOARD_ALLOWED_ORIGINS` 是 `["https://xingyu.domalyze.net"]`。
- 未驗：開工時要求的實測「Discord 發新 token 舊 token 會不會失效」，需要真實 Discord 憑證與兩個授權，結果出來要記在這裡。
- 實作時的取捨：登入換 token 失敗回 400 純文字頁；登出時 Discord 撤銷失敗不擋登出，本地 session 與 token 仍刪除，所以授權會殘留到 token 自然到期，本地已無 token 可重試；`client.py` 新增公開的 `release_session()` 給 `run_db` 用。

### T-02 管理員能看到可管理的伺服器清單

**使用者價值**：管理員登入後能一眼看到哪些伺服器已經有星羽、哪些還可以邀請。

**範圍**
- 包含：
  - 「已邀請」「未邀請」兩組，依權限篩選。
  - 10 分鐘快取與手動重新整理。
  - 空清單的說明。
  - Discord 授權失效時，清單頁的提示與重新授權。
- 不包含：
  - 點進伺服器後的通知頁，留到 T-03。
  - 邀請流程，留到 T-09。這張卡的「未邀請」項目和空清單的邀請入口，先連到前端既有的 `NEXT_PUBLIC_BOT_INVITE_URL`。T-01 已經讓這條路不會覆寫後台的 token。

**驗收條件**
- [x] bot 已在且自己有 Manage Channels 的伺服器列在「已邀請」；bot 不在且自己有 Manage Server 的伺服器列在「未邀請」；其他伺服器都不出現。Administrator 與擁有者視同具備所有權限。
- [x] 每筆顯示伺服器圖示與名稱，依名稱排序。
- [x] 沒有任何可顯示的伺服器時，顯示說明與邀請入口。
- [x] 在 Discord 拔掉自己的 Manage Channels 後，按重新整理，該伺服器從「已邀請」消失；不按的話最多 10 分鐘後消失。
- [x] bot 加入或離開某伺服器後，重新載入清單頁時立即反映，不受 10 分鐘快取影響。
- [x] 在 Discord 撤銷授權後按重新整理，看到需要重新授權的提示，按下後才導向授權；授權回來後清單正常。
- [x] 360px 寬時清單可以完整操作。

**實作設計**
- 後端：
  - 在 `starServer/dashboard/` 新增伺服器清單服務：
    - 用使用者的 `OAuthToken` 呼叫 Discord `GET /users/@me/guilds`，取得每個伺服器的 `permissions`、`owner`、名稱與圖示。
    - token 過期時用 refresh token 換新，成功後先 `self.db_token = self.to_db_token(token)`，再補 `self.db_token.client_credential_id = self._credential_id`，最後呼叫 `save_token_to_db(user_id)` 寫回。補這一步是因為 `to_db_token` 傳的是 `OAuthToken` 沒有的 `credential_id`（`oauth_lib.py:233-240`），主鍵欄位 `client_credential_id` 沒被設定，`exchange_code` 也是在 `:129` 另外補上。`OAuth2Base.refresh()` 本身不會寫回資料庫，所以要自己寫回。不能把 refresh 回傳的 dict 直接交給 `save_token_to_db`：它的 scope 是空白分隔字串，`OAuthToken.scope` 是 `ARRAY(String)`，寫入會失敗，`to_db_token` 才會先 split（`oauth_lib.py:194-201`、`:226-233`）。這段要有單元測試，確認 refresh 後寫回的 scope 是陣列、`client_credential_id` 正確。refresh 失敗、Discord 回 401，或 token 的 scope 沒有 `guilds`，都視為授權失效。
    - Discord 回 429 或網路錯誤，不算授權失效：有舊快取就沿用，沒有就回 502，錯誤碼 `discord_unavailable`，前端顯示稍後再試。
    - OAuth instance 用 `async with` 建立，用完關閉連線，`oauth_lib.py` 的 `aclose` 註解有要求。
    - 結果存在記憶體快取，以 Discord user ID 為 key，10 分鐘過期。
    - 過期後由下一次請求觸發重抓，不做背景輪詢。
    - 提供 `invalidate(user_id)` 給 T-09 使用；這張卡也在 T-01 的 logout 與 login callback 裡呼叫它，重新授權回來後一定重抓。
    - 授權失效、429、網路錯誤的結果都不寫進快取。
    - 同一個 user_id 的重抓與 refresh 用 single-flight 序列化，例如每個 user_id 一把 `asyncio.Lock`，第二個請求等第一個的結果。Discord 的 refresh token 用一次就換新，同時 refresh 兩次，第二次會失敗而被誤判成授權失效。
  - 權限判斷寫成一個函式，例如 `guild_perms(user_id, guild_id) -> {manage_channels, manage_guild}`：
    - Administrator 或 owner 視同全部權限。
    - 使用者的清單裡沒有該伺服器，視同沒有權限。
    - T-03、T-09 也用它。
    - 這個函式會觸發快取重抓，所以授權失效時要能拋出可辨識的例外。
  - bot 在不在伺服器，每次請求即時判斷（經 `sclient.bot.submit`），不快取。
  - `GET /dashboard/guilds?refresh=1`：回傳兩組清單，`refresh=1` 時略過快取。授權失效時回錯誤碼 `reauth_required`，跟 `session_expired` 區分開。
- 前端：
  - `app/dashboard/page.tsx` 實作兩組清單、重新整理按鈕與空狀態。
  - 經 T-01 的 fetch wrapper 呼叫，`reauth_required` 的提示與導向由 wrapper 處理。

**依賴**：T-01（登入與 session）

**風險 / 實作注意**：記憶體快取在重啟後會清空，重啟後的第一次請求會重抓，這是預期行為。

**進度**：完成（2026-11-08），已部署並在正式環境驗收
- commit：XingyuBot `53cbaf0` 與後續的登出鎖修正、domalyze_frontend `c79f300`，已 push 並部署。
- 正式環境驗收條件全部通過。
- 實作時的取捨：登出與 token refresh 共用 `auth.user_lock`，避免登出刪掉 token 後進行中的 refresh 又寫回；登入與登出清快取經 `auth.on_auth_change` 通知，`auth.py` 不依賴 `guilds.py`。

### T-03 管理員能看到伺服器的通知一覽

**使用者價值**：管理員能在一個頁面看完伺服器目前設了哪些通知，這是規格要解決的第一個問題。這張卡也建立後面所有卡共用的存取檢查與有效性判斷。

**範圍**
- 包含：
  - 頻道通知與社群推播的唯讀一覽，包括失效標示。
  - 存取檢查，並在頁面載入時處理 bot 不在、沒有權限、授權失效三種情況。
  - 有效性判斷函式與欄位對照常數。
- 不包含：
  - 新增、修改、刪除，留到 T-06、T-07。
  - 測試按鈕，留到 T-08。
  - 存檔或測試時的錯誤處理，留到 T-06、T-07、T-08。

**驗收條件**
- [x] 資料庫裡有 `NotifyCommunity` 卻沒有對應 `Community` 的推播，一覽仍然列出，顯示帳號 ID。
- [x] 點進已邀請的伺服器，只列出已設定的通知。每筆的頻道，以及該種類用得到的身分組，跟 `/channel list` 與各平台 list 指令查到的一致；自訂文字跟資料庫裡的值一致。
- [x] 用指令替天氣預報設了身分組，一覽不顯示這個身分組。
- [x] 社群推播顯示「顯示名稱（帳號）」；沒有 handle 的 YouTube 頻道，括號裡顯示頻道 ID。
- [x] 用指令把通知設在之後被刪除的頻道、bot 不能發訊息的頻道，或 bot 無法 tag 的身分組，一覽把那筆標成失效並說明原因。
- [x] 一筆通知都沒有時，顯示說明。
- [x] 沒有 Manage Channels 的帳號直接打開某伺服器的通知頁網址，看到沒有權限的提示並回到清單。
- [x] bot 不在的伺服器，打開它的通知頁網址，看到 bot 已不在的提示並回到清單。
- [x] 360px 寬時一覽可以完整閱讀。

**實作設計**
- 後端：
  - 存取檢查寫成 dependency `require_guild_access(guild_id)`，T-04～T-09 共用：
    - 先確認 session。
    - 用 T-02 的 `guild_perms` 確認使用者有 Manage Channels：不符回 403，錯誤碼 `no_permission`；授權失效回 401，錯誤碼 `reauth_required`。
    - 確認 bot 在該伺服器：不在回 404，錯誤碼 `bot_not_in_guild`。
  - 欄位對照常數，例如 `starServer/dashboard/notify_fields.py`，後面的卡都用它：
    - 定義字串種類鍵，例如 `channel:<NotifyChannelType 值>`、`community:<NotifyCommunityType 值>`，並提供跟 enum 互轉的函式。
    - 把規格〈通知種類與欄位〉的表寫成常數，記錄每種通知用得到哪些欄位、是不是定時通知。
    - 記錄每種通知的顯示名稱：頻道通知取 `database/command_option.json` 的 `channel_set_option` zh-TW；Twitch 三種取 `twitch_notify_option`；YouTube、Twitter 檔案裡沒有，直接寫在常數裡。
  - 有效性判斷函式，例如 `starServer/dashboard/validity.py`，T-04、T-06、T-07 也用：
    - `channel_invalid_reason(guild, channel_id, scheduled: bool) -> str | None`：
      - 頻道要存在，類型是文字或公告頻道。
      - bot 要有 View Channel、Send Messages、Embed Links；`scheduled` 為真時另要 Read Message History。
      - 失效時回傳原因，例如「頻道不存在」「不支援的頻道類型」「bot 缺少 Send Messages」；有效時回 None。
    - `role_invalid_reason(guild, role_id) -> str | None`：
      - 身分組要存在，而且開啟了「允許任何人提及」，或 bot 有 Mention Everyone。
      - @everyone、bot 自己的身分組，以及 managed 的身分組都視為無效。
  - `GET /dashboard/guilds/{id}/notifies` 回傳兩份清單：
    - 讀取用 `client.py` 新增的方法，例如 `get_dashboard_notifies(guild_id: int)`，查詢加 `populate_existing`，見共通規則〈讀到最新的資料〉；既有的 `get_notify_channel_all` 沒有加，不能直接用。
    - 頻道通知查 `NotifyChannel`，只列欄位對照表裡的種類；社群推播查 `NotifyCommunity` LEFT JOIN `Community`，顯示名稱用 `display_name`，為 null 時改用 `username`；括號裡用 `username`。
    - 缺 `Community` 的 `NotifyCommunity` 仍然列出，名稱與括號都顯示帳號 ID，可以照常修改與刪除。這種孤兒列會在指令先寫入 `NotifyCommunity`、接著 merge `Community` 失敗時留下（`system_community.py:168-169`），它仍然會發通知。
    - 只輸出該種類用得到的欄位，每筆附上失效原因與該筆目前的值。後者讓 T-04 拿來當衝突比對的原始值。
  - 現有沒有 handle 的 YouTube 資料：指令存入時 `username` 用的是 `customUrl`，因為 `username` 不可為 null，沒有 handle 時 merge 會失敗，留下上面說的孤兒列。開工時查一次資料庫有沒有孤兒列，記在卡上。往後由 T-07 確保寫入時有值。
- 前端：
  - `app/dashboard/guilds/[id]/page.tsx` 由兩個區塊元件組成，各自放在獨立的檔案：`components/dashboard/channel-notify-section.tsx`、`components/dashboard/community-notify-section.tsx`。T-06、T-07 各自擴充一個，避免並行時改到同一處。
  - 經 T-01 的 fetch wrapper 呼叫，`no_permission`、`bot_not_in_guild`、`reauth_required` 都由 wrapper 處理。
  - 種類名稱由一覽 API 一起回傳，來源見上面的欄位對照常數。

**依賴**：T-02（`guild_perms`、清單頁的進入點）

**進度**：完成（2026-11-08），已部署並在正式環境驗收
- commit：XingyuBot `e468427`、`8ae39a1`，domalyze_frontend `e77d19c`、`2514524`、`07a6f9f`、`509bcb7`，已 push 並部署。
- 正式環境驗收條件全部通過。孤兒列檢查：2026-11-08 查正式 DB（`stardb`，`stardb_basic.notify_community` LEFT JOIN `community_info`），0 筆孤兒列。
- 實作時的取捨：存取檢查放 `dashboard/access.py`（含 `on_guild`，讀 Discord 物件一律經它）而非 `notifies.py`，避免後續卡互相 import 路由模組；討論串當頻道時失效原因會顯示「頻道不存在」，未特別區分；前端版面改為側欄加分隔列，社群推播依帳號分組，`ChannelNotifySection`、`CommunityNotifySection` 保留 `headerActions`，`NotifyRow` 保留 `actions`，供 T-06、T-07 放按鈕。專案 eslint 設定本身載入失敗（既有問題），前端沒跑 lint。

### T-04 [共用] 通知編輯：選項、衝突比對、表單暫存

**使用者價值**：T-06、T-07 都要用到頻道與身分組選單、衝突比對與表單暫存。抽成共用卡，避免各寫一套、行為不一致。規格的「未存內容要保留」「換帳號就丟棄」「權限不足時不保留」的暫存部分集中在這裡。

**範圍**
- 包含：
  - 頻道與身分組選項 API 與選單元件。
  - 以「打開時的值」做衝突比對的服務，以及衝突提示元件。
  - 表單內容的暫存與還原介面，接上 T-01 fetch wrapper 的暫存掛勾。
- 不包含：各類通知的表單與寫入，留到 T-06、T-07。

**驗收條件**
- [x] 頻道選項與身分組選項，只包含 T-03 有效性判斷認為有效的頻道與身分組。
- [x] 衝突比對：傳入的原始值與資料庫目前的值不同，或那一筆已被刪除，就回報衝突並附上目前的值；值相同才允許寫入。
- [x] 選項 API 收到 `bot_not_in_guild`、`no_permission` 時，由 wrapper 提示並導回清單。
- [x] domalyze_frontend 加入 vitest 與 jsdom，`package.json` 新增 `npm test`，CI 的 deploy workflow 在 build 前跑 `npm test`。
- [x] 暫存介面有單元測試：註冊的表單在 wrapper 導向前被存下；同一個帳號回來時 `consumeDraft` 取得內容；不同帳號時取不到；收到 `no_permission` 時暫存被清掉。
- [x] 選項 API 與衝突比對服務有單元測試。
- [ ] 表單實際的暫存與還原，在 T-06、T-07 各自驗收。

**實作設計**
- 介面：
  - `GET /dashboard/guilds/{id}/options?notify_type=<種類>`：回傳 `{channels: [{id, name, type}], roles: [{id, name, color}]}`。經過 `require_guild_access`；依種類是否為定時通知，決定頻道是否要 Read Message History。
  - 後端函式 `check_conflict(current: dict | None, original: dict) -> Conflict | None`：
    - `original` 是使用者打開表單時看到的值，只含該種類用得到的欄位。
    - `current` 為 None 表示已被刪除。
    - 有衝突時回 `Conflict(current_values | deleted)`。
  - 前端暫存介面，例如 `lib/dashboard-draft.ts`：
    - `registerDraft(entryKey, mode, getState)`：表單打開時註冊，關閉時取消註冊。`entryKey` 是哪一筆或哪個新增流程，`mode` 是新增或編輯，`getState()` 回傳表單要還原所需的全部狀態，內容由各表單自己決定，例如 T-07 的新增流程要包含已查到的帳號與勾選的種類。
    - 在 `app/dashboard/layout.tsx` 取得 `/dashboard/me` 之後呼叫 T-01 的 `setDashboardHooks` 接上，userId 用 `/dashboard/me` 回傳的 ID：`beforeLoginRedirect` 把目前註冊的表單存成 `{userId, entryKey, mode, state}` 放進 sessionStorage；`onNoPermission` 清掉暫存。
    - `consumeDraft(entryKey) -> {mode, state} | null`：頁面載入後，各表單用它取回自己的暫存並重新打開；取出後即刪除。暫存的 `userId` 跟目前帳號不同時回 null。T-01 的換帳號偵測本來就會丟棄全部暫存，這裡再擋一次。
  - 前端元件：
    - 頻道與身分組選單：`components/dashboard/channel-select.tsx`、`role-select.tsx`。
    - 衝突提示：`components/dashboard/conflict-notice.tsx`，並排顯示最新版本與使用者的輸入，提供「以我的內容覆蓋」按鈕。按下後用最新版本當新的原始值再送一次。最新版本是「已刪除」時，按鈕改成「重新新增」，呼叫呼叫端傳入的 `onRecreate`；怎麼重新新增由 T-06、T-07 各自決定。
- 後端：衝突比對採「比對打開時的值」，不新增版本欄位，原因是 XingyuBot 沒有 migration 工具，改既有表要手動 ALTER。

**依賴**：T-03（`require_guild_access`、有效性判斷、欄位對照常數）。fetch wrapper 來自 T-01。

**風險 / 實作注意**：「比對打開時的值」偵測不到 A→B→A 的變化，也就是改過又改回原值的情況。規格沒有要求偵測這種情況。

**進度**：完成（2026-11-08），已部署並在正式環境驗收
- 實作時的取捨：衝突比對放 `dashboard/conflict.py`，`Conflict.to_error()` 產生 409（`{"error":"conflict","deleted":bool,"current":{...}|null}`），T-06、T-07 直接 raise；`check_conflict` 只比對 `original` 有的欄位，兩邊都轉字串後比。暫存介面的 `userId` 不由 `registerDraft` 傳入，改由 layout 呼叫 `createDraftHooks(me.id)` 設定，`consumeDraft(entryKey)` 取出時就刪除，帳號不符也一併刪除。選項 API 的頻道依 position 排序、身分組由高到低；`color` 為 `#rrggbb`，沒設為 null。前端另有 `lib/dashboard-options.ts`（`useNotifyOptions`）供表單載入選項；選單在目前的值不在選項內時會顯示「（無法使用）」。`npm test` 為 `vitest run`。
- commit：XingyuBot `13288a3`，domalyze_frontend `f53b9be`，已 push 並部署。
- 驗收條件中選項 API 的 `bot_not_in_guild`、`no_permission` 沿用 T-01 wrapper 既有處理，後端已有測試。

### T-05 [共用] 通知範例內容：預覽與測試共用

**使用者價值**：T-06、T-07 的預覽與 T-08 的測試訊息必須長得一樣，抽成同一個產生器。

**範圍**
- 包含：依通知種類與設定值產生範例訊息，包括文字、身分組提及與卡片；提供預覽 API 與預覽元件。
- 不包含：實際發送，留到 T-08。

**驗收條件**
- [x] 每種通知都能產生範例：卡片用該種類的範例資料，不呼叫外部平台 API。
- [x] 成員加入、成員離開只產生純文字，沒有卡片；`{member}`、`{guild}` 會被代換。
- [x] Twitter 推播跟實際發送一樣沒有卡片：內容是預設文字「{fullName} 發布新推文」，換行後接一行範例推文網址（`task.py:309-315`）。
- [x] 自訂文字留空時，使用 bot 實際發送時的預設文字。
- [x] 只採用欄位對照表中打勾的欄位；資料庫裡存著、但表上沒打勾的值不會出現在範例中。
- [x] 各種類有單元測試；現有通知實際發出的內容不變。

**實作設計**
- 介面：
  - `build_sample(notify_type, values: dict, *, member: Member | None, guild: Guild) -> SampleMessage`。
  - `SampleMessage` 包含：`content: str`、`embeds: list[discord.Embed]`、`mention_role_id: int | None`。
    - `content` 是已經把身分組提及放在正確位置的最終文字，位置跟現有發送端一致：頻道通知是「預設文字＋空格＋提及」（`bot.py:241-243`），社群推播是「提及＋空格＋文字」（`bot.py:216-218`），全群公告與機器人更新只送提及（`owner.py`）。
    - `mention_role_id` 只給 `allowed_mentions` 與預覽標示使用，呼叫端不再自己組文字。
    - 社群推播的 `additional_content` 照 `send_notify_communities` 的規則接在文字後面，Twitter 用它放推文網址。
  - 傳入 `member` 時，`{member}` 代入該成員的提及；沒傳入時代入範例成員的提及形式，預覽元件把它顯示成 `@範例成員` 的樣子。
  - `POST /dashboard/guilds/{id}/preview`：body 是 `{notify_type, values}`，回傳可在網頁呈現的資料，也就是 content 文字與 embed 的 JSON。經過 `require_guild_access`。
- 後端：
  - 預設文字以現有發送端的寫法為準，各自的來源在呼叫端：
    - 地震、天氣預報：`starDiscord/cmds/task.py:102`、`:104`、`:152`。
    - 全群公告：`starDiscord/cmds/owner.py:62-79`；機器人更新：`owner.py:88-115`。兩者都由各自的 embed 組出。
    - 成員加入、離開：`starDiscord/cmds/bot_event.py`。
    - 天氣警報（`task.py:131`）、Apex 輪替（`task.py:158`，多個 embed）、加入紀錄與離開紀錄（`bot_event.py:473-486`、`:512-525`）、語音紀錄（`bot_event.py:398` 起）：沒有預設文字，只用範例 embed。
    - 社群推播：`starDiscord/bot.py` 的 `send_notify_communities`，以及各輪詢任務傳入的 `default_content`。
    - 這張卡只把這些文字複製或引用到產生器，不改現有的發送端。
  - 範例卡片可以沿用各 provider model 的 `embed()` 方法，建一個假資料物件來產生；做不到的種類寫成固定的範例 embed。
- 前端：預覽元件，例如 `components/dashboard/notify-preview.tsx`，呈現文字、身分組提及與 embed 的大致外觀，經 T-01 的 fetch wrapper 呼叫預覽 API。T-06、T-07 共用。

**依賴**：T-03（欄位對照常數）

**風險 / 實作注意**：預設文字目前散在多個檔案，抽出來時不要改變現有通知實際發出的內容。

**進度**：完成（2026-11-08），已部署並在正式環境驗收
- commit：XingyuBot `671e4f1`，domalyze_frontend `bdf76e8`，已 push 並部署。
- 實作時的取捨：範例卡片全部寫成固定的範例 embed（`dashboard/samples.py`），沒有用各 provider model 的 `embed()` 造假資料，避免為了建物件去湊一堆必填欄位；欄位與外觀照現有 embed 的寫法。預設文字從發送端複製，測試會檢查這些字串仍存在於 `task.py`、`bot_event.py`、`bot.py`，發送端改動時會提醒同步。`build_sample` 的 `notify_type` 用字串種類鍵，`values` 只採用欄位對照表打勾的欄位。預覽 API 多回 `mention_role_name`（該身分組存在時），前端把 `<@&id>` 顯示成 `@名稱`、成員提及顯示成 `@範例成員`。預覽元件是 `components/dashboard/notify-preview.tsx`，`useNotifyPreview` 在值變動 400ms 後才呼叫 API。

### T-06 管理員能新增、修改、刪除頻道通知

**使用者價值**：管理員能在網頁上設定 12 種頻道通知，不必再一筆筆打指令。

**範圍**
- 包含：
  - 頻道通知的新增、修改、刪除與二次確認。
  - 只顯示用得到的欄位。
  - 定時通知的提醒、預覽、衝突處理。
  - 失效設定必須重選頻道；失效的身分組可以清空。
- 不包含：社群推播（T-07）；測試（T-08）。

**驗收條件**
- [ ] 各種類的表單只出現欄位對照表中打勾的欄位；例如天氣預報沒有身分組與自訂文字欄位，成員加入除了頻道只有自訂文字欄位。頻道必填。
- [ ] 對已設定的種類按新增，打開的是那一筆的編輯。
- [ ] 編輯天氣預報或 Apex 輪替時，看到「訊息要保持在最新位置」的提醒。
- [ ] 在成員加入的自訂文字輸入 `{member}`，預覽顯示成範例成員的提及。
- [ ] 在網頁修改一筆用指令設定的通知，`/channel list` 查到的結果跟著改變；用指令替天氣預報設的身分組，在網頁存檔後仍在。
- [ ] 刪除前出現確認視窗，顯示要刪除的通知種類；刪除後一覽與指令都查不到這筆。
- [ ] 一筆頻道通知都沒有時，頻道通知區塊顯示說明與新增入口。
- [ ] 衝突：
  - A、B 同時新增同一種尚未設定的通知，後存的被擋下，看到 A 存的版本，自己的輸入仍在，確認後可以覆蓋。
  - A、B 同時打開同一筆，A 先存；B 存檔時被擋下並看到最新版本，自己的輸入仍在，確認後可以覆蓋。
  - A 打開後有人用指令改了同一筆，A 存檔被擋下。
  - A 打開後 B 改了同一筆，A 按刪除被擋下。
- [ ] 失效的頻道不重選就不能存；失效的身分組可以清空後存檔。
- [ ] 直接呼叫 API 送出 bot 無法發訊息的頻道或無法 tag 的身分組，請求被拒絕。
- [ ] 通知頁開著時把 bot 踢出伺服器，接著按存檔，看到 bot 已不在的提示並回到清單。
- [ ] 表單編輯到一半，在 Discord 撤銷授權並等快取過期後按存檔，看到需要重新授權的提示；重新授權回來後，表單重新打開，內容仍在，而且能存檔。session 過期時也一樣。
- [ ] 回來時換成另一個 Discord 帳號，表單內容丟棄，回到伺服器清單。
- [ ] 360px 寬時表單可以完整操作。

**實作設計**
- 資料：`client.py` 新增只新增不覆蓋的方法，例如 `insert_notify_channel`：用 insert，主鍵衝突時拋出可辨識的例外，不用 `merge`。成功後比照 `add_notify_channel` 更新 VoiceLog 的記憶體快取（`cache.voice_log.set`），否則網頁新增的語音紀錄要等 bot 重啟才生效。
  - 另外新增條件式的修改與刪除方法，例如 `update_notify_channel_if(guild_id, notify_type, original, values)`、`delete_notify_channel_if(guild_id, notify_type, original)`：
    - `UPDATE`／`DELETE ... WHERE <主鍵> AND channel_id = :orig AND role_id IS NOT DISTINCT FROM :orig AND message IS NOT DISTINCT FROM :orig`，比對與寫入在同一條 SQL 完成。
    - 回傳影響的列數；0 表示已被改過或刪除。
    - 成功後比照 `add_notify_channel`、`remove_notify_channel` 更新或清掉 VoiceLog 的記憶體快取。
    - 指令仍走原本的 `add_notify_channel`、`remove_notify_channel`。
- 後端：
  - `PUT /dashboard/guilds/{id}/channel-notifies/{notify_type}`：body 是 `{values, original}`，`original` 為 null 表示新增。
    - **新增**：呼叫 `insert_notify_channel`。主鍵衝突，包括送出前剛被別人新增，回 409，錯誤碼 `already_exists`，附上已存在那一筆的目前值。
    - **修改**：呼叫 `update_notify_channel_if`，只更新用得到的欄位，表上沒打勾的欄位不動。影響 0 列時，用 `populate_existing` 讀出目前的列（見共通規則〈讀到最新的資料〉），交給 T-04 的 `check_conflict` 組出 409 的內容。
    - **驗證**：只驗用得到的欄位。頻道用 `channel_invalid_reason`，身分組有值時用 `role_invalid_reason`；失效回 400 `invalid_field` 並附欄位與原因，前端把原因標在對應的欄位下。
  - `DELETE /dashboard/guilds/{id}/channel-notifies/{notify_type}`：body 帶 `original`，呼叫 `delete_notify_channel_if`；影響 0 列時同樣讀出目前的列回 409。
  - 修改與刪除都用條件式寫入，兩人同時存或刪同一筆時，後到的一定被擋下。見〈決策紀錄〉第 2 題。
- 前端：
  - 在 `channel-notify-section.tsx` 加入新增按鈕（選種類）、編輯表單、刪除確認。
  - 表單用 T-04 的選單、T-05 的預覽，經 T-01 的 fetch wrapper 呼叫 API，收到 409 時顯示衝突提示。
  - 表單打開時用 T-04 的 `registerDraft` 註冊，頁面載入時用 `consumeDraft` 還原。
  - 衝突提示的 `onRecreate`：用 PUT 以 `original=null` 重新新增。
  - 新增遇到已存在，分兩種情況：
    - 按新增時，一覽上已經有這一筆：直接打開那一筆的編輯。
    - 送出時才收到 `already_exists`，也就是別人剛新增：把附的目前值當 `current` 交給衝突提示，使用者的輸入保留。按「以我的內容覆蓋」時，以目前值當 `original` 改走修改。

**依賴**：T-04（選單、衝突、表單暫存）、T-05（預覽）

**風險 / 實作注意**：條件式寫入的 `original` 只含該種類用得到的欄位，沒打勾的欄位不放進 WHERE，否則用指令設的值會讓比對永遠失敗。

**進度**：未完成

### T-07 管理員能新增、修改、刪除社群推播

**使用者價值**：管理員能在網頁上設定 Twitch、YouTube、Twitter 推播，貼網址就能找到帳號。

**範圍**
- 包含：
  - 帳號名稱或網址的解析與確認。
  - 新增時一次勾選多種 Twitch 推播，任一種已存在就整批擋下。
  - 修改只能改頻道、身分組、自訂文字。
  - 刪除可以只刪一種，並有二次確認。
  - 寫入與後續清理和指令完全相同。
- 不包含：頻道通知（T-06）；測試（T-08）。

**驗收條件**
- [ ] 輸入名稱或貼網址都能找到帳號，存檔前顯示「顯示名稱（帳號）」供確認。網址有沒有 `https://`、`www.`、`m.`，後面有沒有接路徑或 query 都接受；YouTube handle 少打 `@` 也接受；不分大小寫。
- [ ] 找不到時無法存檔，並顯示原因：帳號不存在、網址格式不支援，或平台暫時無法查詢。
- [ ] Twitter 的表單沒有自訂文字欄位。
- [ ] 新增 Twitch 推播勾選開台與剪輯，一覽出現兩筆，兩筆可以設在不同頻道；刪掉其中一筆，另一筆不受影響。其中一種已存在時整批擋下，並標出已存在的種類。
- [ ] 新增 YouTube 或 Twitter 推播時，該帳號已經設定過，就改成打開那一筆的編輯。
- [ ] 一筆社群推播都沒有時，社群推播區塊顯示說明與新增入口。
- [ ] 對一個之前沒人訂閱過的 Twitch、YouTube、Twitter 帳號新增推播，該帳號開台、發片或發文時，通知發到指定的頻道並 tag 指定的身分組。
- [ ] YouTube 推播訂閱失敗時，設定仍然存入，並顯示提示。
- [ ] 貼上 `youtube.com/channel/<頻道 ID>` 加入沒有 handle 的 YouTube 頻道，一覽括號裡顯示頻道 ID。
- [ ] 修改時，對象帳號與推播種類不能改。
- [ ] 刪除前出現確認視窗，顯示要刪除的推播種類與對象帳號。某個種類在所有伺服器都沒人訂閱後，該種類的 `CommunityCache` 被清掉；一個帳號在所有伺服器、所有種類的推播都刪光後，該帳號的 `Community` 與 YouTube 的 `PushRecord` 也被清掉。
- [ ] 衝突處理、失效設定、bot 不在與權限不足的處理，都跟 T-06 相同。
- [ ] 新增流程進行到一半，例如已查到帳號並勾好種類，session 過期或授權失效；回來後新增流程停在同一步，已查到的帳號與勾選的種類都還在，而且能存檔。編輯表單也一樣。
- [ ] 360px 寬時新增流程與表單可以完整操作。

**實作設計**
- 資料：
  - `client.py` 新增批次新增社群推播的方法，套用既有的 `_rollback_on_error`：
    - 在同一個交易內，先 `SELECT` 勾選的種類裡哪些已經存在，有就整批不寫，回報全部已存在的種類。
    - 沒有就 insert 多筆 `NotifyCommunity`，並在同一個交易用 `session.merge` 寫入 `Community`，不會再留下孤兒列。整段不呼叫會自己 commit 的 `sqldb.merge`。insert 的 IntegrityError 只當作 SELECT 之後被別人搶先寫入的後備，同樣回報衝突。
    - 只有 `NotifyCommunity` 的主鍵衝突算 `already_exists`；`CommunityCache` 用 `ON CONFLICT DO NOTHING` 寫入，帳號已被其他伺服器訂閱時不會造成衝突。
  - `CommunityCache` 比照 `add_notify_community` 的 `cache_time=nowtz()` 寫入；`Community` 的欄位比照各 set 指令（`system_community.py:43`、`:169`、`:280`）。少寫 `Community` 的話，指令的 list 用 inner join 會查不到這筆。
  - 上面的批次方法叫 `insert_notify_communities`，只負責 `NotifyCommunity`、`Community`、`CommunityCache` 三張表，一個交易完成。
  - 條件式的修改與刪除方法，做法同 T-06：`update_notify_community_if`、`delete_notify_community_if`，WHERE 帶主鍵加頻道、身分組、自訂文字的原始值，回傳影響的列數。刪除成功後執行跟 `remove_notify_community` 相同的清理，清理抽成共用的內部函式，兩邊都呼叫它。
  - 規格外的修正：`remove_notify_community` 目前只刪掉「這次刪除的那個種類」的 `CommunityCache`（`client.py:540-553`），例如某 Twitch 帳號先刪開台、再刪剪輯，開台的輪詢紀錄會留下來。輪詢任務是逐筆掃 `CommunityCache`（`task.py:190-245`），留下的紀錄會一直被輪詢。改成依種類判斷：某帳號的某個種類已經沒有任何 `NotifyCommunity`，就刪該種類的 `CommunityCache`；整個平台都沒有推播時，再刪 `Community` 與 `PushRecord`。指令也走這個方法，會一起受益。
- 後端：
  - 在 starlib 新增社群推播的設定服務，例如 `starlib/notify_settings.py`。服務寫成同步函式。端點把寫 DB 的步驟交給 `run_db`；「確保 YouTube 訂閱」的網路呼叫與等待改用預設 executor，只有最後更新 `PushRecord` 再交給 `run_db`，避免長達約 70 秒的等待佔住 `run_db` 的小 executor。YouTube 訂閱時 `add_push` 會用 `time.sleep` 重試，cog 在 `add_push` 與 `get_push` 之間另有等待 3 秒，服務內改用 `time.sleep(3)`，因為整段都在 executor 裡執行：
    - **解析帳號**：輸入是名稱或網址，輸出平台帳號 ID、顯示名稱與 username。
      - 網址先正規化：去掉 scheme、`www.`、`m.`、路徑尾段與 query，再取出名稱、handle 或頻道 ID。
      - YouTube 用 `google_api.get_channel(handle=...)` 或 `get_channel(channel_id=...)` 查詢。
      - 沒有 handle 的 YouTube 頻道，username 存頻道 ID，因為 `Community.username` 不可為 null。這樣一覽括號裡就會是頻道 ID。
      - 錯誤分成三種：不存在、格式不支援、平台暫時無法查詢。
      - 網址或名稱的格式先在解析服務裡檢查，格式不合法直接歸成「格式不支援」，不送去平台查詢。
      - `platforms.py` 要改的點：
        - Twitch：`get_user` 與 `get_user_by_id` 在 404 時都回 None，不呼叫 `.json()`。`APINetworkError` 的 `status_code` 是 400 時歸成「格式不支援」；只有 5xx、429 與網路錯誤歸成「平台暫時無法查詢」。
        - YouTube：`get_channel` 遇到配額或 5xx 會拋 `APINetworkError`，歸成「平台暫時無法查詢」；404 時同 Twitch，回 None，不呼叫 `.json()`（`platforms.py:206-214`）。
        - Twitter：JSON 解析失敗改成拋例外，不回 None。`CalledProcessError`、`TimeoutExpired`、rettiwt 不存在時的 `FileNotFoundError`（`platforms.py:571-572`）與 JSON 解析失敗，都歸成「平台暫時無法查詢」；回 None 才算「不存在」。
        - 既有呼叫端的行為要維持不變，需要的話自己接住新的例外。呼叫端：Twitch、Twitter 在 `system_community.py:40`、`:69`、`:137`、`:269`、`:295`、`:335`；YouTube 的 `get_channel` 在 `:145`、`:166`、`:203`、`:215`。`test/test_community.py` 直接測了 `get_user_details`，要跟著調整。
    - **新增推播**：呼叫 `insert_notify_communities`，YouTube 再接著做「確保 YouTube 訂閱」。
    - **修改推播**：只改頻道、身分組、自訂文字，不改 `Community`、不查平台；YouTube 再接著做「確保 YouTube 訂閱」。帶 `original` 時用 `update_notify_community_if`，影響 0 列就回報衝突；指令呼叫時不帶 `original`，用原本的 `add_notify_community`。
    - **確保 YouTube 訂閱**：獨立一步。`PushRecord` 已過期或不存在時，呼叫 `yt_push.add_push`，再用 `get_push` 確認並更新 `PushRecord`，回傳是否訂閱成功。`add_push`、`get_push` 拋例外（`APINetworkError`，或 hub 回 404 時 `platforms.py:296-299` 的 AttributeError），都當成訂閱失敗：不更新 `PushRecord`，推播設定照常存入，前端依規格顯示提示。`add_push` 用 `hub.verify=async`，3 秒後 `has_verify` 為假常只是 hub 還沒驗證完，這時視為「已送出、待驗證」：不更新 `PushRecord`、不提示，跟現有指令一樣。
    - **移除推播**：帶 `original` 時用 `delete_notify_community_if`，影響 0 列就回報衝突；指令呼叫時不帶，用 `sqldb.remove_notify_community`。兩者都包含後續清理。
  - 這段邏輯目前寫在 `system_community.py` 的各 set／remove 指令裡。指令也改呼叫同一個服務，見〈決策紀錄〉第 1 題：指令的 set 依該筆是否已存在，分別呼叫「新增推播」或「修改推播」，remove 呼叫「移除推播」。
  - 端點：
    - `POST /dashboard/guilds/{id}/community-notifies/resolve`：body 是 `{platform, input}`，回傳找到的帳號。解析結果存在伺服器的記憶體快取 10 分鐘，key 是平台 × 帳號 ID。
    - `POST /dashboard/guilds/{id}/community-notifies`：body 是 `{platform, account_id, notify_types[], values}`。帳號資料從 resolve 的快取取得，不信任前端傳來的名稱；快取過期時依 ID 重查平台：`tw_api.get_user_by_id`、`google_api.get_channel(channel_id=...)`、`cli_api.get_user_details(<id>)`。接著呼叫「新增推播」。有衝突時回 409，錯誤碼 `already_exists`，並列出已存在的種類，一筆都不寫入。前端收到時：只勾了一種，比照 T-06 顯示衝突提示，按「以我的內容覆蓋」改走 PUT 修改；勾了多種，就標出已存在的種類，表單內容保留。按新增前一覽上已經有的，比照 T-06 直接打開那一筆的編輯。
    - `PUT /dashboard/guilds/{id}/community-notifies/{notify_type}/{account_id}`：帶 `original`，只接受頻道、身分組、自訂文字。寫入時呼叫「修改推播」，所以 YouTube 的推播訂閱過期時也會重新訂閱。
    - `DELETE /dashboard/guilds/{id}/community-notifies/{notify_type}/{account_id}`：帶 `original`，呼叫「移除推播」。
  - 驗證只檢查用得到的欄位。有效性判斷用 T-03 的函式，條件式寫入影響 0 列時，用 `populate_existing` 讀出目前的列（見共通規則〈讀到最新的資料〉），交給 T-04 的 `check_conflict` 組出 409 的內容。
- 前端：
  - 在 `community-notify-section.tsx` 加入新增流程：選平台 → 輸入或貼上 → 按查詢 → 顯示找到的帳號 → Twitch 勾選種類 → 頻道、身分組、自訂文字 → 存檔。
  - 編輯表單、刪除確認、錯誤處理，與 T-06 一致。
  - 新增流程與編輯表單都用 T-04 的 `registerDraft` 註冊，`getState` 包含目前的步驟、已查到的帳號、勾選的種類與欄位值；頁面載入時用 `consumeDraft` 還原。
  - 衝突提示的 `onRecreate`：改打 POST，`notify_types` 只放這一種。
  - YouTube 的新增與修改要等推播訂閱完成，最壞約 70 秒：`add_push` 最多 3 次、每次 timeout 15 秒，中間 sleep 2 與 4 秒，再加 3 秒等待與 `get_push` 的 15 秒。存檔按鈕顯示處理中並停用，這個請求的 fetch timeout 設 90 秒。

**依賴**：T-04（選單、衝突、表單暫存）、T-05（預覽）

**風險 / 實作注意**
- Twitter 的查詢 API 次數很少，查詢只在按下查詢按鈕時送出，不隨輸入即時查詢。
- 指令改呼叫設定服務後，要手動測一次 `/twitch set`、`/youtube set`、`/twitter set` 與對應的 remove，確認行為不變。

**進度**：未完成

### T-08 管理員能發送測試通知

**使用者價值**：管理員設定完能馬上確認 bot 真的發得出去、內容長什麼樣子。

**範圍**
- 包含：
  - 一覽每筆旁邊的測試按鈕，用已存的設定發送。
  - 不 tag 身分組，訊息標明是測試。
  - 1 分鐘共用冷卻；失敗顯示原因，而且不計入冷卻。
- 不包含：定時通知的測試。依規格，定時通知不提供測試。

**驗收條件**
- [ ] 一覽中除了天氣預報、Apex 輪替，每筆都有測試按鈕。
- [ ] 按下後，bot 在該筆設定的頻道發出一則標明測試的訊息，內容與預覽規則相同，用的是已存的設定；`{member}` 代入按下的人。
- [ ] 測試訊息顯示會 tag 的身分組，但不實際通知該身分組的成員。
- [ ] A 發送後，B 在 1 分鐘內對同一筆的按鈕無法使用，並顯示剩餘時間。
- [ ] 移除 bot 在該頻道的發訊息權限後發送測試，看到失敗原因，而且可以立刻再按一次。
- [ ] 直接呼叫 API 在冷卻中發送，請求被拒絕。
- [ ] 按測試時 bot 已不在伺服器，看到 bot 已不在的提示並回到清單。

**實作設計**
- 後端：
  - `POST /dashboard/guilds/{id}/notifies/test`：body 是 `{kind: channel|community, notify_type, account_id?}`。
    - 從資料庫讀出已存的設定，用 T-05 的 `build_sample` 產生內容，帶入按下者的 member。在 bot loop 上先 `guild.get_member`，拿不到再 `await guild.fetch_member(user_id)`；仍然失敗就不傳 `member`，`{member}` 改用範例成員。
    - 經 `sclient.bot.submit` 發送。訊息加上測試標示，並用 `AllowedMentions.none()`，身分組與 `{member}` 代入的本人都不會被通知。
    - 定時通知回 400，錯誤碼 `scheduled_not_testable`。
  - 冷卻存在記憶體，key 是 guild × 種類鍵 × 帳號：
    - 發送前先寫入「發送中」佔位，同時按下的第二個請求會看到佔位而回 429。
    - 發送成功後，佔位改成成功時間；失敗就移除佔位，所以不計入冷卻。
    - 冷卻中回 429，錯誤碼 `cooldown`，附上剩餘秒數。發送失敗回 502，錯誤碼 `send_failed`。
  - T-03 的一覽 API 每筆加上剩餘冷卻秒數，讓按鈕一載入就是正確狀態。
- 前端：
  - 在兩個區塊元件的每筆加上測試按鈕，含冷卻倒數與失敗提示。
  - 錯誤處理用 T-01 的 fetch wrapper。

**依賴**：T-06、T-07（測試按鈕要加在這兩張卡擴充過的區塊元件上）。T-05 的範例內容經由它們間接滿足。

**進度**：未完成

### T-09 管理員能從清單邀請 bot 並回到後台

**使用者價值**：還沒用星羽的伺服器管理員，能在後台直接邀請 bot 並開始設定，這是規格要解決的第二個問題。

**範圍**
- 包含：
  - 從「未邀請」發起邀請並預選伺服器。
  - 完成後依權限導向通知頁或清單；改選了別的伺服器，以實際加入的為準；取消回清單。
  - 邀請完成時立即刷新清單。
- 不包含：清單本身（T-02）。

**驗收條件**
- [x] 從「未邀請」的伺服器點邀請，Discord 邀請頁已預選該伺服器。
- [x] 有 Manage Server 與 Manage Channels 的帳號完成邀請後，直接進入該伺服器的通知頁。
- [x] 只有 Manage Server 的帳號完成邀請後，回到清單並看到需要 Manage Channels 的提示。
- [x] 在邀請頁改選別的伺服器並完成，以實際加入的那個伺服器套用上面兩條規則。
- [x] 在邀請頁取消，回到伺服器清單。
- [x] 邀請完成後的清單，該伺服器已在「已邀請」。
- [x] 在 Discord 邀請頁登入的是另一個帳號時，後台改以該帳號登入，回到清單，而且清單正常顯示。
- [x] 重新邀請先前被踢出的伺服器後，原本的通知設定都還在。
- [x] 未登入時打開 `/to/dashboard-invite`，先導向登入，完成後回到伺服器清單。
- [x] 360px 寬時邀請流程可以完成。

**實作設計**
- 後端：
  - `GET /to/dashboard-invite?guild_id=<id>&origin=<前端 origin>`：
    - `origin` 的驗證規則同 T-01 的 `/to/dashboard-login`。
    - 需要 session。沒有 session 時，導向 `/to/dashboard-login?next=/dashboard&origin=<origin>`。
    - 產生 state，寫入 T-01 的 `dashboard_oauth`：`{state, purpose: invite, next: /dashboard, origin}`。
    - `guild_id` 是選填；沒帶時不帶預選參數。
    - 導向 Discord 授權：有 `guild_id` 時帶 `guild_id` 與 `disable_guild_select=false`；權限沿用現有的 `permissions=8`；scope 為 `bot identify guilds`。
  - `/oauth/discord` 的 `purpose=invite` 分支：在 `invite.py` 用 T-01 的 `register_oauth_purpose("invite", handler)` 註冊。以下導回的路徑都接在 cookie 的 `origin` 後面：
    - **取消**（帶 `error`）：導回 `/dashboard`。
    - **完成**：
      - 換 token、`get_me()`，存該帳號的 token，呼叫 T-02 的 `invalidate`。state 已經在 T-01 的分流驗過。
      - callback 時已經沒有有效 session，例如另一台裝置登出：以 `get_me()` 的帳號建立新 session。如果 cookie 裡的舊 session 屬於同一個帳號，或沒有舊 session，接著照「帳號相同」的流程導向；屬於不同帳號時才照下一條回清單。
      - 帳號跟 session 的帳號不同時，依換帳號規則處理：刪掉舊 session，建立該帳號的 session，導回 `/dashboard`。
      - 帳號相同時，等 bot 看到實際加入的 `guild_id`，最多重試 5 秒，重試間隔用 `await asyncio.sleep`，不阻塞事件迴圈。看到之後，依 `guild_perms` 決定導回 `/dashboard/guilds/<id>` 或 `/dashboard?notice=need_manage_channels`；5 秒仍看不到，導回 `/dashboard?notice=invite_pending`。這個「bot 尚未出現」的提示是規格外新增的去向，規格只有通知頁與清單兩種。
- 前端：
  - T-02 的「未邀請」項目與空清單的邀請入口，改連 `${NEXT_PUBLIC_BASE_API_URL}/to/dashboard-invite?guild_id=<id>&origin=<window.location.origin>`；空清單沒有指定伺服器時，不帶 `guild_id`。
  - 清單頁讀 `notice` 參數顯示提示。

**依賴**：T-02（`guild_perms`、`invalidate`、清單頁）。導向的通知頁在 T-03 完成前是 T-01 的佔位頁，不影響驗收。

**進度**：完成（2026-11-08），已部署並在正式環境驗收
- commit：XingyuBot `f4a878a`，domalyze_frontend `979cb30`，已 push 並部署。
- 實作時的取捨：`session.py` 新增唯讀的 `lookup_session`（不續期、不刪除），邀請入口與 callback 判斷舊 session 時用；其餘檔案只動 `invite.py`。授權用 `bot identify guilds` scope，token 照 T-01 的登入流程存進 `OAuthToken`，所以從清單邀請的管理員不會被要求重新授權。等 bot 出現的上限與間隔是 `invite.WAIT_SECONDS`、`POLL_INTERVAL`。前端的邀請連結改為整頁導向（不開新分頁），完成後回到後台；清單頁讀 `?notice=` 顯示一次後從網址移除。官網首頁的邀請按鈕沿用 `NEXT_PUBLIC_BOT_INVITE_URL`，不受影響。
- 正式環境驗收：Discord 邀請頁預選伺服器、改選別的伺服器、取消、換帳號、重新邀請被踢出的伺服器、360px 寬，都要在部署後實測。

## 決策紀錄

1. **現有指令改呼叫同一個設定服務**：T-07 把社群推播的設定邏輯抽到 starlib，網頁與 `/twitch`、`/youtube`、`/twitter` 的 set／remove 共用。接受的代價：要動到線上指令，T-07 完成時手動測一次指令。
2. **修改與刪除用條件式寫入**：`UPDATE`／`DELETE` 的 WHERE 帶原始值，影響 0 列就回 409，不改表、不自己控制交易。其他做法是接受毫秒等級的空窗，或用 `SELECT ... FOR UPDATE`。接受的代價：T-06、T-07 各自另寫條件式的修改與刪除方法，並自己補上 VoiceLog 快取與刪除後的清理。
3. **官網首頁邀請 bot 時不存 token**：帶 `guild_id` 的 bot 授權不再寫入 `OAuthToken`。其他做法是舊 token 失效時登出後台，或讓官網首頁的邀請也帶 `guilds` scope。接受的代價：如果實測發現 Discord 發新 token 會讓舊 token 失效，用官網首頁邀請 bot 的管理員，下次操作後台會看到「需要重新授權」。

## 後續追蹤

- 規格〈登入與 session〉第 3 點「已綁定析域、Discord 授權仍有效的使用者直接進入」等網站有析域登入後再做。`OAuthToken` 以 Discord user ID 為主鍵，屆時從析域綁定查到 Discord ID 即可沿用。
