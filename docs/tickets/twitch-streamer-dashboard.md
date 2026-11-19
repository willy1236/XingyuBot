# 實況主後台與 Twitch bot 開放接入（第一階段）任務拆解

規格書：[docs/spec/twitch-streamer-dashboard-spec.md](../spec/twitch-streamer-dashboard-spec.md)

## 現況與前提

- 技術棧：
  - 後端 XingyuBot：FastAPI web 服務跑在 Discord bot 的 process 裡（`API_WEBSITE`）。
  - Twitch bot 是另一個 process：`twitch_main.py` 加上 `starServer/twitch_chatbot.py`，用 twitchAPI 的 Chat 與 EventSubWebhook。
  - 兩個 process 經 Redis 通訊，契約見 `docs/messaging-contract.md`。
  - 資料庫是 PostgreSQL，透過 SQLModel 存取；前端 domalyze_frontend 用 Next.js。
- 共通規則沿用[伺服器管理後台的任務拆解](server-dashboard-polls.md)〈現況與前提〉：
  - DB 一律經 `db.run_db`；錯誤一律 `raise DashboardError`。
  - router 檔由 `starServer/dashboard/__init__.py` 自動掃描。
  - 沒有 migration 工具：改既有表要附 ALTER，部署時先手動執行，再部署 code。卡上寫的是欄位設計，實作時把實際的 ALTER SQL 寫回該卡的「進度」。
  - 測試：後端在 `tests/`（真實 PostgreSQL），前端是 `lib/*.test.ts`（vitest）。
- 既有相關機制：
  - **後台 session**（`starServer/dashboard/session.py`、`models.py` 的 `DashboardSession`）：
    - 身分一律是 `discord_user_id`（NOT NULL）。
    - `follow_account` 每 60 秒向 auth server 確認析域帳號。
    - `require_session` 是所有後台端點的 dependency，`access.require_section`、`personal.require_personal` 都建立在它上面。
    - `/dashboard/me` 回 Discord 的 id、名稱、頭像。
    - 前端 `app/dashboard/layout.tsx` 用 `me.id` 做換帳號偵測與草稿 key（`setDashboardUserId`、`createDraftHooks`）。
  - **Discord 登入**（`starServer/dashboard/auth.py`）：
    - `/to/dashboard-login` 寫 `dashboard_oauth` cookie（state、purpose、next、origin）。
    - callback 依 `purpose` 分派到 `register_oauth_purpose` 註冊的 handler。
    - 析域登入在 `domalyze_login.py`：OIDC，多個 Discord 時讓使用者選擇。
  - **析域帳號**（`starlib/identity/client.py` 的 `Account`）：
    - 帶 `twitch_passports`、`discord_passports`。
    - `starlib/identity/twitch.py` 的 `lookup_twitch_member` 用 Twitch ID 查域民。
  - **Twitch 授權**（`starServer/bot_website.py` 的 `/oauth/twitch`）：
    - 用 OAuth client `APIType.Twitch` #3，`TwitchOAuth.save_token_to_db` 把實況主 token 存進 `OAuthToken`。
    - 舊流程的起點是 `/to/twitchauth`（`bot_website.py` 約 355 行），自帶一份實況主 scope 清單。
    - `OAuth2Base.create_from_db`（`starlib/oauth/oauth_lib.py` 約 167 行）用 `scopes or default_scopes`，傳空 list 會退回 DB 的預設 scope。
    - 沒有任何地方會自動 refresh 實況主 token；Twitch user token 約 4 小時過期。
    - 要求是域民，新增 `TwitchBotJoinChannel`，完成頁提示手動 `/mod` 並等重啟。
    - client #3 與 bot 用的 #2 是同一個 Twitch 應用程式，只是兩筆設定。
  - **Twitch bot**（`starServer/twitch_chatbot.py`）：
    - 啟動時 `load_join_channels()` 讀全部 `TwitchBotJoinChannel`，用 bot 帳號 token（client #2）連 Chat、`join_room`。
    - 每個頻道訂閱 EventSub：開台、下播、Raid；bot 是 mod 時再訂閱追隨、兌換、訂閱、續訂、贈訂、預測結束。
    - 聊天室回應（開台、Raid、續訂、贈訂）只在 `action_channel_id` 有值時發送。
    - 事件經 bus 發給 Discord 端。
    - `chat.is_mod(room)` 是 USERSTATE 的快取，只在加入房間或 bot 自己發言時更新，拿掉 mod 後不會立即反映。
    - 自訂指令：`respond_to_chat_command` 查 `sqldb.get_twitch_cmd_response_cache`，全部指令共用 30 秒冷卻；`!add_cmd`、`!remove_cmd`、`!list_cmd` 只有實況主與 mod 能用。
    - 指令快取是 `DBCacheType.TwitchCmd`，在 `twitch_main.py` 的 `sqldb.init_cache()` 載入。
  - **跨 process 機制**（`starlib/messaging/`）：
    - 事件（Stream）。
    - 請求／回應：`rpc.py`，逾時寫死 5 秒（`REQUEST_TIMEOUT`），對方不在時得到 `RpcUnavailable`。
    - 快取失效：`cache_invalidation.py`，Pub/Sub。
  - **Discord 端轉發**（`starDiscord/cmds/twitch_notify.py`、`twitch_live_notify.py`）：
    - 依 `TwitchBotJoinChannel.action_channel_id` 發送（`resolve_action_channel`），設定改了立即生效。
    - 預測結果、私訊與下播通知（`twitch_live_notify.py` 約 68 行）固定發到 `DEFAULT_TWITCH_CHANNEL`。
    - 贈訂沒有事件。
  - **資料表**（`models.py`，schema `stardb_basic`）：
    - `TwitchBotJoinChannel`：twitch_id、action_channel_id、point_name。
    - `TwitchChatCommand`：PK 是 twitch_id 加 name，另有 response。
  - **伺服器權限**（`starServer/dashboard/guilds.py` 的 `guild_perms`）：GuildPerms 有 `manage_channels`。
  - **bot owner**：`await sclient.bot.is_owner(discord.Object(user_id))`，是 async。
  - **前端後台**：
    - `app/dashboard/layout.tsx`。
    - `components/dashboard/dashboard-header.tsx`：NAV 有「我的」「伺服器」。
    - 伺服器頁的區塊導覽：`lib/dashboard-sections.ts`、`components/dashboard/guild-nav.tsx`。
    - 字數元件：`components/dashboard/char-count.tsx` 的 `LabelWithCount`；有字數上限的欄位一律用它。
    - `lib/dashboard-api.ts` 在全域攔下 `no_permission`：先 alert 伺服器權限的訊息，再導到 `/dashboard/guilds`，呼叫端收不到這個錯誤。
    - `app/dashboard/page.tsx` 看到任何 `notice` 參數就轉到 `/dashboard/guilds`（`lib/dashboard-personal.ts` 的 `guildListRedirect`）。
  - **官網**：`app/page.tsx`、`app/features/page.tsx`、`lib/features-data.ts`。
- 這次會動到的既有部位：
  - XingyuBot：
    - `models.py`、`client.py`、`cache.py`
    - `starServer/dashboard/session.py`、`auth.py`、`domalyze_login.py`
    - `starServer/bot_website.py`
    - `starServer/twitch_chatbot.py`、`twitch_main.py`
    - `starDiscord/cmds/twitch_notify.py`、`twitch_live_notify.py`
    - `starlib/messaging/events/twitch_activity.py`、`docs/messaging-contract.md`
  - 新增：
    - XingyuBot：`starServer/twitch_bot/`、`starServer/dashboard/channel_*.py`、`starServer/dashboard/twitch_login.py`、`starlib/twitch_audit.py`、`starlib/twitch_tokens.py`
  - 另外會動到：`starlib/oauth/oauth_lib.py`、`starServer/dashboard/invite.py`、`tests/twitch/`
  - domalyze_frontend：
    - 既有：`app/dashboard/layout.tsx`、`app/dashboard/page.tsx`、`app/dashboard-login/`、`components/dashboard/dashboard-header.tsx`、`lib/dashboard-login.ts`、`lib/dashboard-api.ts`
    - 新增：`app/dashboard/channels/`、`components/dashboard/channel/`、`lib/dashboard-channel*.ts`
- 已定案的技術前提：
  - 後台 API 放在 XingyuBot 的 web 服務，前端放在 domalyze_frontend。
  - Twitch 登入與啟用都用 XingyuBot 自己的 Twitch 應用程式（client #3），不經 auth server。client #3 與 bot 用的 #2 是同一個應用程式。
  - web 和 Twitch bot 之間的即時同步，走既有的 RPC 與快取失效機制。
  - 自訂指令與計時訊息的變數：`{user}`、`{touser}`、`{args}`、`{count}`、`{channel}`、`{uptime}`、`{game}`、`{title}`。事件回應另有 `{months}`、`{amount}`、`{viewers}`。

## 實作順序總覽

| # | 卡號 | 進度 | 標題 | 依賴 | 並行組 | 備註 |
|---|---|---|---|---|---|---|
| 1 | W-00 | 未完成 | [共用] session 支援 Twitch 身分 | 無 | — | W-01、W-10 依賴 |
| 2 | W-01 | 未完成 | 實況主能用 Twitch 登入並進到自己的頻道後台 | W-00 | — | 骨架切片 |
| 3 | W-02 | 未完成 | [共用] Twitch bot 頻道控制：狀態、即時加入離開、模組拆分 | W-01 | — | W-03 之後都依賴 |
| 4 | W-03 | 未完成 | 實況主能啟用與停用 bot | W-02 | — | 含舊頻道、關閉舊入口 |
| 5 | W-04 | 未完成 | [共用] bot 發言管線與修改紀錄 | W-03 | — | W-05～W-07、W-12 依賴 |
| 6 | W-05 | 未完成 | 實況主能在後台管理自訂指令 | W-04 | A | |
| 7 | W-06 | 未完成 | 實況主能設定計時訊息 | W-04 | A | |
| 8 | W-07 | 未完成 | 實況主能設定事件回應 | W-04 | A | |
| 9 | W-08 | 未完成 | 實況主能看到權限問題並一鍵修復 | W-03 | B | |
| 10 | W-09 | 未完成 | 實況主能刪除頻道的所有資料 | W-04 | B | 要保留修改紀錄；表由 W-04 建好 |
| 11 | W-10 | 未完成 | 用析域登入能同時管理伺服器與頻道 | W-01 | B | |
| 12 | W-13 | 未完成 | 官網有 Twitch bot 介紹與接入入口 | W-05、W-06、W-07、W-11 | — | 純前端；只介紹已上線的功能 |
| 13 | W-11 | 未完成 | 實況主能把事件轉發到 Discord | W-10、W-07 | — | 與 W-07 都改事件模組 |
| 14 | W-12 | 未完成 | bot owner 能在營運入口管理頻道 | W-04、W-08 | — | 用 W-08 的狀態判定 |

並行組 A 的分工：

- W-02 先把 Twitch bot 拆成 `starServer/twitch_bot/commands.py`、`timers.py`、`events.py` 三個模組。
- W-01 先建好頻道頁的導覽，以及各區塊的空頁面。
- W-04 先建好三張卡要用的資料表、model 與 `sqldb` 存取函式（`models.py`、`client.py` 只在 W-04 改）。
- 之後 W-05、W-06、W-07 各自只改自己的 bot 模組、router 檔、頁面與元件。快取失效的 handler 由各自的 bot 模組在 `start()` 裡自己註冊，不改 `twitch_main.py`。
- 三張卡都會用到修改紀錄與發言管線，只透過 W-04 的介面呼叫，不改 W-04 的檔案。

並行組 B 的分工：

- W-01 把頻道頁的 layout 拆成 `channel-header.tsx`（頁首）與 `channel-access-guard.tsx`（載入與錯誤處理），layout 本身之後不再改。
- W-08 改頻道狀態的計算，以及 `channel-status.tsx`。
- W-09 改頻道的「設定」頁。
- W-10 改析域登入、個人區與 `channel-access-guard.tsx`。

## 任務卡

### W-00 [共用] session 支援 Twitch 身分

**使用者價值**：W-01（Twitch 登入）與 W-10（析域登入帶入 Twitch 頻道）都要在同一套 session 上加入 Twitch 身分。先統一 session 的形狀，兩張卡才不會各自改 `session.py`。伺服器後台的既有端點則維持「需要 Discord 身分」。

**範圍**
- 包含：
  - session 的身分改成 Discord 帳號或 Twitch 帳號至少一個。
  - 新的 dependency：
    - `require_session`：維持需要 Discord，伺服器與個人區的既有端點不必改。
    - `require_any_session`：只要求已登入，給 `/me`、`/logout` 與頻道端點用。
  - `/dashboard/me` 的新形狀，以及前端 `DashboardUser` 跟著調整。
- 不包含：
  - Twitch 登入入口（W-01）。
  - 析域登入帶入 Twitch 頻道（W-10）。

**驗收條件**
- [ ] 既有的 Discord 登入、析域登入，以及伺服器管理後台所有自動測試照常通過，行為不變。
- [ ] 只有 Twitch 身分的 session 呼叫伺服器或個人區端點，得到 403 `discord_required`，不是 500。
- [ ] 只有 Twitch 身分的 session 呼叫 `/dashboard/me`，得到 Twitch 的名稱與頭像，`discord` 為 null。
- [ ] 登出時，與這個 session 同一個登入身分的所有 session 一起失效：Twitch 登入以 Twitch 帳號為單位，Discord 與析域登入以 Discord 帳號為單位。

**實作設計**
- 資料：`dashboard_session` 有以下異動，ALTER 附在 commit 說明裡：
  - `discord_user_id` 改為可為 null。
  - 新增 `twitch_user_id`（String，可為 null，加 index）、`twitch_login`、`twitch_name`、`twitch_avatar`。
  - 新增 `login_method`（String，值是 `discord`、`domalyze`、`twitch`）。
    - 既有資料：`via_domalyze` 為 true 的設成 `domalyze`，其餘設成 `discord`。
    - `via_domalyze` 保留不刪，由 `login_method` 推出，避免改到析域登入的既有判斷。
  - 加 CHECK：`discord_user_id` 與 `twitch_user_id` 至少一個不為 null，或者 `login_method = 'domalyze'` 且 `account_id` 不為 null（W-10 的「析域帳號沒有連結 Discord」session）。
- 後端：改 `starServer/dashboard/session.py`。
  - `SessionInfo`：
    - `discord_user_id: str | None`。
    - 新增 `login_method`、`twitch: TwitchIdentity | None`（id、login、name、avatar）。
    - 新增 `twitch_channels: tuple[TwitchIdentity, ...]`：這個 session 可以管理的頻道。Twitch 登入時只有自己；析域登入在 W-10 補上。
  - 函式拆分：
    - 原本的 `require_session` 改名為 `require_any_session`。
    - 新的 `require_session` 呼叫它，`discord_user_id` 為 None 時 `raise DashboardError(403, "discord_required")`。
    - 用 `require_session` 的既有 15 個模組都不用改。
    - `invite.py` 用 `lookup_session` 直接取 `discord_user_id`（約 71–77 行），要補上：值為 None 時導回 `/dashboard`。
  - `create_session` 增加 Twitch 身分參數。
  - 新增 `delete_twitch_user_sessions(twitch_user_id)`。
  - `follow_account`：`login_method == "twitch"` 的 session 不向 auth server 確認，直接回傳。規格〈細部規則〉2：Twitch 登入不附帶析域帳號。判斷一律看 `login_method`，不看身分欄位，W-10 的無 Discord 析域 session 才不會被誤判。
  - `_record_activity` 只在有 Discord 身分時記錄。
  - 改 `auth.py`：
    - `/dashboard/me` 改用 `require_any_session`，回傳 `{id, name, avatar_url, discord: {id} | null, twitch: {id, login} | null, account, login_method}`。
    - `id` 是這個 session 的主身分 key：有 Discord 時是 Discord ID，否則是 `twitch:<twitch_id>`。
    - `/dashboard/logout` 改用 `require_any_session`，依 `login_method` 呼叫 `delete_user_sessions` 或 `delete_twitch_user_sessions`。
- 前端：
  - `components/dashboard/dashboard-header.tsx` 的 `DashboardUser` 加上新欄位。
  - NAV 的「伺服器」只在 `discord` 不為 null 時顯示。
  - `lib/dashboard-api.ts` 遇到 `discord_required` 時導到 `/dashboard`，不顯示錯誤。
  - `me.id` 的既有用途（換帳號偵測、草稿 key）沿用主身分 key，不必改。
  - `app/dashboard/layout.tsx` 把 `me` 放進新的 `DashboardUserContext`（`lib/dashboard-user.tsx`），讓頁面在發請求前就知道登入身分。
- 介面：
  - `require_any_session(request) -> SessionInfo`：未登入時 401 `session_expired`。
  - `require_session(request) -> SessionInfo`：保證 `discord_user_id` 不為 None，否則 403 `discord_required`。
  - `SessionInfo.twitch_channels`：頻道端點只用這個判斷可不可以管理某頻道，不自己查。

**依賴**：無

**風險 / 實作注意**
- 主身分 key 的規則：有 Discord 時是 Discord ID；Twitch 登入是 `twitch:<twitch_id>`；W-10 的無 Discord 析域 session 是 `domalyze:<account_id>`。
- `domalyze_login._start_session`、`auth._handle_login` 呼叫 `create_session` 的地方要補 `login_method`。
- `_check` 與 `_fallback` 假設 `discord_user_id` 不為 None，要在 Twitch-only 的分支前先返回。

**進度**：實作完成（2026-11-19），待審查
- commit：後端 41777f3；前端（domalyze_frontend）bf3adbb
- 實作時的決定：
  - 型別：新增 `DiscordSessionInfo(SessionInfo)`，`require_session` 回傳它；14 個模組的 `info: SessionInfo` 標註改成 `DiscordSessionInfo`（只改型別標註與 import，邏輯不變），pyright 才不會對 `int(info.discord_user_id)` 報錯。`follow_account` 改成泛型，保留傳入的型別。
  - `create_session` 自己推導 `login_method`（帶 `twitch` 是 `twitch`、`via_domalyze` 是 `domalyze`、其餘 `discord`），呼叫端不傳；`domalyze_login._start_session`、`auth._handle_login` 因此不必補。身分組合不合法時 `ValueError`。
  - `SessionInfo.identity_key` 實作三種主身分 key；`/dashboard/me` 的 `id` 用它。
  - 登出：`login_method == "twitch"` 刪同一 Twitch 帳號的 session，其餘刪同一 Discord 帳號的 session；沒有 Discord 的析域 session 尚未處理（W-10）。
  - `invite.py`：沒有 Discord 身分時導回 `/dashboard`。
- ALTER（已套到本機 DB；正式機先手動執行，再部署 code）：
  ```sql
  BEGIN;
  ALTER TABLE credentials.dashboard_session
      ALTER COLUMN discord_user_id DROP NOT NULL,
      ADD COLUMN twitch_user_id varchar,
      ADD COLUMN twitch_login   varchar,
      ADD COLUMN twitch_name    varchar,
      ADD COLUMN twitch_avatar  varchar,
      ADD COLUMN login_method   varchar NOT NULL DEFAULT 'discord';
  UPDATE credentials.dashboard_session SET login_method = 'domalyze' WHERE via_domalyze;
  ALTER TABLE credentials.dashboard_session
      ADD CONSTRAINT ck_dashboard_session_identity CHECK (
          discord_user_id IS NOT NULL
          OR twitch_user_id IS NOT NULL
          OR (login_method = 'domalyze' AND account_id IS NOT NULL)
      );
  CREATE INDEX ix_dashboard_session_twitch_user_id ON credentials.dashboard_session (twitch_user_id);
  COMMIT;
  ```
- 前端：`DashboardUser` 移到 `lib/dashboard-user.tsx`（`dashboard-header.tsx` 再匯出同名型別）；導覽由 `dashboardNav(user)` 決定；`discord_required` 導向由 `discordRequiredTarget(pathname)` 判斷，已在 `/dashboard` 時不導，呼叫端收到一般錯誤。
- 未驗：待人工驗證——Discord 登入、析域登入後後台照常；Twitch session 要等 W-01 的登入入口才建得出來，目前只有自動測試覆蓋。

### W-01 實況主能用 Twitch 登入並進到自己的頻道後台

**使用者價值**：實況主不需要析域帳號或 Discord，用 Twitch 登入就能進到自己頻道的後台。這是第一次端到端跑通「Twitch 身分 → session → 頻道頁」。

**範圍**
- 包含：
  - 登入頁新增「用 Twitch 登入」。
  - 頻道清單頁 `/dashboard/channels`：只有一個頻道時直接導過去；沒有頻道時，顯示「還沒有頻道」與 Twitch 登入的連結。
  - Twitch 授權回來後建立 session，落地頁是自己的頻道後台。
  - 頻道後台的頁框：頁首有頻道名稱、頭像與 bot 狀態；左側是區塊導覽。
  - 各區塊先放「尚未開放」的空頁面，讓 W-05～W-09 各自替換。
  - 只用 Twitch 登入時，轉發 Discord 區塊顯示「需要析域帳號」，並附上引導。
  - 第一次登入時建立頻道資料列，狀態為未啟用，讓營運入口看得到。
- 不包含：
  - 啟用 bot（W-03）。
  - 狀態的完整判定（W-08）。這張卡只顯示「未啟用」或「已啟用」。

**驗收條件**
- [ ] 未登入時打開 `/dashboard/channels/<id>`，被導到登入頁；按「用 Twitch 登入」完成授權後，回到該頁。
- [ ] 從登入頁直接用 Twitch 登入，落在自己的頻道後台；頁首顯示頻道名稱、頭像，以及「bot 未啟用」。
- [ ] 在 Twitch 授權頁按取消，回到登入頁，沒有登入。
- [ ] 只用 Twitch 登入時，頁首沒有「伺服器」；打開 `/dashboard/guilds`，被導回 `/dashboard`。
- [ ] 打開別人頻道的 `/dashboard/channels/<id>`，看到「沒有這個頻道的權限」；API 回 403 `channel_forbidden`。
- [ ] 轉發 Discord 區塊顯示「需要析域帳號」，並附上 auth server 帳號頁的連結。
- [ ] 360px 寬的畫面能完整操作。

**實作設計**
- 資料：`twitch_bot_join_channel` 有以下異動：
  - 新增 `state`（String，NOT NULL，預設 `inactive`，值是 `inactive`、`enabled`、`disabled`）。
  - 新增 `login`、`display_name`、`avatar_url`，在登入與啟用時更新，給營運入口顯示用。
  - 新增 `first_seen_at`。
  - 既有資料一律設為 `inactive`（規格：舊頻道要重新啟用）。
  - ALTER 附在 commit 說明裡。
- 後端：
  - 新增 `starServer/dashboard/twitch_login.py`。
  - `GET /to/dashboard-twitch-login?next=&origin=`：
    - 用 `TwitchOAuth.create_from_db(client #3, scopes=[])` 產生授權網址，scope 為空，只識別身分。
    - `oauth_lib.py` 的 `create_from_db` 改成 `scopes if scopes is not None else default_scopes`，空 list 才不會退回 DB 的預設 scope。改之前確認其他呼叫端沒有依賴「傳空 list 等於預設」。
    - 寫 `dashboard_twitch_oauth` cookie，格式比照 `auth.OAuthCookie`，`purpose` 為 `login`。
  - 改 `bot_website.py` 的 `/oauth/twitch`：
    - 開頭先呼叫 `handle_dashboard_twitch_oauth(request)`，有後台 cookie 且 state 相符時，依 `purpose` 分派。分派表比照 `auth.register_oauth_purpose`，W-03 再註冊 `enable`。
    - 回 None 才走原本的流程。原本流程由 W-03 改掉。
  - `login` handler：
    - `exchange_code` 加 `get_me`，`create_session(login_method="twitch", twitch=...)`。
    - 若 `TwitchBotJoinChannel` 沒有這個頻道，新增一列 `inactive`；有的話更新 login、名稱、頭像。
    - `next` 是 `/dashboard` 時改成 `/dashboard/channels/<twitch_id>`。
    - 取消或失敗時回到 `{origin}/dashboard-login`。
  - 新增 `starServer/dashboard/channels.py`：
    - `require_channel(twitch_id)` dependency：用 `require_any_session`，`twitch_id` 不在 `info.twitch_channels` 時回 403 `channel_forbidden`。不用 `no_permission`，因為前端在全域把它當成伺服器權限處理。之後所有頻道端點都用它。
    - `GET /dashboard/channels`：列出 session 可以管理的頻道，每筆有 id、login、名稱、頭像、state。
    - `GET /dashboard/channels/{twitch_id}`：頻道基本資料加 state，以及 `forward_access`：`ok`（析域登入且有 Discord）、`need_domalyze`（不是析域登入）、`need_discord`（析域登入但沒有 Discord）。W-11 的 `editable` 用同一個判斷。
- 前端：
  - `lib/dashboard-login.ts`：`LoginProvider` 加上 `twitch`，`providerLoginUrl` 對應到 `/to/dashboard-twitch-login`。
  - `app/dashboard-login/page.tsx` 加一顆按鈕。
  - 新增：
    - `app/dashboard/channels/[id]/layout.tsx`：結構比照 `app/dashboard/guilds/[id]/layout.tsx`，只組合下面兩個元件與導覽，之後的卡不再改它。
    - `components/dashboard/channel/channel-header.tsx`：頭像、名稱，以及 `channel-status.tsx`（這張卡只顯示 state，W-03、W-08 擴充）。
    - `components/dashboard/channel/channel-access-guard.tsx`：載入頻道資料；收到 `channel_forbidden` 時顯示「沒有這個頻道的權限」。W-10 擴充。
    - `app/dashboard/channels/[id]/page.tsx`：頻道總覽，這張卡先放狀態說明，W-04 加上擋下紀錄。
    - `app/dashboard/channels/page.tsx`：頻道清單頁。
    - `lib/dashboard-channel-sections.ts`：`CHANNEL_NAV`，包含指令、計時訊息、事件回應、轉發 Discord、設定。
    - `components/dashboard/channel/channel-nav.tsx`。
    - 各區塊的空頁面：`app/dashboard/channels/[id]/commands/page.tsx`、`timers/`、`events/`、`forward/`、`settings/`，內容都是「尚未開放」。
  - 轉發 Discord 頁依 `forward_access` 顯示「需要析域帳號」或「需要連結 Discord」的說明。
  - Twitch 登入時，`app/dashboard/page.tsx` 從 `DashboardUserContext` 判斷 `login_method`，不發 overview 請求，直接 `router.replace("/dashboard/channels")`。規格〈細部規則〉6。
  - 頁首 NAV 加「頻道」，href 是 `/dashboard/channels`。`/dashboard/me` 回傳 `has_channels`，為 true 時顯示。
  - `lib/dashboard-api.ts`：`channel_forbidden` 不做全域處理，交給呼叫端。

**依賴**：W-00（session 的 Twitch 身分、`require_any_session`）

**風險 / 實作注意**
- client #3 在 DB 的 `callback_uri` 就是 `/oauth/twitch`。沿用同一個 callback、靠 cookie 分派，不必到 Twitch 後台新增 redirect URI。
- 空 scope 的 user token 也能呼叫 Helix `/users` 取得自己的資料。

**進度**：實作完成（2026-11-19），待審查；驗收條件未打勾，待人工驗證與審查後再勾
- commit：後端 482e9e3、395ac7c、ced5464、4653ef7、759cf5a、fc441ea；前端（domalyze_frontend）ea18333、a262f40
- 實作時的決定：
  - 登入 handler 只做 `exchange_code` 與 `get_me`，**不存 token**：沒有 scope 的 token 會蓋掉同一筆 `OAuthToken` 裡已啟用頻道的完整 token，有測試鎖住。
  - Twitch 登入的 session 用 W-00 的 `create_session(None, name, avatar, replace_session_id, twitch=TwitchIdentity(...))`，`login_method` 由它推導；`TwitchIdentity.id` 是 str，`require_channel` 以 `str(twitch_id)` 比對。
  - `starServer/dashboard/config.py` 新增 `TWITCH_OAUTH_SEQ = 3`；`twitch_login.py` 自己懶載入 client #3，不能 import `bot_website`（循環）。
  - `auth.encode_cookie`／`decode_cookie` 改公開名稱（純改名，`invite.py` 同步）。
  - `/oauth/twitch` 開頭先 `handle_dashboard_twitch_oauth`，沒有 cookie 或 state 不符才走原流程（搬到 `_oauth_twitch_fallback`，內容不變）；有 cookie 但 state 不符時一併清掉。
  - `/dashboard/me` 補 `has_channels`（`len(info.twitch_channels) > 0`），前端 `DashboardUser` 與 `dashboardNav` 同步。
  - 頻道頁的名稱與頭像取自 session 的 Twitch 身分；DB 沒有頻道列時 `state` 視為 `inactive`，GET 不建列。頻道資料由 `ChannelAccessGuard` 載入並放進 context（`useChannel()`）。
  - `lib/dashboard-api.ts` 不需改：`channel_forbidden` 本來就落在 `default` 分支，交給呼叫端處理。
  - 側欄多一項「總覽」（頻道頁本身），卡上的 `CHANNEL_NAV` 沒列。
  - 已登入的人從「還沒有頻道」頁按 Twitch 登入，session 會被取代（不疊加帳號），頁面文案有提醒。
- ALTER（已套到本機 DB；正式機先手動執行，再部署 code）：
  ```sql
  ALTER TABLE stardb_basic.twitch_bot_join_channel
      ADD COLUMN state varchar NOT NULL DEFAULT 'inactive',
      ADD COLUMN login varchar,
      ADD COLUMN display_name varchar,
      ADD COLUMN avatar_url varchar,
      ADD COLUMN first_seen_at timestamptz(0);
  ```
  既有列因 `DEFAULT` 成為 `inactive`；`first_seen_at` 可為 null，既有列不補值，只在新增頻道列時填入。
- 未驗：
  - 真實 Twitch 授權：空 scope 時授權網址不帶 `scope` 參數，Twitch 文件把 `scope` 列為必填，是否接受要用 client #3 真的授權一次。失敗時改用最小實際 scope 或明確帶空 `scope=`，由使用者決定。
  - 360px 與桌面寬度的畫面操作、頻道清單頁多筆情形（W-10 之後才會出現）。
  - 部署：W-01 與 W-02 同一次上線；W-02 之前 Twitch bot 啟動仍載入全部頻道列。

### W-02 [共用] Twitch bot 頻道控制：狀態、即時加入離開、模組拆分

**使用者價值**：W-03 之後的卡都需要「改了設定，Twitch bot 立即知道」，現在要重啟才生效。這張卡讓 web 能叫 Twitch bot 加入或離開某頻道、重載某頻道的設定。也把 `twitch_chatbot.py` 拆成指令、計時、事件三個模組，讓並行組 A 不會改到同一個檔案。

**範圍**
- 包含：
  - Twitch bot 啟動時只載入 `state = enabled` 的頻道。
  - RPC handler：同步單一頻道（加入或離開聊天室、訂閱或取消 EventSub）、查詢頻道狀態。
  - mod 狀態一律用 Helix Get Moderators 查（實況主 token），不用 Chat 的 `is_mod` 快取。
  - 快取失效：頻道設定、自訂指令、計時訊息、事件回應各有一個快取名稱，以 twitch_id 為 key。
  - 把 `twitch_chatbot.py` 的聊天室指令與事件處理，原樣搬到 `starServer/twitch_bot/` 底下，行為不變。
- 不包含：
  - 啟用流程（W-03）。
  - 各功能的新行為（W-05～W-07）。

**驗收條件**
- [ ] 把某頻道的 state 改成 enabled，web 呼叫同步後，不必重啟 Twitch bot，bot 就加入該聊天室並訂閱該頻道的事件。
- [ ] 改成 disabled 再同步，bot 離開聊天室，該頻道的 EventSub 訂閱被取消。
- [ ] Twitch bot 沒在跑時，web 呼叫同步得到明確的「bot 離線」結果，不會卡住；bot 下次啟動時照 DB 的 state 加入。
- [ ] 搬模組後，既有 `tests/twitch` 全部通過，聊天室指令與事件行為不變。測試裡替換模組全域（`chat`、`twitch`、bus）的目標可以跟著改成新模組，斷言不改。

**實作設計**
- 資料：無新表。`TwitchBotJoinChannel.state` 由 W-01 新增。
- 後端（Twitch bot 端）：
  - 新增 `starServer/twitch_bot/`：
    - `channels.py`：已加入的頻道與 EventSub 訂閱的狀態表，以及 `sync_channel(twitch_id)`、`channel_status(twitch_id)`。
    - `commands.py`：搬入 `add_chat_command`、`remove_chat_command`、`list_chat_command`、`respond_to_chat_command`。
    - `events.py`：搬入 `on_follow` 到 `on_channel_prediction_end` 的 EventSub handler。
    - `timers.py`：空模組，W-06 實作。
      - 先提供空函式：`start(chat)`、`stop()`、`on_stream_online(twitch_id)`、`on_stream_offline(twitch_id)`、`on_chat_message(twitch_id, is_bot)`。
      - `events.py` 的開台與下播 handler、`commands.py` 的 on_message 在這張卡就先呼叫它們，W-06 只改 `timers.py`。
  - `twitch_chatbot.py` 只留下 `run()`、`TwitchBotThread` 與註冊。`run()` 改用 `load_join_channels()`，只載入 enabled 的頻道。
  - 原本 `run()` 裡每個頻道的 `_listen` 迴圈，抽成 `channels.subscribe_channel(user)`，啟動時和 `sync_channel` 共用。
  - 取消訂閱時，記住每個頻道的 subscription id。
  - 在 `twitch_main.py` 的 bus 啟動後，註冊以下 RPC handler（service 名稱是 `twitch`）：
    - `channel.sync {twitch_id}`：在 5 秒內同步完成加入或離開聊天室，回傳 `{accepted: true, joined: bool}`。EventSub 的訂閱與取消排進背景佇列，完成情況由 `channel.status` 回報。
    - `channel.status {twitch_id}` 回傳 `{joined: bool, subscriptions: {ok: [str], failed: [str], pending: bool}}`。
    - sync 是 idempotent 的：對已加入的頻道再呼叫一次，會依當下的 mod 狀態（Helix Get Moderators）補訂或退訂需要 mod 的事件。W-03 啟用、W-08 修復都靠這點。
  - 快取失效名稱：`twitch_channel`、`twitch_cmd`、`twitch_timer`、`twitch_event_response`，key 是 twitch_id 字串。Twitch bot 收到後重讀該頻道的資料。
- 後端（web 端）：新增 `starServer/dashboard/twitch_control.py`，給後台端點呼叫：
  - `async def sync_channel(twitch_id: int) -> SyncResult | BotOffline`：包 RPC；遇到 `RpcUnavailable` 回 `BotOffline`，不 raise。`SyncResult` 是 `{joined}`，代表聊天室已處理；訂閱結果不在這裡。
  - `async def channel_status(twitch_id: int) -> ChannelStatus | BotOffline`：`ChannelStatus` 是 `{joined, subscriptions}`。
  - `def invalidate(cache: Literal["twitch_channel","twitch_cmd","twitch_timer","twitch_event_response"], twitch_id: int) -> None`。
- 後端（兩邊共用）：新增 `starlib/twitch_tokens.py`。
  - `async def broadcaster_token(twitch_id: int) -> str | TokenInvalid`：從 `OAuthToken`（client #3）讀實況主 token；過期前 10 分鐘內就用 refresh token 換新並寫回 DB。refresh 失敗或沒有 token 時回 `TokenInvalid`，不 raise。
  - 同一頻道同時有多個呼叫時只 refresh 一次。
  - Twitch bot 端與 web 端都只透過它取 token，W-03、W-04、W-08 共用。
- `docs/messaging-contract.md`：補上 `twitch` 服務的 RPC 方法與快取名稱。
- 介面：上面三個 web 端函式、`twitch_tokens.broadcaster_token`，以及 Twitch bot 端的 `channels.sync_channel`。
  - Twitch bot 端的 invariant：同一頻道的 sync 依序執行，不並行。
  - `channel.status` 不打 Twitch API，只回報已加入的房間與背景訂閱的結果。mod 狀態由 W-08 在 web 端用 Helix 查。

**依賴**：W-01（`state` 欄位）

**風險 / 實作注意**
- 訂閱放背景，是因為 EventSub 每次訂閱後的 `asyncio.sleep(1)` 會讓 sync 超過 RPC 寫死的 5 秒逾時，這樣就不必改 `rpc.py`。
- Helix Get Moderators 要用實況主 token（`moderation:read`），一律經這張卡新增的 `starlib/twitch_tokens.py` 取得。
- twitchAPI 的 `chat.join_room` 與 `leave_room` 必須在 Chat 的 event loop 上呼叫。

**進度**：進行中（2026-11-19）
- 已定案：Twitch bot 各模組共用的 `chat`、`twitch`、`join_channels`、`eventsub`、`bot_user_id` 放 `starServer/twitch_bot/state.py`（避免 `channels` 與 `events` 循環 import）；聊天室 IRC 事件（`on_sub`、`on_whisper` 等）併入 `events.py`；`on_message` 在 `commands.py`；既有測試只改 patch 目標。訂閱記在 `channels.subscriptions`，`subscribe_channel` 是「讓訂閱符合目前 mod 狀態」的可重複呼叫函式，啟動與 sync 共用。
- 已定案（timers 介面）：`timers`、`commands`、`events` 各有同步的 `start()`／`stop()`（`timers.start(chat)`），由 `run()` 在 chat 啟動後、`cleanup` 時呼叫；`timers.on_stream_online`、`on_stream_offline`、`on_chat_message` 是 async。`on_stream_online` 在確認有直播後才呼叫，`on_stream_offline` 一進來就呼叫；`is_bot` 以 `msg.user.name` 對 `chat.username`（不分大小寫）判斷。
- commit：（1）純搬移 `twitch_bot/{state,events,commands}.py`；（2）`channels.subscribe_channel` 與訂閱 id 記錄；（3）`timers.py` 空介面與 `start()`／`stop()` 接線；（4）`starlib/twitch_tokens.py`
- 已定案（twitch_tokens）：續期用 `SELECT … FOR UPDATE` 鎖那筆 `OAuthToken`、拿到鎖後重查 `expires_at`（使用者決定 Q1）；`TokenInvalid` 帶 `reason`（`missing`、`revoked`、`unavailable`）；Twitch 暫時連不上且舊 token 尚未過期時繼續用舊 token，只有過期才回 `unavailable`。
- 續做：`twitch_control.py`；契約文件；等 W-01 合入後做 enabled 載入、`on_ready` 改用目前清單、`sync_channel`／`channel_status`、RPC 註冊

### W-03 實況主能啟用與停用 bot

**使用者價值**：外部實況主不需要任何人手動處理，按一下就能讓 bot 在自己頻道運作，也能隨時停用。這是「能自己完成接入」的主體。

**範圍**
- 包含：
  - 頻道後台的「啟用 bot」：到 Twitch 授權完整權限，比對授權帳號，把 bot 設為 mod，立即加入頻道。
  - 「停用 bot」：bot 離開，資料保留；重新啟用就復原。
  - 舊頻道視為未啟用。舊頻道重新啟用後，沿用既有的自訂指令與轉發設定（規格〈細部規則〉8）。
  - 關閉舊的 `/oauth/twitch` 獨立授權流程。
- 不包含：
  - 權限失效的偵測與修復（W-08）。
  - 刪除資料（W-09）。
  - 停權的頻道不能啟用（W-12 加上檢查）。

**驗收條件**
- [ ] 按「啟用 bot」完成授權後，不必重啟任何服務，bot 就出現在聊天室並具有 mod 身分；後台顯示「已啟用」。
- [ ] 授權途中取消，回到頻道後台，仍是「未啟用」。
- [ ] 用另一個 Twitch 帳號完成授權，回到頻道後台並顯示「請用頻道本人的帳號授權」，仍是「未啟用」，不保存該 token。
- [ ] 按「停用 bot」後，bot 離開聊天室，觸發指令與發生事件都沒有回應；後台顯示「已停用」。
- [ ] 停用後重新啟用，原本的指令與轉發設定都還在。
- [ ] 舊流程登記的頻道上線後顯示「未啟用」；啟用後原本的自訂指令可用，冷卻為全體 30 秒。
- [ ] 直接打開舊的 Twitch 授權連結，完成授權後看到「請到後台啟用」，並附連結，不會登記頻道。
- [ ] 自動設 mod 失敗時，啟用仍完成，後台提示手動輸入 `/mod xingyu1016`。
- [ ] Twitch bot 離線時按啟用，授權仍會保存；後台顯示「bot 暫時離線，上線後自動生效」；bot 上線後加入頻道。

**實作設計**
- 資料：
  - 不新增欄位。
  - 實況主 token 照舊存在 `OAuthToken`（user_id 是 twitch_id，client 是 #3）。
- 後端：
  - 新增 `starServer/dashboard/channel_activation.py`。
  - `GET /to/dashboard-twitch-enable?channel=&origin=`：
    - 這是整頁導覽：session 無效、`require_channel` 失敗、或頻道被停權（W-12）時，不回 JSON，而是導回 `{origin}/dashboard/channels/<id>?notice=<代碼>`。
    - 用以下 scope 產生授權網址：`channel:manage:moderators`、`moderation:read`、`moderator:read:followers`、`channel:read:subscriptions`、`channel:read:redemptions`、`channel:read:predictions`、`user:read:blocked_users`。
    - cookie 用 W-01 的 `dashboard_twitch_oauth`，格式在 W-01 的欄位外加 `channel_id`；`purpose = enable`。在 W-01 的分派表註冊 `enable` handler。
  - `enable` handler：
    1. `exchange_code` 加 `get_me`。`user.id` 不等於 cookie 的 channel 時，不保存，導回頻道頁並帶 `?notice=wrong_account`。
    2. `save_token_to_db`。
    3. 用實況主 token 呼叫 Twitch `Add Channel Moderator`，把 bot 帳號設為 mod。已經是 mod 的錯誤視為成功。
    4. `state = enabled`。
    5. `twitch_control.sync_channel`，結果是 `BotOffline` 時帶 `?notice=bot_offline`。
    6. 導回頻道頁。
  - `POST /dashboard/channels/{id}/disable`：`state = disabled`，然後 `sync_channel`。
  - 舊頻道資料轉換：重新啟用時，原有的 `TwitchChatCommand` 照用。W-05 加的新欄位預設值要讓舊指令等同全體冷卻 30 秒，這點由 W-05 的 ALTER 預設值保證。
  - 改 `bot_website.py`：
    - `/oauth/twitch`：拿掉原本「是域民才保存 token、新增頻道」的流程。沒有後台 cookie 的請求，一律回「請到星羽後台啟用」的頁面，附 `{frontend}/dashboard-login` 連結。
    - `/to/twitchauth`：改成直接導向 `{frontend}/dashboard-login`。
- 前端：
  - 頻道頁頁首的狀態區塊（`components/dashboard/channel/channel-status.tsx`），依 state 顯示：
    - 未啟用：「啟用 bot」按鈕，連到 `/to/dashboard-twitch-enable`。
    - 已啟用：「停用 bot」。
    - 已停用：「重新啟用」。
  - 讀網址的 `notice`（`wrong_account`、`bot_offline`、`session_expired`、`channel_forbidden`，以及 W-12 的 `channel_banned`）顯示提示後，從網址移除。寫法比照 `app/dashboard-login/page.tsx`。

**依賴**：W-02（`sync_channel`、只載入 enabled 的頻道）

**風險 / 實作注意**
- Add Channel Moderator 的 API 有速率限制，且帳號要已在聊天室出現過才能被設為 mod。失敗時不擋啟用：啟用照常完成，記 Sentry，後台提示「請在聊天室輸入 `/mod xingyu1016`」，W-08 會持續標示「bot 不是 mod」直到修好。
- `twitch_chatbot.USER_SCOPE` 是 bot 帳號自己的 scope，不要拿來要求實況主；實況主的 scope 以上面列的清單為準。

**進度**：未完成

### W-04 [共用] bot 發言管線與修改紀錄

**使用者價值**：W-05 自訂指令、W-06 計時訊息、W-07 事件回應都要代入變數、過 AutoMod 才發言，並且留修改紀錄；W-09 刪除資料時要保留修改紀錄；W-12 營運入口要能查修改紀錄。這些共用一套管線與資料表，三張功能卡就不用各寫一份。三張卡要用的資料表也在這裡一次建好，`models.py`、`client.py` 才不會被三張卡同時改。

**範圍**
- 包含：
  - W-05～W-07、W-11 要用的資料表、model 與 `sqldb` 存取函式。各卡的「資料」欄是欄位設計，實際在這張卡建立。
  - 變數代入。
  - AutoMod 檢查加送出。
  - 擋下紀錄的寫入，以及頻道後台的「最近被擋下的訊息」。
  - 修改紀錄的寫入與查詢介面。
- 不包含：營運入口的修改紀錄畫面（W-12）。

**驗收條件**
- [ ] 模板「感謝 {user}，已經 {count} 次」代入後，送出的文字正確。不認得的變數原樣保留，不會壞掉。
- [ ] 沒開台時 `{uptime}` 代入「未開台」。
- [ ] `check_template` 檢查會被頻道 AutoMod 擋下的模板，回傳 `blocked`；正常的模板回傳 `ok`；Twitch API 失敗或超出限制時回傳 `unavailable`。
- [ ] 不含 `{touser}`、`{args}` 的訊息，發言時不呼叫 Check AutoMod Status。
- [ ] 含 `{args}` 的訊息，代入後的文字會被 AutoMod 擋下時不送出，並寫進擋下紀錄。
- [ ] 含 `{args}` 的訊息，AutoMod 檢查失敗或超出限制時不送出，寫進擋下紀錄並標原因。
- [ ] 頻道後台的「最近被擋下的訊息」列出最近 20 筆，有時間、來源（指令名稱、計時訊息、事件種類）與文字。
- [ ] 呼叫修改紀錄寫入後，查詢得到操作者、時間、來源（後台或聊天室）、修改前與修改後。

**實作設計**
- 資料（給功能卡用的）：
  - `twitch_chat_command` 新增欄位，見 W-05。
  - 新增 `twitch_timer`，見 W-06；新增 `twitch_event_response`，見 W-07。
  - `twitch_bot_join_channel` 新增 `action_guild_id`，見 W-11。
  - `client.py` 為這些表加上 CRUD 與快取的存取函式，以及「依 twitch_id 刪除該頻道資料」的函式，給 W-09 用。
- 資料（這張卡自己的）：新增兩張表，schema 是 `stardb_basic`。
  - `twitch_channel_audit`：
    - 欄位：id（serial）、twitch_id、at、actor_platform（`twitch`、`discord`）、actor_id、actor_name、source（`dashboard`、`chat`）、target_kind（`command`、`timer`、`event_response`）、target_key、action（`create`、`update`、`delete`）、before（jsonb）、after（jsonb）。
    - index 是 twitch_id 加 at。
  - `twitch_automod_block`：
    - 欄位：id、twitch_id、at、source_kind、source_key、text、reason（`automod`、`check_failed`）。
    - 每個頻道只保留最新 100 筆，寫入時順手刪掉更舊的。
- 後端（Twitch bot 端）：新增 `starServer/twitch_bot/speech.py`。
  - `render(template: str, ctx: SpeechContext) -> str`：
    - `SpeechContext` 帶 user、args、count、channel、stream（開台資訊或 None）、channel_info（分類與標題）、event 變數。
    - 變數清單照〈現況與前提〉。`{touser}` 沒有參數時用觸發者。
    - 計時訊息沒有觸發者，`{user}`、`{touser}`、`{args}`、`{count}` 不提供，前端表單也不列出；模板裡寫了就原樣保留。
    - 開台資訊由 `events.py` 的開台、下播事件維護，Twitch bot 啟動時用 Helix `get_streams` 補一次。
    - `{game}`、`{title}` 用 Helix Get Channel Information 查，每個頻道快取 60 秒。
  - `async def say(channel: str, twitch_id: int, text: str, *, source_kind: str, source_key: str, reply_to: ChatMessage | None = None) -> bool`：
    - 用 `twitch_tokens.broadcaster_token` 取得 token，呼叫 Twitch `Check AutoMod Status`，通過才 `chat.send_message` 或 `reply`，回傳是否送出。
    - 沒通過或檢查失敗時，寫入 `twitch_automod_block`。
    - 只有內容帶入觀眾輸入（`{touser}`、`{args}`）的訊息，才在發言前檢查；同一頻道、同樣的文字快取檢查結果 10 分鐘。其他訊息的模板已在儲存時檢查過，直接送出。
    - 檢查超出限制或失敗時，帶觀眾輸入的訊息不發，記成 `check_failed`。
- 後端（web 端）：在 `starlib/twitch_speech_check.py` 提供 `async def check_template(twitch_id: int, template: str) -> TemplateCheck`，回傳 `ok`、`blocked` 或 `unavailable`。
  - 檢查前先把變數換成中性的佔位文字，例如 `{user}` 換成 `觀眾`，只檢查實況主寫的部分。
  - W-05、W-06、W-07 的儲存端點都先呼叫它：`blocked` 時回 422 `automod_blocked`，`unavailable` 時回 503 `automod_unavailable`，兩者都不儲存。
- 後端（兩邊共用）：新增 `starlib/twitch_audit.py`。
  - `record_change(twitch_id, actor, source, target_kind, target_key, action, before, after) -> None`。web 端與 Twitch bot 端的聊天室指令都呼叫它。
  - `list_changes(twitch_id, offset, limit)`。
- 後端（web 端）：新增 `starServer/dashboard/channel_audit.py`，只放端點。
  - `GET /dashboard/channels/{id}/automod-blocks`：要求 `require_channel`。
- 前端：`components/dashboard/channel/automod-blocks.tsx`，放在頻道後台的總覽，也就是 `app/dashboard/channels/[id]/page.tsx`。
- 介面：
  - `speech.render`、`speech.say`：簽名同上。`say` 不 raise，一律回傳 bool。
  - `starlib.twitch_audit.record_change(...)`：同步函式，在呼叫端的 DB session 內寫入。
  - `before` 與 `after` 是 dict，存可序列化的欄位快照，刪除時 `after` 為 None。

**依賴**：W-03（實況主 token 已保存，AutoMod 檢查要用）

**風險 / 實作注意**
- `Check AutoMod Status` 的速率限制以頻道計：一般帳號每分鐘 5 次、每小時 50 次；Affiliate 10 次與 100 次；Partner 30 次與 300 次（Twitch API Reference〈Moderation〉）。所以主要在儲存模板時檢查，發言時只檢查帶觀眾輸入的訊息。
- `{count}` 是指令的使用次數，由 W-05 存在指令列上。render 只負責代入，不負責遞增。

**進度**：未完成

### W-05 實況主能在後台管理自訂指令

**使用者價值**：實況主不必在聊天室打指令，就能在後台管理自訂指令：設定變數、冷卻、權限、別名，暫時關閉也不必刪除。

**範圍**
- 包含：
  - 後台指令的清單、新增、編輯、刪除、開關。
  - 聊天室觸發時的權限、冷卻、別名、使用次數，回應走 W-04 的管線。
  - 聊天室的 `!add_cmd`、`!remove_cmd`、`!list_cmd` 改成新規則，並寫修改紀錄。
  - 後台與聊天室同時編輯的衝突處理。
- 不包含：無。

**驗收條件**
- [ ] 在後台新增指令後立即能在聊天室觸發；回應內容的變數正確代入。
- [ ] 在聊天室 `!add_cmd` 新增的指令，重新整理後台後看得到，修改紀錄的來源是「聊天室」。
- [ ] 設定全體冷卻 30 秒：30 秒內一般觀眾第二次觸發不回應。實況主與 mod 觸發不受冷卻限制。
- [ ] 設定個人冷卻：同一位觀眾在冷卻內再觸發不回應，其他觀眾可以觸發。
- [ ] 權限設為「mod」：一般觀眾與 VIP 觸發不回應，mod 與實況主觸發會回應。權限層級是單選、有層級：所有人 < 訂閱者 < VIP < mod < 實況主。
- [ ] 觸發別名與觸發主名稱得到相同回應，`{count}` 一起累加。
- [ ] 關閉指令後觸發不回應，`!list_cmd` 不列出；重新打開後恢復。
- [ ] 在後台新增與既有名稱或別名重複的名稱，無法儲存並標出衝突。
- [ ] 回應內容會被頻道 AutoMod 擋下時無法儲存，並提示原因；AutoMod 暫時無法檢查時也無法儲存，提示稍後再試。`!add_cmd` 同樣檢查。
- [ ] `!add_cmd` 的名稱和既有指令或別名相同時，拒絕並提示，不覆蓋；和內建指令同名時拒絕。
- [ ] `!remove_cmd` 指定別名時，只移除這個別名，指令本身保留。
- [ ] 後台編輯中，有人在聊天室改了同一個指令，後台儲存時顯示衝突，不直接覆蓋。
- [ ] 舊頻道的既有指令在啟用後是全體冷卻 30 秒、權限所有人、開啟。

**實作設計**
- 資料：`twitch_chat_command` 新增以下欄位，由 W-04 建立。ALTER 的預設值讓既有指令等同舊行為：
  - `aliases`（text[]，預設空）
  - `enabled`（bool，預設 true）
  - `global_cooldown`（int 秒，預設 30）
  - `user_cooldown`（int 秒，預設 0）
  - `permission`（String，預設 `everyone`）
  - `use_count`（int，預設 0）
  - `updated_at`
- 上下限：冷卻 0～3600 秒，名稱 1～25 字，回應 1～500 字。Twitch 單則訊息上限是 500 字。
- 後端（web 端）：新增 `starServer/dashboard/channel_commands.py`。
  - `GET`、`POST /dashboard/channels/{id}/commands`。
  - `PUT`、`DELETE /dashboard/channels/{id}/commands/{name}`。
    - 帶 `original`，用 `conflict.check_conflict` 比對，衝突回 409，形狀照伺服器後台。`original` 只放可編輯的欄位，不放 `use_count`、`updated_at`，觸發指令才不會造成假衝突。
    - 改名：在同一個交易內刪除舊列、新增新列，`use_count` 沿用；修改紀錄記成一次 `update`。
  - 名稱與別名統一轉小寫、去掉開頭的 `!`；同頻道內不得重複，也不得與內建指令重複。
  - 每次寫入後：
    - `starlib.twitch_audit.record_change`，actor 是 session 的 Twitch 或 Discord 身分。
    - `twitch_control.invalidate("twitch_cmd", id)`。
- 後端（Twitch bot 端）：改 `starServer/twitch_bot/commands.py`。
  - 快取改存整列指令，名稱與別名都指到同一列。
  - 觸發時依序檢查：
    1. enabled。
    2. 權限：從 ChatMessage 的 user 旗標判斷 mod、vip、subscriber，實況主用 room 名稱判斷。
    3. 冷卻：以「頻道、指令」計全體冷卻，以「頻道、指令、使用者」計個人冷卻；實況主與 mod 豁免。
  - 通過後 `use_count += 1`，然後 `speech.say(..., reply_to=msg)`。
  - 聊天室管理指令照驗收條件改寫，並寫修改紀錄（source 是 `chat`，actor 是聊天室的使用者）。
  - 寫入後更新快取並發 `invalidate`，讓其他實例與 web 一致。
- 前端：
  - 改 `app/dashboard/channels/[id]/commands/page.tsx`。
  - 新增 `components/dashboard/channel/command-list.tsx`、`command-form.tsx`、`lib/dashboard-channel-commands.ts`。
  - 表單：名稱、回應（`LabelWithCount`，500 字）、別名（多值輸入）、全體與個人冷卻、權限（單選）、開關。
  - 回應欄下方列出可用的變數。
  - 衝突提示沿用 `components/dashboard/conflict-notice.tsx`。
- `CHANNEL_NAV` 不必改，W-01 已經建好。

**依賴**：W-04（`speech.say`、`render`、`record_change`）

**風險 / 實作注意**
- `use_count` 每次觸發都寫 DB，量大時可以改成批次寫回。這屬於實作細節。
- Twitch IRC tags 的 badges 可以判斷 vip 與 subscriber，twitchAPI 的 `ChatUser` 有對應屬性。

**進度**：未完成

### W-06 實況主能設定計時訊息

**使用者價值**：實況主能讓 bot 在開台時定時提醒觀眾，例如社群連結、規則；聊天室安靜時不會洗版。

**範圍**
- 包含：計時訊息的清單、新增、編輯、刪除、開關，以及 Twitch bot 端依條件發送。
- 不包含：無。

**驗收條件**
- [ ] 開台中，計時訊息依設定的間隔發送。開台後第一則等滿一個間隔才發。
- [ ] 沒開台時不發送；下播後停止，再次開台時重新計時。
- [ ] 設最少聊天量 10 則：時間到但距上次發送不足 10 則時不發，累積到第 10 則時立刻發。bot 自己的訊息不計入。
- [ ] 關閉某則計時訊息後它不再發送，其他計時訊息不受影響。
- [ ] 間隔小於 5 分鐘無法儲存。訊息超過 500 字無法儲存。
- [ ] 訊息會被頻道 AutoMod 擋下時無法儲存，並提示原因。
- [ ] 訊息內容的變數正確代入。
- [ ] 每次新增、修改、刪除都寫進修改紀錄。

**實作設計**
- 資料：新增 `twitch_timer`，schema 是 `stardb_basic`，由 W-04 建立。
  - 欄位：id（serial）、twitch_id、message、interval_minutes、min_chat_lines、enabled、updated_at。
  - 上下限：間隔 5～1440 分鐘，最少聊天量 0～1000 則，訊息 1～500 字。
- 後端（web 端）：新增 `starServer/dashboard/channel_timers.py`。
  - 提供 CRUD，形狀比照 W-05，包含衝突檢查。
  - 寫入後 `record_change`，並 `invalidate("twitch_timer", id)`。
- 後端（Twitch bot 端）：實作 `starServer/twitch_bot/timers.py`。
  - 每個 enabled 頻道、每則計時訊息，各有一個狀態：上次發送時間、自上次發送後的聊天數。
  - 開台、下播由 `events.py` 的 stream online、offline 通知 `timers.on_stream_online(twitch_id)`、`on_stream_offline(twitch_id)`。
    - 這是 W-02 拆模組時就預留的呼叫點；W-02 在 `events.py` 先呼叫空函式。
  - 聊天訊息由 `commands.py` 的 on_message 呼叫 `timers.on_chat_message(twitch_id, is_bot)` 計數。
  - Twitch bot 啟動時，用 Helix `get_streams` 補一次各頻道目前是否開台。
  - 每 30 秒檢查一次，條件成立就 `speech.say`。
- 前端：
  - 改 `app/dashboard/channels/[id]/timers/page.tsx`。
  - 新增 `components/dashboard/channel/timer-list.tsx`、`timer-form.tsx`、`lib/dashboard-channel-timers.ts`。

**依賴**：W-04（`speech.say`、`record_change`）

**風險 / 實作注意**
- `commands.py` 與 `events.py` 呼叫 `timers` 的那一行，由 W-02 先放好，W-06 不改這兩個檔案，避免和 W-05、W-07 衝突。
- 開台狀態在 Twitch bot 重啟時會遺失，用 `get_streams` 補。

**進度**：未完成

### W-07 實況主能設定事件回應

**使用者價值**：實況主能自訂 bot 在聊天室感謝追隨、訂閱、Raid 的文字，也可以關掉不要的；不需要設定 Discord 轉發也能使用。

**範圍**
- 包含：
  - 事件：開台、追隨、訂閱、續訂、贈訂、Raid。每種都有開關、文字與變數。
  - 開台訊息納入事件回應。
  - 與轉發 Discord 脫鉤。
  - 贈訂只回應一次；匿名贈訂照常回應。
- 不包含：轉發 Discord 的事件範圍（W-11）。

**驗收條件**
- [ ] 新啟用的頻道，所有事件回應預設開啟，並使用中性語氣的預設文字。
- [ ] 有人追隨時，聊天室出現回應；改寫文字後，下一次事件改用新文字。
- [ ] 訂閱、續訂、贈訂、Raid 各自出現對應的回應，`{months}`、`{amount}`、`{viewers}` 正確代入。
- [ ] 一次贈 5 份訂閱時，聊天室只出現一則贈訂回應，不會每位收禮者各一則。
- [ ] 匿名贈訂時照常回應，名稱顯示為「匿名」。
- [ ] 關閉 Raid 回應後，被 Raid 時聊天室不發回應。
- [ ] 改寫的文字會被頻道 AutoMod 擋下時無法儲存，並提示原因。
- [ ] 沒有設定轉發 Discord 的頻道，事件回應照常出現。
- [ ] 每次修改都寫進修改紀錄。

**實作設計**
- 資料：新增 `twitch_event_response`，schema 是 `stardb_basic`，由 W-04 建立。
  - 欄位：twitch_id、event_kind（`stream_online`、`follow`、`subscribe`、`resubscribe`、`gift`、`raid`）、enabled、template、updated_at；PK 是 twitch_id 加 event_kind。
  - 沒有資料列時，視為開啟並使用預設文字。預設文字定義在程式碼的常數表，不寫進 DB，之後調整預設文字才不必改 DB。
- 後端（web 端）：新增 `starServer/dashboard/channel_event_responses.py`。
  - `GET /dashboard/channels/{id}/event-responses`：回傳六種，每種都有 enabled、template、is_default、可用變數。
  - `PUT /dashboard/channels/{id}/event-responses/{kind}`。
  - 「恢復預設」就是刪除該列。
  - 寫入後 `record_change`，並 `invalidate("twitch_event_response", id)`。
- 後端（Twitch bot 端）：改 `starServer/twitch_bot/events.py`。
  - 拿掉各 handler 裡 `if channel_config and channel_config.action_channel_id` 的聊天室發送條件，改成查該頻道的事件回應設定，再 `speech.say`。
  - 訂閱：`on_channel_subscribe` 在 `is_gift` 時不回應，由贈訂回應一次，避免每位收禮者各一則。
  - 贈訂：`on_channel_subscription_gift` 拿掉 `not is_anonymous` 的條件；匿名時 `{user}` 代入「匿名」。
  - bus 事件的發布維持原樣，與這張卡無關。
- 前端：
  - 改 `app/dashboard/channels/[id]/events/page.tsx`。
  - 新增 `components/dashboard/channel/event-response-list.tsx`、`lib/dashboard-channel-events.ts`。
  - 每種事件一列，有開關、文字（`LabelWithCount`，500 字）、可用變數、恢復預設。

**依賴**：W-04（`speech.say`、`record_change`）

**風險 / 實作注意**
- 追隨、訂閱類事件需要 bot 是 mod 才訂閱得到。mod 被拿掉時，這些回應會自然停止，W-08 會把它顯示成部分暫停。

**進度**：未完成

### W-08 實況主能看到權限問題並一鍵修復

**使用者價值**：實況主在 Twitch 端撤銷授權、拿掉 bot 的 mod，或封鎖 bot 時，打開後台就知道哪些功能停了，按一下就能修好，不必找人。

**範圍**
- 包含：
  - 頻道狀態的完整判定：未啟用、已啟用、部分暫停（附原因與暫停的功能）、已停用。已停權由 W-12 補上。
  - 頻道頁頁首顯示問題與「修復」按鈕。修復就是重新走 W-03 的啟用流程。
- 不包含：營運入口的狀態清單（W-12 使用這張卡的判定函式）。

**驗收條件**
- [ ] 在聊天室拿掉 bot 的 mod 後，下一次載入頻道後台時，頁首顯示「bot 不是 mod」，並列出暫停的功能（追隨、訂閱、續訂、贈訂的事件回應與轉發）。自訂指令仍能回應。
- [ ] 在 Twitch 撤銷星羽的授權後，下一次載入時顯示「授權已失效」，並列出需要授權的功能已暫停。
- [ ] 在 Twitch 封鎖 bot 帳號後，下一次載入時顯示問題，處理方式視同撤銷授權。
- [ ] 按「修復」並完成授權後，問題消失，暫停的功能恢復。bot 已在聊天室時，修復後會補訂需要 mod 的事件（W-02 的 sync 是 idempotent）。
- [ ] Twitch bot 離線時，頁首顯示「bot 暫時離線」，不誤判成權限問題。

**實作設計**
- 資料：無。狀態在載入時即時判定，不存 DB。
- 後端：新增 `starServer/dashboard/channel_health.py`。
  - `async def channel_health(twitch_id) -> ChannelHealth`，`ChannelHealth` 包含 state、issues 與 paused_features。
    - state 是 `inactive`、`enabled`、`partial`、`disabled`；W-12 再加 `banned`。
    - issues 是 `token_invalid`、`not_mod`、`bot_banned`、`bot_offline` 的列表。
    - paused_features 是功能代碼列表。
  - 判定方式：
    - 用 `twitch_tokens.broadcaster_token` 取得 token（已含 refresh），再用 Twitch `validate` 端點取 scope 比對必要的 scope。取不到 token 就是 `token_invalid`。
    - 用 Helix Get Moderators 判斷 bot 是不是 mod。不用 Chat 的 `is_mod`，因為它是快取。
    - 用 Helix Get Banned Users 判斷 bot 是否被 ban，用 Get User Block List（`user:read:blocked_users`，W-03 已要求）判斷是否被封鎖。兩者任一成立就是 `bot_banned`。查詢失敗時略過這一項，不擋其他判定。
    - 用 `twitch_control.channel_status` 取得 joined 與訂閱結果。
  - 功能與條件的對照表放在常數：
    - 需要 mod：follow、subscribe、resubscribe、gift 的回應與轉發，以及兌換、預測的轉發。
    - 需要 token：AutoMod 檢查（因此所有發言），以及上述全部。
  - `GET /dashboard/channels/{twitch_id}` 改為回傳 `health`。
- 前端：
  - 改 W-03 的 `channel-status.tsx`，依 issues 顯示說明與「修復」按鈕。按鈕和「啟用 bot」連到同一個入口。
  - 新增 `lib/dashboard-channel-health.ts`：問題代碼對應的文案，以及功能代碼對應的名稱。

**依賴**：W-03（啟用流程、token）

**風險 / 實作注意**
- token 失效時，W-04 的 AutoMod 檢查必然失敗，bot 實際上會完全不發言。所以 `token_invalid` 的 paused_features 要列出所有發言功能。這是規格「需要該授權的功能暫停」的實際範圍，實作時照此顯示。

**進度**：未完成

### W-09 實況主能刪除頻道的所有資料

**使用者價值**：想徹底離開的實況主能清掉自己頻道在星羽的資料。

**範圍**
- 包含：
  - 頻道「設定」頁的「刪除所有資料」，確認方式是輸入頻道名稱。
  - 刪除時停用 bot。
  - 修改紀錄與停權狀態保留。
- 不包含：無。

**驗收條件**
- [ ] 輸入的頻道名稱不符時，無法按刪除。
- [ ] 刪除後：bot 離開聊天室；指令、計時訊息、事件回應、轉發設定、實況主 token 全部清除；頻道狀態變成「未啟用」。再次啟用時從空白開始。
- [ ] 刪除後，`twitch_channel_audit` 裡該頻道的修改紀錄仍在（用 DB 或 W-04 的 `list_changes` 確認）。

**實作設計**
- 資料：不新增欄位。
- 後端：新增 `starServer/dashboard/channel_settings.py`。
  - `POST /dashboard/channels/{id}/delete-data {confirm_login}`：`confirm_login` 必須等於頻道 login，大小寫不敏感。
  - 在同一個交易內：
    - 刪除 `twitch_chat_command`、`twitch_timer`、`twitch_event_response`、`twitch_automod_block` 中屬於該頻道的資料，以及該頻道 client #3 的 `OAuthToken`。
    - `TwitchBotJoinChannel` 的 `action_channel_id`、`action_guild_id`、`point_name` 清空，`state` 設為 `inactive`。`banned_at` 不動（W-12 新增後也一樣）。資料列本身保留，營運入口與停權需要它。
  - 之後 `sync_channel`，並 invalidate 所有快取。
  - `twitch_channel_audit` 不刪。
  - `twitch_point` 第一階段沒有資料，但一起刪掉該頻道的資料，條件是 `broadcaster_id`（PK 是 twitch_id 加 broadcaster_id）。
  - 刪除各表用 W-04 在 `client.py` 建好的「依 twitch_id 刪除」函式，這張卡不改 `client.py`。
- 前端：
  - 改 `app/dashboard/channels/[id]/settings/page.tsx`。
  - 新增 `components/dashboard/channel/delete-data.tsx`：危險區塊，輸入框加確認按鈕。

**依賴**：W-04（`twitch_automod_block` 表）

**進度**：未完成

### W-10 用析域登入能同時管理伺服器與頻道

**使用者價值**：有析域帳號的人登入一次，就能同時管理 Discord 伺服器和自己所有的 Twitch 頻道；這也是使用跨平台功能的前提。

**範圍**
- 包含：
  - 析域登入的 session 帶入析域帳號連結的所有 Twitch 頻道。
  - 連結增減時，60 秒內生效。
  - 只連結 Twitch、沒有連結 Discord 的析域帳號也能登入。
  - 落地頁是個人區，個人區並列伺服器與頻道。
  - 正在看的頻道被解除連結時，回到頻道清單並提示。
- 不包含：轉發 Discord 的設定（W-11）。

**驗收條件**
- [ ] 析域帳號連了兩個 Twitch 和一個 Discord，用析域登入後，個人區同時有伺服器入口和兩個頻道；兩個頻道後台都能進入。
- [ ] 析域帳號只連 Twitch、沒連 Discord，能用析域登入，看得到頻道，看不到伺服器。
- [ ] 析域帳號都沒有連結，用析域登入時回到登入頁，提示先連結 Discord 或 Twitch。
- [ ] 登入中在 auth server 解除某個 Twitch 的連結，60 秒後該頻道從清單消失；正在看它的頁面，下一次操作被導回頻道清單並提示。
- [ ] 登入中在 auth server 新增一個 Twitch 連結，60 秒後出現在頻道清單。
- [ ] 析域登入、而且有 Discord 時，頻道後台的轉發 Discord 區塊不再顯示「需要析域帳號」。析域登入但沒有 Discord 時，改顯示「需要連結 Discord」。

**實作設計**
- 資料：不新增欄位。析域登入 session 的 Twitch 頻道清單來自帳號跟隨，不存 DB。
- 後端：
  - 改 `session.py`：
    - `_Followed` 加 `twitch_channels`，由 `Account.twitch_passports` 轉成 `TwitchIdentity`；名稱與頭像從 `TwitchBotJoinChannel` 補，沒有就用 passport 的顯示名稱。
    - `follow_account` 把結果放進 `SessionInfo.twitch_channels`。
    - 析域登入的 session 判定失效的條件，從「不再連結這個 Discord」改成：這個 session 有 Discord 時，維持原本規則；沒有 Discord 時，析域帳號查無或停權才失效。
  - 改 `domalyze_login.py`：
    - 沒有 Discord 但有 Twitch 時，直接建立沒有 Discord 身分的 session：`login_method = domalyze`、`account_id` 有值、`discord_user_id` 與 `twitch_user_id` 都是 null、`name` 用域民代號（查不到時用「析域帳號」）、頭像為 null。
    - 這種 session 的主身分 key 是 `domalyze:<account_id>`；登出時刪除同一個 `account_id`、而且沒有 Discord 的析域 session。
    - auth server 暫時不可用時，沿用上次的頻道清單；沒有上次結果時，頻道清單為空，不判定失效。
    - 兩者都沒有時，維持 `domalyze_no_discord` 的提示，文案改成「先連結 Discord 或 Twitch」。
  - 析域登入帶入的頻道，若不存在 `TwitchBotJoinChannel` 就新增一列 `inactive`，與 W-01 的規則相同。
  - 改 `personal.py`：個人區的 overview 加上 `channels`。Discord 欄位為 null 時，個人區的 Discord 相關區塊隱藏。
    - 個人區目前用 `require_session`（需要 Discord）。這裡改用 `require_any_session`，只在需要 Discord 的子區塊檢查。
- 前端：
  - `lib/dashboard-login.ts`：`domalyze_no_discord` 的文案改成「先連結 Discord 或 Twitch」。
  - `app/dashboard/page.tsx` 與 `components/dashboard/personal/`：新增「我的頻道」區塊，列出頻道與狀態，連到頻道後台。
  - 改 `channel-access-guard.tsx`：收到 403 `channel_forbidden`，而且這個 session 是析域登入時，導到 `/dashboard/channels?notice=channel_unlinked`，由頻道清單頁顯示提示。不導回 `/dashboard`，因為那裡的 `notice` 會被轉到伺服器清單。

**依賴**：W-01（頻道後台、`require_channel`）

**風險 / 實作注意**
- 個人區既有區塊大多以 Discord ID 查資料。沒有 Discord 的析域 session 進個人區時，逐一確認每個區塊在 discord 為 null 時不會出錯。

**進度**：未完成

### W-11 實況主能把事件轉發到 Discord

**使用者價值**：有析域帳號的實況主能自己設定把開台、追隨、訂閱等事件發到哪個 Discord 頻道，不必請 bot owner 改資料庫；外部頻道的事件也不會跑到 bot owner 的頻道。

**範圍**
- 包含：
  - 轉發設定頁：選伺服器與頻道，要求該伺服器的 Manage Channels。
  - 轉發的事件：開台、下播、追隨、訂閱、續訂、贈訂、Raid、兌換、預測。
  - 預測結果改發到實況主設定的頻道。私訊仍只發給 bot owner。
  - 新增贈訂的 bus 事件。
- 不包含：無。

**驗收條件**
- [ ] 用析域登入，在轉發頁選一個自己有 Manage Channels 的伺服器頻道並儲存後，有人訂閱時該頻道收到通知。
- [ ] 選擇清單只列出 bot 在、且自己有 Manage Channels 的伺服器；直接呼叫 API 設定沒有權限的頻道，回 403。
- [ ] 外部頻道的預測結果發到該實況主設定的頻道，不再發到 bot owner 的預設頻道；沒設定就不發。
- [ ] 私訊仍然只發到 bot owner 的預設頻道。
- [ ] 贈訂時，轉發頻道收到一則贈訂通知，有贈送者與份數。
- [ ] 實況主解除析域連結後，已設定的轉發照常運作；只用 Twitch 登入時，轉發頁顯示目前設定但不能修改，並提示要用析域登入。
- [ ] 下播時，轉發頻道收到下播通知。
- [ ] 每次修改轉發設定都寫進修改紀錄。

**實作設計**
- 資料：沿用 `TwitchBotJoinChannel.action_channel_id`，另外使用 W-04 建好的 `action_guild_id`（BigInteger），供顯示與權限檢查。
- 後端（web 端）：新增 `starServer/dashboard/channel_forward.py`。
  - `GET /dashboard/channels/{id}/forward`：回傳目前設定，以及 `editable`（`forward_access == ok`，與 W-01 同一個判斷）。
  - `GET /dashboard/channels/{id}/forward/options`：bot 在、且 session 的 Discord 有 Manage Channels 的伺服器與文字頻道。用 `guilds.guild_perms` 的 `manage_channels`。
  - `PUT /dashboard/channels/{id}/forward {guild_id, channel_id | null}`：
    - 要求 `editable`。
    - 伺服器端重新檢查 Manage Channels，以及頻道屬於該伺服器。
    - 寫入後 `record_change`（target_kind 加上 `forward`）。
  - Discord 端以 `resolve_action_channel` 讀 DB，設定改了本來就立即生效，不必 invalidate。
- 後端（Discord 端）：
  - 改 `starDiscord/cmds/twitch_notify.py`：`on_prediction_result` 改用 `_action_channel(event.broadcaster_id)`。
  - `TwitchPredictionResultEvent` 加上 `broadcaster_id`，同步更新 `twitch_activity.py` 與 `docs/messaging-contract.md`。
  - 新增 `on_gift` handler。
  - `twitch_live_notify.py` 的下播通知目前發到 `DEFAULT_TWITCH_CHANNEL`（約 68 行），改成發到 action channel。
- 後端（Twitch bot 端）：改 `starServer/twitch_bot/events.py`：
  - 新增 `TwitchSubscriptionGiftEvent` 並發布，事件欄位有 broadcaster_id、user_name（匿名時為 null）、total、tier。
  - 預測結果事件帶 broadcaster_id。
- 前端：
  - 改 `app/dashboard/channels/[id]/forward/page.tsx`。
  - 新增 `components/dashboard/channel/forward-form.tsx`、`lib/dashboard-channel-forward.ts`。
  - 頻道選擇器沿用 `components/dashboard/channel-select.tsx`；它只能選頻道，伺服器選擇器在 `forward-form.tsx` 另外做。

**依賴**：
- W-10：析域 session 同時帶 Discord 與 Twitch 頻道。
- W-07：兩張卡都改 `events.py`，W-07 先完成。

**風險 / 實作注意**
- bus 事件新增欄位時，舊的 Discord 端會略過不認得的欄位（契約已規定），部署順序不受影響。但新事件類型要等兩邊都部署完才會開始處理。

**進度**：未完成

### W-12 bot owner 能在營運入口管理頻道

**使用者價值**：bot owner 能看到有哪些頻道接入、各自的狀態；遇到濫用的頻道可以停權，並查修改紀錄追到是誰寫的。這是共用 bot 帳號的保險。

**範圍**
- 包含：
  - 營運入口頁：頻道清單、狀態、停權與解除停權、修改紀錄。
  - 停權後，實況主那邊的畫面與限制。
  - 頻道狀態加上「已停權」。
- 不包含：無。

**驗收條件**
- [ ] bot owner 用 Discord 或析域登入後，頁首出現「營運」，清單列出所有曾經在後台出現過的頻道，每個都有狀態：未啟用、已啟用、部分暫停（附原因）、已停用、已停權。
- [ ] 非 bot owner 看不到「營運」；直接打開網址或呼叫 API，得到 403。
- [ ] 停權一個已啟用的頻道後，bot 離開該頻道；實況主後台顯示「此頻道已被停權」與支援 Discord 伺服器的邀請連結，「啟用 bot」不能按，直接呼叫啟用也被擋下。
- [ ] 停權任何狀態的頻道都會成功，包含未啟用與已停用。
- [ ] 解除停權後，頻道回到「已停用」（不會自動啟用），實況主可以自己重新啟用。
- [ ] 在營運入口打開某頻道的修改紀錄，看得到每筆修改的操作者、時間、來源、修改前與修改後。
- [ ] 實況主刪除所有資料後，營運入口仍列出這個頻道，修改紀錄仍查得到。
- [ ] 已停權的頻道刪除資料後，仍是已停權。

**實作設計**
- 資料：`twitch_bot_join_channel` 新增 `banned_at`（timestamp，可為 null）、`banned_reason`（String，可為 null）。
- 後端：新增 `starServer/dashboard/ops.py`。
  - `require_bot_owner` dependency：使用 `require_session`（需要 Discord），並檢查 `await sclient.bot.is_owner(discord.Object(int(info.discord_user_id)))`，不是 owner 就 403。
  - `GET /dashboard/ops/channels?page=`：每頁 50 筆，每筆有頻道資料與 `channel_health`（W-08）。已停權的直接回 `banned`，不打 Twitch API。
  - `POST /dashboard/ops/channels/{id}/ban {reason}`：設 `banned_at`、`state = disabled`，然後 `sync_channel`。
  - `POST /dashboard/ops/channels/{id}/unban`：清除 `banned_at`。
  - `GET /dashboard/ops/channels/{id}/audit?page=`：使用 `channel_audit.list_changes`。
  - W-03 的啟用 handler 與 `/to/dashboard-twitch-enable`：`banned_at` 不為 null 時回 403 `channel_banned`。
  - `channel_health` 遇到 `banned_at` 時回 `state = banned`。
  - `/dashboard/me` 加 `is_bot_owner`，給前端決定是否顯示「營運」。
- 前端：
  - 新增 `app/dashboard/ops/page.tsx`、`app/dashboard/ops/channels/[id]/page.tsx`（修改紀錄）、`components/dashboard/ops/`。
  - 頁首 NAV 在 `is_bot_owner` 為 true 時加「營運」。
  - `channel-status.tsx` 加上 `banned` 的畫面：顯示說明與星羽支援 Discord 伺服器的邀請連結，隱藏啟用按鈕。

**依賴**：
- W-04：修改紀錄。
- W-08：`channel_health`。

**進度**：未完成

### W-13 官網有 Twitch bot 介紹與接入入口

**使用者價值**：外部實況主從官網就能知道星羽有 Twitch bot、能做什麼，並直接從入口開始接入。

**範圍**
- 包含：
  - 官網新增 Twitch bot 的功能介紹，內容只寫第一階段已上線的功能：自訂指令、計時訊息、事件回應、轉發 Discord。
  - 「開始使用」入口：未登入時到登入頁並預選 Twitch，已登入時直接進頻道後台。
- 不包含：多語言版本。

**驗收條件**
- [ ] 官網看得到 Twitch bot 的介紹，列出的功能都已經上線，不提還沒做的點數、聊天室管理。
- [ ] 未登入時按「開始使用」，到登入頁，可以直接用 Twitch 登入，登入後落在自己的頻道後台。
- [ ] 已登入時按「開始使用」，直接進頻道後台。
- [ ] 文案用直白的寫法，不用星羽的人設語氣。
- [ ] 360px 寬的畫面版面正常。

**實作設計**
- 資料：無。
- 後端：無。
- 前端：
  - `lib/features-data.ts` 新增 Twitch bot 的功能項目。
  - `app/features/page.tsx` 新增一個 Twitch 區段，或新增 `app/twitch/page.tsx`，由動手的人依現有版面選擇。
  - 首頁 `app/page.tsx` 的功能區加一個連結。
  - 「開始使用」連到 `/dashboard/channels`；未登入時由後台 layout 導到 `/dashboard-login?next=/dashboard/channels`。
  - 登入頁讀到 `next` 是 `/dashboard/channels` 開頭時，把 Twitch 按鈕排第一。
  - 頻道清單頁 `/dashboard/channels` 由 W-01 建好，這張卡不改。

**依賴**：W-05、W-06、W-07、W-11（介紹的功能要已上線；Twitch 登入與頻道後台來自 W-01）

**風險 / 實作注意**：文案照規格〈已定案的前提〉的中性語氣，用直白的寫法，不寫空洞形容詞。

**進度**：未完成

## 開工前待決

無。三題已拍板：AutoMod 主要在儲存模板時檢查（W-04）、停權頁附支援 Discord 伺服器邀請連結（W-12）、自動設 mod 失敗不擋啟用（W-03）。
