# 營運入口擴充任務拆解

## 現況與前提
- 技術棧：後端 FastAPI（`starServer/dashboard/`，跑在 `WebsiteThread` 自己的 event loop），Discord bot 是 py-cord（主 process 的主 loop），Twitch bot 是獨立 process（`twitch_main`），兩個 process 之間用 Redis 匯流排（`starlib/messaging`）的 RPC 溝通；前端是 `D:/github/domalyze_frontend`（Next.js）。
- 既有相關機制：
  - **營運入口**：`ops.py`（Twitch 頻道清單、`/health`、停權、修改紀錄）、`ops_discord.py`（伺服器清單 `_live()`、每日人數、加入離開紀錄）、`ops_website.py`（每週連結率）。權限一律用 `ops.require_bot_owner`，不是 owner 回 403 `not_bot_owner`。`starServer/dashboard/__init__.py` 用 `pkgutil.iter_modules` 自動 include 每個模組的 `router`。
  - **呼叫 Discord bot**：後台跟 bot 不同 loop。要 await Discord API 或迭代大量快取時用 `await asyncio.wrap_future(bot.submit(coro))`（例：`discord_users.py`、`guilds.py`）；`_live()` 只讀少量屬性才直接讀。
  - **呼叫 Twitch bot**：`twitch_control._call(method, twitch_id)` 經 `rpc.request`，`RpcUnavailable`（5 秒沒回應）轉成 `BotOffline`；Twitch 端在 `starServer/twitch_bot/channels.py` 的 `register()` 用 `rpc.handle` 註冊 `channel.sync`、`channel.status`。
  - **後台 DB**：`db.run_db` 走專屬 `ThreadPoolExecutor(max_workers=3)`。
  - **排程**：Discord bot 的 `self.bot.scheduler`（APScheduler `AsyncIOScheduler`）。週期任務在 `starDiscord/cmds/task.py` 的 `on_ready` 註冊，`debug_mode` 時一個都不註冊，但 `scheduler.start()` 照樣執行；同一個 scheduler 上還有 `DateTrigger` 一次性 job：抽獎、投票結束、YouTube 開台通知（`task.py:318`，每部影片一個）。`settle_website_link_rate` 等部分 job 會自己 `except Exception` 後只記 log。
  - **Twitch 頻道清單的健康度**：前端 `ops-channel-row.tsx` 的 `useHealth` 對每個 `enabled` 的列自動打 `GET /dashboard/ops/channels/{id}/health`（同時最多 3 個），`/health` 會續期 token 並呼叫 Twitch validate，已經會顯示授權失效；但只看得到目前這一頁，沒有跨頁統計或篩選。
  - **實況主 token**：`OAuthToken`（`tokens.oauth_token`）以 `user_id = str(twitch_id)` 與 `client_credential_id` 對應；`client_credential_id` 要先用 `sqldb.get_oauth_client(APIType.Twitch, BROADCASTER_CLIENT_SEQ)` 取 `client.credential_id`，`BROADCASTER_CLIENT_SEQ = 3` 是 `Credential.source_seq`，不是 credential id。沒有 token 或 `refresh_token` 為空算 `missing`。只在用到時續期（`twitch_tokens._refresh_locked`），所以 access token 過期本身不算異常。refresh token 失效（`revoked`）目前只寫 log，不留在 DB。必要 scope 是 `starServer/dashboard/channel_activation.py` 的 `ENABLE_SCOPES`。
  - **頻道狀態**：`inactive`、`enabled`、`disabled`，加上營運入口算出的 `banned`（`channels.py`）。
  - **成員快取**：`dee80157` 起，每日人數只在 `bot.is_ready() and all(g.chunked for g in bot.guilds)` 時取樣。
  - **DB 遷移**：專案沒有遷移工具，`create_all` 只建新表，既有表加欄位要手動 `ALTER TABLE`。
  - **舊指令**：`starDiscord/cmds/owner.py` 的 `/find`（ID 查使用者、頻道、伺服器、身分組、訊息）、`/findmember`（指定伺服器與 `happycamp_guild[0]` 的共通成員），`help.py:235-236` 有說明。
- 這次會動到的既有部位：
  - 後端：`starServer/dashboard/ops_discord.py`、`ops.py`、`db.py`、`twitch_control.py`、`channel_activation.py`、`channel_health.py`，新增 `ops_system.py`；`starDiscord/bot.py`、`starDiscord/cmds/task.py`，新增 `starDiscord/scheduler_status.py`；`starServer/twitch_bot/channels.py`、`twitch_main.py`；`starlib/messaging/bus.py`、`starlib/twitch_tokens.py`、`starlib/oauth/oauth_lib.py`、`starlib/database/postgresql/client.py`。
  - 前端：`components/dashboard/ops/ops-tabs.tsx`、`ops-discord.tsx`、`ops-channel-row.tsx`、`ops-channel-list.tsx`；`lib/dashboard-ops*.ts`；新增 `app/dashboard/ops/system/`、`app/dashboard/ops/discord/lookup/`、`app/dashboard/ops/discord/common/`。
- 已定案的技術前提：
  - 全部只給 bot owner，沿用 `require_bot_owner` 與 `OpsForbidden`。
  - 依賴成員快取的結果，快取沒載完時不計算或明確標示可能不完整。

## 實作順序總覽

| # | 卡號 | 進度 | 標題 | 依賴 | 並行組 | 備註 |
|---|---|---|---|---|---|---|
| 1 | O-01 | 未完成 | bot owner 能在網頁上用 ID 查使用者、頻道、伺服器、身分組與訊息 | 無 | A | 骨架切片，取代 `/find` |
| 2 | O-03 | 未完成 | bot owner 能在系統分頁看到 Discord bot、Twitch bot、匯流排與 DB 的運行狀態 | 無 | A | 新增「系統」分頁 |
| 3 | O-05 | 完成 | bot owner 能跨頁統計並篩出 token 有問題的 Twitch 頻道 | 無 | A | 做不做見待決 3 |
| 4 | O-02 | 未完成 | bot owner 能查任兩個伺服器的共通成員 | O-01 | B | 取代 `/findmember` |
| 5 | O-04 | 未完成 | bot owner 能看到每個排程任務的下次執行時間與最近一次結果 | O-03 | B | |

並行組 A 的三張卡動到的檔案互不重疊。O-02 與 O-01 都在 `ops_discord.py`、`lib/dashboard-ops-discord.ts` 加東西，但是不同段落，git 可自動合併。

## 任務卡

### O-01 bot owner 能在網頁上用 ID 查使用者、頻道、伺服器、身分組與訊息

**使用者價值**：bot owner 不必在 Discord 裡打 `/find`，貼一個 ID 就能在後台看到它是什麼；同一個 ID 對到多種東西時全部列出，不再只回「id 重複」。

**範圍**
- 包含：使用者、頻道（含討論串）、伺服器、身分組、訊息（需另給頻道 ID）；查不到任何東西時從 snowflake 換算的建立時間。
- 不包含：共通成員（O-02）；移除舊的 `/find`（見待決 4）。

**驗收條件**
- [ ] 輸入使用者 ID：顯示名稱、頭像、帳號建立時間、是否為 bot、是否為 Discord 官方帳號，以及與星羽的共同伺服器清單；每個伺服器列出該成員的暱稱、最高身分組、加入時間、是否被禁言、目前狀態與活動。成員快取沒載完時，共同伺服器清單上方提示「成員資料載入中，清單可能不完整」。
- [ ] 輸入頻道 ID：顯示名稱、類型、所屬類別與伺服器、建立時間。
- [ ] 輸入伺服器 ID：顯示名稱、圖示、群主、成員數、文字與語音頻道數、驗證等級、建立時間；不另外顯示同 ID 的 `@everyone` 身分組。
- [ ] 輸入身分組 ID，不必指定伺服器：顯示名稱、所屬伺服器、位置、顏色、權限值。
- [ ] 同時給頻道 ID 時查訊息：顯示內容、發送者、時間與 embed；頻道找不到時顯示「找不到這個頻道」，bot 沒有讀取權限時顯示「沒有權限讀取這則訊息」。
- [ ] 一個 ID 對到多種東西時，每一種都顯示一張卡片。
- [ ] 什麼都查不到時顯示「查無此 ID」，並附上從 ID 換算的建立時間；輸入的不是數字 ID 時顯示格式錯誤。

**實作設計**
- 後端：`ops_discord.py` 新增 `GET /dashboard/ops/discord/lookup?id=&channel_id=`。
  - `id`、`channel_id` 必須是 1 到 2^64-1 之間的整數，否則 400 `invalid_id`；`sclient.bot` 為 None 或沒就緒時回 503 `bot_unavailable`。
  - 整段查詢包成一個 coroutine 交給 `bot.submit`，在 bot 的 loop 上跑：
    - 使用者：`bot.get_user`，沒有再 `bot.fetch_user`；`NotFound` 與 ID 超出範圍造成的 400 算查不到；其他 `HTTPException`（rate limit、5xx）回該項 `{"kind": "user", "error": "unavailable"}`，畫面顯示「暫時查不到」。共同伺服器用 `user.mutual_guilds`，每個再 `guild.get_member` 取 `nick`、`top_role`、`joined_at`、`timed_out`、`raw_status`、`activity`。回應帶 `member_cache_complete = all(g.chunked for g in bot.guilds)`。
    - 頻道：頻道與討論串都用 `bot.get_channel`，只認快取中的。
    - 伺服器：`bot.get_guild`。
    - 身分組：逐一 `guild.get_role(id)`，找到第一個就停；`role.is_default()` 的跳過。
    - 訊息：有 `channel_id` 時 `bot.get_channel(channel_id)`，找不到或不是可讀訊息的頻道回該項 `{"kind": "message", "error": "channel_not_found"}`；`fetch_message` 遇到 `Forbidden` 回 `{"kind": "message", "error": "forbidden"}`，`NotFound` 算查不到。
  - 回應：`{"id", "created_at"（snowflake 換算，ISO）, "member_cache_complete", "matches": [{"kind": "user"|"channel"|"guild"|"role"|"message", ...}]}`。各 kind 的欄位比照驗收條件。
- 前端：
  - 新增 `app/dashboard/ops/discord/lookup/page.tsx`，網址帶 `?id=&channel_id=`。按下查詢時才把輸入寫進網址，頁面只在網址參數改變時查詢，所以可以直接分享或從其他頁連過來，打字時不會送請求。
  - `lib/dashboard-ops-discord.ts` 加 `LookupResult` 型別、`fetchLookup`、`lookupPath(id, channelId?)`。
  - 新增 `components/dashboard/ops/ops-lookup.tsx`：輸入區（ID、選填的頻道 ID）與各 kind 的卡片；使用者卡片的共同伺服器、伺服器卡片的群主都連回 `lookupPath`。
  - `ops-discord.tsx` 的伺服器列加「查詢」連結到 `lookupPath(guild.id)`。

**依賴**：無

**風險 / 實作注意**
- 訊息內容需要 message content intent，沒開時 `content` 是空字串，畫面要能區分「空訊息」與「讀不到內容」。
- 目前狀態與活動需要 presence intent，沒有資料時顯示「不明」，不要顯示成離線。
- `fetch_user` 打的是 Discord REST，有 rate limit。

**進度**：未完成

### O-02 bot owner 能查任兩個伺服器的共通成員

**使用者價值**：取代 `/findmember`，主伺服器不再寫死；從伺服器清單一鍵就能看該伺服器跟主伺服器的共通成員。

**範圍**
- 包含：任選兩個伺服器、預設主伺服器、成員快取沒載完時的處理、成員連到 ID 查詢。
- 不包含：移除舊的 `/findmember`（見待決 4）。

**驗收條件**
- [ ] 從 Discord 分頁的伺服器列點「共通成員」，直接看到該伺服器與主伺服器（`happycamp_guild[0]`）的共通成員清單：頭像、名稱、ID、在兩邊的加入時間。
- [ ] 頁面上可以把任一邊換成星羽所在的其他伺服器。
- [ ] 兩邊選到同一個伺服器時顯示「請選擇兩個不同的伺服器」。
- [ ] 任一邊的成員快取還沒載完時，不列清單，顯示「成員資料載入中，稍後再試」。
- [ ] 星羽離線時顯示「星羽目前離線」，不顯示選單。
- [ ] 沒有共通成員時顯示「沒有共通成員」。
- [ ] 點成員打開該成員的 ID 查詢（O-01）。

**實作設計**
- 後端：`ops_discord.py` 新增 `GET /dashboard/ops/discord/common-members?a=&b=`。
  - `b` 省略時用 `happycamp_guild[0]`；`a == b` 回 400 `same_guild`；bot 為 None 或沒就緒回 503 `bot_unavailable`；任一邊 `bot.get_guild` 找不到回 404 `guild_not_found`；任一邊 `guild.chunked` 為 False 回 409 `member_cache_loading`。
  - 交集經 `bot.submit` 在 bot 的 loop 上算，避免後台 thread 迭代成員 dict 時 bot 同時修改：兩邊成員 ID 取 `set` 交集，依 `a` 邊加入時間排序。
  - 回應：`{"a": {id, name, icon_url}, "b": {...}, "members": [{id, name, avatar_url, joined_a, joined_b}]}`。
- 前端：
  - 新增 `app/dashboard/ops/discord/common/page.tsx`，網址帶 `?a=&b=`。
  - 兩邊各一個下拉選單，選項來自既有的 `fetchOpsDiscord(1)` 的 `live.guilds`；`live` 為 null 時顯示離線訊息。
  - `ops-discord.tsx` 的伺服器列加「共通成員」連結；主伺服器那一列不顯示。
  - 成員列連到 O-01 的 `lookupPath(member.id)`。

**依賴**：O-01（成員列連到 ID 查詢頁）

**進度**：未完成

### O-03 bot owner 能在系統分頁看到 Discord bot、Twitch bot、匯流排與 DB 的運行狀態

**使用者價值**：營運頁第一次能看出各個 process 與服務本身有沒有在跑，不用登進主機看 log。

**範圍**
- 包含：新的「系統」分頁與狀態總覽區。
- 不包含：排程任務（O-04）；Sentry issue。

**驗收條件**
- [ ] 營運入口多一個「系統」分頁。
- [ ] Discord bot：顯示是否就緒、gateway latency、啟動以來的時間、伺服器數，以及成員快取是否全部載完（未載完時顯示還剩幾個伺服器）。
- [ ] Twitch bot：顯示是否在線、process 啟動以來的時間、已加入的聊天室數；5 秒內沒有回應時顯示離線。
- [ ] 訊息匯流排：顯示已連線、斷線，或未設定 Redis。
- [ ] 後台 DB：顯示 executor 執行中與排隊中的工作數，以及連線池使用中與上限。
- [ ] 每 30 秒自動更新；任一項取不到時只有該項顯示「無法取得」，其他項照常顯示；離線與無法取得分開顯示。

**實作設計**
- 後端：
  - 新增 `starServer/dashboard/ops_system.py`，`router = APIRouter(prefix="/dashboard/ops/system")`。
  - `GET /dashboard/ops/system/status` 回 `{"discord", "twitch", "bus", "db"}`，每一區都是 `{"state": "up"|"down"|"error", ...}`：`down` 是確定沒在跑（`sclient.bot` 為 None、`BotOffline`、匯流排斷線），`error` 是取資料時出錯；匯流排另有 `unconfigured`。每一區各自 try/except，一區失敗不影響其他區。
  - Discord：`bot.is_ready()`、`bot.latency`（`nan`、`inf` 轉成 null）、`len(bot.guilds)`、`sum(not g.chunked for g in bot.guilds)`、`started_at`。`starDiscord/bot.py` 的 `DiscordBot` 在第一次 `on_ready` 記下 `started_at`，之後重新 identify 不覆寫。
  - Twitch：`twitch_main.py` 啟動時記下 process 啟動時間（放在 `starServer/twitch_bot/state.py`）；`channels.py` 的 `register()` 多註冊 `bot.status` RPC，回 `{"started_at", "rooms": is_in_room 為真的聊天室數}`。`twitch_control.py` 加 `bot_status() -> BotStatus | BotOffline`，`_call` 改成 payload 可省略；`RpcHandlerError` 歸到 `error`。
  - 匯流排：`starlib/messaging/bus.py` 的 `MessageBus` 加唯讀屬性 `state`，由 `RedisConnection.configured`、`is_up` 推出 `up`、`down`、`unconfigured`。
  - DB：`db.py` 加 `executor_stats() -> {"workers", "busy", "queued"}`：`busy` 用 `_run` 前後維護的 in-flight 計數器（加 lock），`queued` 讀 `_work_queue.qsize()`，`workers` 是 `max_workers`；連線池使用中是 `pool.checkedout()`，上限是 `pool.size() + pool._max_overflow`，私有屬性一樣包在 `db.py` 裡不外流。
- 前端：
  - `ops-tabs.tsx` 的 `TABS` 加 `{ href: OPS_SYSTEM_PATH, label: "系統", active: (p) => p.startsWith(OPS_SYSTEM_PATH) }`。
  - 新增 `lib/dashboard-ops-system.ts`（`OPS_SYSTEM_PATH`、型別、`fetchSystemStatus`）、`app/dashboard/ops/system/page.tsx`、`components/dashboard/ops/ops-system.tsx`。
  - 四個區塊用一致的狀態標示：正常、離線、無法取得。在 `ops-system.tsx` 用 interval 每 30 秒呼叫 `useLoad` 的 `reload`，不改共用的 `useLoad`。

**依賴**：無

**風險 / 實作注意**：狀態端點本身不要經 `run_db`，DB executor 塞住時它還要能回應。

**進度**：未完成

### O-04 bot owner 能看到每個排程任務的下次執行時間與最近一次結果

**使用者價值**：地震、天氣、YouTube、Twitch 開台等輪詢任務壞掉時，不必等使用者回報才發現。

**範圍**
- 包含：Discord bot scheduler 上 `on_ready` 註冊的週期任務（cron、interval）。
- 不包含：`DateTrigger` 一次性 job（見待決 5）；Twitch bot 的計時器（見待決 6）。

**驗收條件**
- [ ] 系統分頁多一個「排程任務」區，每個任務一列：名稱、觸發規則（例如「每 3 分鐘」「每天 00:00」）、下次執行時間。
- [ ] 每列顯示最近一次執行的時間、結果（成功、失敗、錯過、因上一次還沒跑完而略過）與耗時；失敗時可展開看錯誤訊息。
- [ ] 啟動後還沒執行過的任務顯示「尚未執行」。
- [ ] 最近一次不是成功的任務排在最前面並醒目標示。
- [ ] 沒有註冊任何週期任務時（`debug_mode`）顯示「此環境不執行週期任務」；scheduler 沒有在跑時顯示「排程未啟動」。

**實作設計**
- 資料：見待決 1。選 B 時新增 `backup.scheduler_job_status`（`job_id` PK、`last_run_at`、`status`、`duration_ms`、`error`），每次執行 upsert 一筆，不留歷史；寫入丟到 executor，不在 listener 裡同步寫。
- 後端：
  - `starDiscord/cmds/task.py` 的 `on_ready` 裡註冊週期任務的 `add_job` 補上固定的 `id` 與可讀的 `name`；YouTube 開台通知等 `DateTrigger` job 不動。
  - 新增 `starDiscord/scheduler_status.py`：`install(scheduler)` 掛 `EVENT_JOB_SUBMITTED`、`EVENT_JOB_EXECUTED`、`EVENT_JOB_ERROR`、`EVENT_JOB_MISSED`、`EVENT_JOB_MAX_INSTANCES` listener，記錄每個 job 最近一次結果；`snapshot() -> list[JobStatus]` 取 `scheduler.get_jobs()` 中 trigger 不是 `DateTrigger` 的，合併 `next_run_time`、trigger 與記錄。`DiscordBot` 建立 scheduler 時呼叫 `install`。
  - `ops_system.py` 新增 `GET /dashboard/ops/system/jobs`，經 `bot.submit` 在 bot 的 loop 上取 `snapshot()`，回 `{"state": "up", "running": scheduler.running, "jobs": [...]}`；前端以 `running` 與 `jobs` 是否為空區分兩種提示。比照 O-03，`sclient.bot` 為 None 回 `{"state": "down"}`，`bot.submit` 出錯回 `{"state": "error"}`，前端顯示離線或無法取得。
  - trigger 轉成可讀文字放在後端，前端只顯示。
- 前端：`ops-system.tsx` 加排程任務區，`lib/dashboard-ops-system.ts` 加型別與 `fetchSystemJobs`，跟狀態總覽一起每 30 秒更新。

**依賴**：O-03（系統分頁與 `ops_system.py`）

**風險 / 實作注意**
- 只有拋出 job 的例外才會觸發 `EVENT_JOB_ERROR`；自己 `except Exception` 的 job 會顯示成功，見待決 2。
- 本機 `debug_mode` 不註冊週期任務，驗收要在非 debug 環境或暫時註冊一個測試 job。

**進度**：未完成

### O-05 bot owner 能跨頁統計並篩出 token 有問題的 Twitch 頻道

**使用者價值**：頻道清單現在只會逐列補查目前這一頁的健康度，看不出全部頻道裡有幾個授權出問題、在哪幾頁；這張卡補上跨頁的統計與篩選。

**範圍**
- 包含：清單上方的問題數統計、只看 token 有問題的篩選、每列以 DB 判定的 token 狀態。
- 不包含：改動現有的逐列 `/health` 補查，兩者並存。

**驗收條件**
- [x] 清單上方顯示 token 有問題的頻道數，依問題分類：沒有授權、缺少權限，以及待決 3 選 A 時的「授權已失效」。
- [x] 勾選「只看 token 有問題」時，只列出有問題的頻道，分頁照常運作，勾選狀態存在網址。
- [x] 只統計 `enabled` 的頻道；其他狀態的列不顯示 token 狀態。
- [x] 缺少權限的列顯示缺了哪些 scope。
- [x] 統計與篩選本身不對 Twitch 發請求；逐列的 `/health` 補查照舊。

**實作設計**
- 資料：待決 3 選 A 時，`OAuthToken` 加 `refresh_failed_at`（nullable timestamptz，精度 0 同其他時間欄位）。`OAuthToken` 在 `credentials` schema，正式機上線前手動執行 `ALTER TABLE credentials.oauth_token ADD COLUMN refresh_failed_at timestamptz(0);`，再部署程式；本機 DB 也要先加，否則讀 `OAuthToken` 的測試與功能都會 `UndefinedColumn`。
- 後端：
  - `ENABLE_SCOPES` 從 `starServer/dashboard/channel_activation.py` 搬到 `starlib/twitch_tokens.py`，`channel_activation.py` 與 `channel_health.py` 改從那裡 import。
  - `starlib/twitch_tokens.py` 新增 `token_state(token: OAuthToken | None) -> Literal["ok", "missing", "scope_missing", "revoked"]`：沒有 token 或 `refresh_token` 為空是 `missing`，`refresh_failed_at` 不為 null 是 `revoked`，scope 不含全部 `ENABLE_SCOPES` 是 `scope_missing`。判定只在這裡做。
  - `starlib/database/postgresql/client.py` 新增 `list_enabled_channel_tokens() -> list[tuple[TwitchBotJoinChannel, OAuthToken | None]]`：先用 `get_oauth_client(APIType.Twitch, BROADCASTER_CLIENT_SEQ)` 取 `credential_id`，再撈所有 `state = enabled` 且沒停權的頻道 LEFT JOIN `oauth_token`（`client_credential_id = credential_id`、`user_id = CAST(twitch_id AS text)`）。
  - `ops.py` 的 `GET /dashboard/ops/channels` 回應加 `token_problems: {"missing": n, "scope_missing": n, "revoked": n}`，每列 `enabled` 的頻道加 `token: {"state", "missing_scopes"}`；加 `?token_problem=1` 時，用 `list_enabled_channel_tokens` 全部撈出後在 Python 以 `token_state` 篩選，再依原本的排序分頁。
  - 沒有篩選時，同樣用 `list_enabled_channel_tokens` 的結果（統計本來就要全量撈），以 `twitch_id` 對應到這一頁 `enabled` 的列帶上 `token`，不另外查詢。
  - 待決 3 選 A 時，`_refresh_locked` 回 `revoked` 時寫 `refresh_failed_at = now` 並 commit，續期成功時清為 null；實況主重新授權存 token 走 `starlib/oauth/oauth_lib.py` 的 `sqldb.merge(OAuthToken(...))`，在那裡明確帶 `refresh_failed_at=None`。
- 前端：`lib/dashboard-ops.ts` 的頻道型別加 `token`、清單回應加 `token_problems`；`ops-channel-list.tsx` 加統計列與篩選勾選；`ops-channel-row.tsx` 顯示 token 狀態。

**依賴**：無

**風險 / 實作注意**
- 全部撈出再篩選的做法在已啟用頻道數千筆以下沒問題；超過時再改成 SQL 篩選。
- access token 過期是正常狀態（用到才續期），不能當成問題。

**進度**：完成
- commit：XingyuBot 35fe7e02、afb1989b、8a6ef57b；domalyze_frontend a1b8980
- 驗證：`tests/dashboard/test_ops.py::TestTokenStats`（統計、只算 enabled 且沒停權、列上的 token 與缺少的 scope、篩選與分頁、不呼叫 Twitch）、`tests/twitch/test_twitch_tokens.py`（`refresh_failed_at` 的標記與清除、`TestTokenState`）、`tests/oauth/test_save_token.py`、前端 `lib/dashboard-ops.test.ts`（網址參數）；勾選狀態存在網址、統計列與列上顯示未在瀏覽器手動驗
- 上線前：正式機先執行上面的 `ALTER TABLE`
- 實作決定：
  - 續期再次被拒時不覆寫 `refresh_failed_at`，保留第一次失敗的時間，也省去每次 `/health` 都寫一次 DB；Twitch 暫時無法回應不算失敗。
  - `oauth_lib.py` 除了 `save_token_to_db` 帶 token_data 的 `OAuthToken(...)`，`to_db_token` 與合併 `self.db_token` 的分支也清為 null：實況主啟用流程走的是 `exchange_code` → `save_token_to_db(user_id)` 這條。
  - `token_state` 的判定順序是 missing → revoked → scope_missing；另外匯出 `missing_scopes(token)`，依 `ENABLE_SCOPES` 的順序回缺少的 scope。回應的 `missing_scopes` 只在 `scope_missing` 時有值。
  - `list_enabled_channel_tokens` 在函式內 import `BROADCASTER_CLIENT_SEQ`，`twitch_tokens` 會 import `sqldb`，放頂層會循環。
  - 前端列上只在 token 有問題時顯示一行，正常時不顯示；切換篩選回到第一頁，網址用 `history.replaceState` 更新（頁碼維持不進網址）。

## 開工前待決

全部採用預設選項（2026-11-20 使用者拍板）。

1. **排程任務的最近結果存在哪裡**：APScheduler 不保存執行結果，O-04 要自己記。
   - 選項 A（已採用，2026-11-20）：存在 bot process 的記憶體。代價：重啟後全部變「尚未執行」，剛重啟時看不出重啟前哪些任務一直在失敗。
   - 選項 B：每個任務一列存進 DB，每次執行 upsert。代價：多一張表；listener 在 bot loop 上同步執行，寫入要另外丟到 executor；每分鐘的 `add_voice_time` 每分鐘寫一次 DB。

2. **自己吞掉例外的排程任務怎麼處理**：`settle_website_link_rate` 等任務自己 `except Exception` 只記 log，listener 收不到失敗，O-04 會顯示成功。
   - 選項 A（已採用，2026-11-20）：O-04 只看拋出的例外，有吞例外的任務不特別處理。代價：這些任務壞掉時頁面仍顯示成功，正是最需要被看見的情況。
   - 選項 B：O-04 一併把 `task.py` 裡吞例外的任務改成記 log 後重新拋出。代價：要逐一確認重新拋出後不影響其他行為（例如一個頻道的通知失敗不能讓後續頻道也中斷），O-04 範圍變大。

3. **O-05 要做到什麼程度**：頻道清單已經會逐列自動查 `/health`，看得到目前這一頁的授權失效；O-05 補的是跨頁統計與篩選。refresh token 失效目前只寫 log，DB 裡看不出來。
   - 選項 A（已採用，2026-11-20）：做 O-05，並在 `OAuthToken` 加 `refresh_failed_at` 記下續期失敗。代價：一次手動 `ALTER TABLE`；web 與 Twitch bot 兩個 process 的續期都會寫這欄；只有實際嘗試續期後才會標記，閒置頻道要等下次用到（包括有人打開清單觸發 `/health`）。
   - 選項 B：做 O-05，但只用 DB 現有欄位判斷沒有授權與缺少權限。代價：最常見的實況主撤銷授權不會出現在統計裡，跨頁統計的價值打折。
   - 選項 C：不做 O-05，維持現有的逐列健康度。代價：要知道哪些頻道有問題只能一頁一頁翻。

4. **舊的 `/find`、`/findmember` 指令怎麼處理**
   - 選項 A（已採用，2026-11-20）：O-01、O-02 不動舊指令，網頁版穩定後再另外移除。代價：兩套功能並存一段時間，舊指令的 bug（例如 `/find` 在 DM 呼叫時 `ctx.guild` 為 None）不會被修。
   - 選項 B：O-01、O-02 完成時一併移除舊指令與 `help.py` 的說明。代價：網頁版有問題時沒有備援，要在 Discord 查只能回頭加回來。

5. **一次性排程要不要顯示**：抽獎、投票結束、YouTube 開台通知都是 `DateTrigger` 一次性 job。
   - 選項 A（已採用，2026-11-20）：O-04 只列週期任務。代價：抽獎或投票沒有按時結束時，在營運頁看不出它是否還排在 scheduler 上。
   - 選項 B：另一區列出一次性 job 與預定時間。代價：O-04 多一個區塊；投票與影片多時清單會很長，要加分頁或只列最近的。

6. **Twitch bot 的計時器要不要算進排程任務**：Twitch bot 的聊天室計時器（`starServer/twitch_bot/timers.py`）在另一個 process，不走 APScheduler。
   - 選項 A（已採用，2026-11-20）：O-04 只做 Discord bot 的排程。代價：Twitch 計時器停擺時營運頁看不出來，只能等實況主回報。
   - 選項 B：O-04 經新的 RPC 一併顯示 Twitch 計時器的 ticker 是否在跑與最近一次觸發。代價：要動 Twitch process 並多一個 RPC 方法，O-04 範圍變大。
