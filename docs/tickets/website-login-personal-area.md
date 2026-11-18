# 星羽網站：登入整合與個人區 任務拆解

規格書：
- [docs/spec/server-dashboard-spec.md](../spec/server-dashboard-spec.md)〈登入與 session〉〈伺服器清單〉〈邀請 bot〉
- [docs/spec/personal-area-spec.md](../spec/personal-area-spec.md)

本檔取代原本的 `dashboard-domalyze-login.md`。

## 現況與前提

- 技術棧：後端是 XingyuBot 的 FastAPI web 服務（`starServer/`），與 bot 同一個行程，經 `sclient.bot.submit` 在 bot 的事件迴圈上讀 Discord 物件；資料庫是 PostgreSQL（`stardb`），SQLModel，沒有 migration 工具，既有表的欄位異動要手寫 SQL；前端是 domalyze_frontend 的 Next.js `main` 分支，後台頁面都是 client component，經 `lib/dashboard-api.ts` 的 `dashboardFetch` 呼叫 API；身分來自 domalyze-identity（Hydra，`auth.domalyze.net`）。
- 既有相關機制：
  - 登入：`starServer/dashboard/auth.py` 的 `/to/dashboard-login` 以 `identify guilds` scope 導向 Discord，`/oauth/discord` 依 `dashboard_oauth` cookie 的 `purpose` 分流，`_handle_login` 存 `OAuthToken` 並建立 session。`sanitize_next` 只接受 `/dashboard` 開頭的路徑。
  - session：`starServer/dashboard/session.py`，`DashboardSession` 只有 Discord ID、名稱、頭像，30 天滑動；`require_session` 是所有後台端點的 dependency。
  - 權限：`starServer/dashboard/guilds.py` 用使用者的 Discord token 抓 `/users/@me/guilds`，10 分鐘快取；`guild_perms`、`can_enter`、`ENTRY_BITS` 給 `access.py` 的 `require_section` 與 `invite.py` 使用。`list_guilds` 回 `invited`、`not_invited` 兩組。token 失效時拋 `reauth_required`。
  - 邀請：`starServer/dashboard/invite.py` 的 `/to/dashboard-invite`（purpose=invite，存 token、等 bot 看到伺服器後導向）；`starServer/bot_website.py` 的 `/to/discordbot` 是官網用的統一邀請入口，回到 `/oauth/discord` 時由 `_oauth_discord_fallback` 顯示授權完成頁。兩者用同一個 Discord OAuth client（`config.DISCORD_OAUTH_SEQ = 4`）。
  - 身分：`starlib/identity/resolver.py` 的 `resolve_identity` 由 Discord ID 取得 `BotIdentity`（`user_id`、`is_formal`），查無此人時發臨時 ID，正式 ID 的重查間隔是 `IDENTITY_TTL_SECONDS`（3600 秒），臨時轉正與合併時搬資料（`UserRepository.save_discord_identity` 的 `merge_from`）。`starlib/identity/client.py` 的 `DomalyzeIdentityClient` 有 `find_by_discord`、`find_by_account_id`，`Account` 目前只解析 Twitch 與 Minecraft passport。auth server 內部 API 另有 `GET /v1/accounts?username=` 可用域民代號查人。
  - bot 用 `discord.Intents.all()`，成員快取完整。
  - 個人資料：`UserPoint`、`PetRepository.get_pet`、`VoiceTime`、`WarningRepository.get_warnings`、`UserPoll`（對 `Poll`、`PollOption`）、`UserBet`（對 `Bet`）、`GiveawayUser`（對 `Giveaway`，`user_id` 存 Discord ID）以 Discord ID 為鍵；`MusicPlaylistRepository`、`DriveShare`、`NetBirdBinding` 以 `user_id`（UUID）為鍵。`/drive` 在 `starDiscord/cmds/command.py`，`/game netbird_setup`、`/game netbird` 在 `starDiscord/cmds/system_game.py`，`/playlist` 在 `starDiscord/cmds/music.py`。
  - 路由：shark-ansible 的 `roles/shark_home/files/dynamic/routes.yml` 只把 `api.domalyze.net` 的 `/oauth/`、`/callback/`、`/to/`、`/dashboard/` 轉給 XingyuBot；新端點都放在這些前綴下，不必改路由。
  - 前端：`app/dashboard/page.tsx` 是伺服器清單，`app/dashboard/layout.tsx` 載入 `/dashboard/me`，`components/dashboard/dashboard-header.tsx` 是登入後頁首，`components/header.tsx` 是官網 header（目前有「管理後台」連結）。
- 這次會動到的既有部位：XingyuBot 的 `starServer/dashboard/`（`auth.py`、`session.py`、`guilds.py`、`access.py`、`sections.py`、`invite.py`、`config.py`、`__init__.py`，新增多個模組）、`starServer/bot_website.py`、`starlib/identity/client.py`、`resolver.py`、`twitch.py`、`starlib/database/postgresql/models.py`、`client.py`、`starlib/settings.py`、`.env.example`、`starDiscord/cmds/command.py`、`system_game.py`、`music.py`、`owner.py`、`test/test_dashboard_*.py`（共用 fixture 在 `test/test_dashboard_guilds.py`）；domalyze_frontend 的 `lib/dashboard-api.ts`、`app/dashboard/`（含 `layout.tsx`、`guilds/[id]/layout.tsx`）、`components/dashboard/`、`components/header.tsx`，新增 `app/dashboard-login/`、`app/u/`；domalyze-identity 的 `identity-clients.toml`、`identity-clients.preview.toml`；shark 主機的 `/etc/xingyubot/env`。
- 已定案的技術前提：
  - session 的身分一律是一個 Discord 帳號，析域帳號是附帶欄位。網站不保存使用者的 Discord 授權，權限由 bot 依成員快取判斷。
  - 個人區的資料與操作由 XingyuBot 提供，不經過 domalyze-api。auth server 的程式不改，只新增 OIDC client 設定。
  - 個人區操作逐項立即生效；歌單的衝突以整份歌單為單位。

## 實作順序總覽

| # | 卡號 | 進度 | 標題 | 依賴 | 並行組 | 備註 |
|---|---|---|---|---|---|---|
| 1 | T-01 | 已完成 | 管理員不必授權讀取伺服器清單，也能管理伺服器 | 無 | — | 骨架切片 |
| 2 | T-02 | 已完成 | 管理員從後台邀請 bot 走統一流程，完成後回到後台 | T-01 | A | |
| 3 | T-03 | 已完成 | 已連結析域帳號的人用 Discord 登入，session 帶上析域帳號並跟隨狀態 | T-01 | A | |
| 4 | T-04 | 已完成 | 域民能用析域帳號登入網站 | T-02、T-03 | — | |
| 5 | T-05 | 已完成 | 登入的人在個人區看到自己的帳號、積分與寵物 | T-02、T-04 | — | 個人區骨架；建好 T-06～T-11 的檔案空位與 T-07、T-10 的資料表異動 |
| 6 | T-06 | 已完成 | 個人區看得到語音時數、警告、投票、賭盤與抽獎紀錄 | T-05 | C | |
| 7 | T-07 | 已完成 | 域民能在網頁管理歌單 | T-05 | C | |
| 8 | T-08 | 已完成 | 域民能在網頁設定雲端資料夾共用 | T-05 | C | |
| 9 | T-09 | 已完成 | 域民能在網頁查看 NetBird 節點並取得安裝指令 | T-05 | C | |
| 10 | T-10 | 已完成 | 擁有者查得到每週的析域帳號連結率 | T-05 | C | |
| 11 | T-11 | 已完成 | 域民能開啟公開頁並選擇公開的內容 | T-06、T-07 | — | |

並行組 C 中，T-06 與 T-07 都改 `starlib/database/postgresql/client.py`，但改的是不同的類別與方法（T-06：`WarningRepository`、`PollRepository`、`BetRepository` 與語音查詢；T-07：`MusicPlaylistRepository` 與 `UserRepository.merge_user_data`），不改同一個方法；合併時依卡號順序 rebase。`models.py` 的異動已集中在 T-05。

## 任務卡

### T-01 管理員不必授權讀取伺服器清單，也能管理伺服器

**使用者價值**：管理員登入時只需讓星羽確認身分，網站不再保存能讀取他伺服器清單的授權；權限被拔掉時立即生效。

**範圍**
- 包含：Discord 登入只要 `identify`、不存 token；權限與伺服器清單改由 bot 判斷；清單只列 bot 已在的伺服器；登出只刪 session；移除 `reauth_required`。
- 不包含：邀請流程與既有 token 的清除（T-02）；登入頁與析域登入（T-04）。

**驗收條件**
- [x] 用 Discord 登入時，Discord 授權頁只要求確認身分，不要求讀取伺服器清單；完成後回到原本要去的頁面。
- [x] 登入後清單只出現 bot 已在、且自己符合進入條件的伺服器，依名稱排序，顯示圖示與名稱；bot 不在的伺服器都不出現。
- [ ] 沒有任何可顯示的伺服器時，清單頁顯示說明與邀請入口。
- [ ] 在 Discord 拔掉某管理員的權限後，他的下一次存檔被拒絕，重新打開清單時該伺服器不再出現。
- [ ] 把 bot 踢出某伺服器後打開清單，該伺服器不出現；重新邀請後原本的設定都還在。
- [x] 在兩台裝置登入，於其中一台登出後，另一台也需要重新登入；登出後 Discord 端的授權沒有被撤銷。
- [ ] 在 Discord 授權頁按取消，回到官網首頁。
- [ ] 通知頁開著時把 bot 踢出該伺服器，接著按存檔，看到 bot 已不在的提示並回到清單。

**實作設計**
- 資料：不異動。
- 後端：
  - `auth.py`：`LOGIN_SCOPES` 改成 `["identify"]`；`_handle_login` 不再呼叫 `save_token_to_db`；`logout` 移除 `_delete_token`、`revoke_token` 與 `user_lock`，只留 `delete_user_sessions` 與清 cookie。`_delete_token`、`user_lock`、`_user_locks`、`on_auth_change`、`_notify_auth_change` 都沒有其他用途，一併移除。
  - `guilds.py`：移除 `_cache`、`_fetch`、`_refresh`、`_load_token`、`get_user_guilds`、`CACHE_TTL`、`_reauth`、`invalidate`，並清掉 `invite.py` 等呼叫端。`guild_perms(user_id, guild_id)` 簽名不變，改在 guilds.py 內直接用 `bot.submit` 在 bot 事件迴圈上取 `guild.get_member(int(user_id))`（不 import `access.py`，避免循環匯入）：bot 未 ready 拋 `503 bot_unavailable`；bot 不在該伺服器拋 `404 bot_not_in_guild`，讓 `require_section` 與 `sections.py` 照舊回「bot 已不在」而不是「沒有權限」；不是成員回 `GuildPerms()`；是成員時 `bits = member.guild_permissions.value`，`full = guild.owner_id == member.id or member.guild_permissions.administrator`。
  - `list_guilds`：bot 未 ready 拋既有的 `503 bot_unavailable`；在 bot 事件迴圈上走訪 `bot.guilds`，取使用者是成員且 `can_enter` 的伺服器，回 `{"guilds": [{id, name, icon_url}]}`，依名稱 casefold 排序。`refresh` 參數移除。`_icon_url` 改用 `guild.icon`。
  - `access.py`：`require_section` 的錯誤說明移除 `reauth_required`。
  - 測試：`test/test_dashboard_guilds.py` 的共用 fixture（`discord`、`seed_token`）改成假 bot 的伺服器與成員資料，所有引用它的 `test/test_dashboard_*.py` 跟著改；`test_dashboard_invite.py`、`test_dashboard_sections.py` 直接操作 `guilds._cache` 的地方改用新 fixture。`test/test_dashboard_auth.py` 的登出測試改成驗證不撤銷。新增 `guild_perms` 的成員、非成員、擁有者、Administrator、bot 不在（404）測試。
- 前端：
  - `app/dashboard/page.tsx`：只有一組清單，移除「未邀請」分組、手動重新整理與 `refresh` 參數；邀請入口暫時維持 `/to/dashboard-invite`（T-02 換掉）。
  - `lib/dashboard-api.ts`：`dashboardFetch` 移除 `reauth_required` 分支，`session_expired` 照舊。

**依賴**：無

**風險 / 實作注意**
- `guild.get_member` 依賴成員快取；bot 剛啟動、快取未齊時可能誤判非成員。`bot.is_ready()` 之後才判斷，與既有 `bot_guild_ids` 一致。
- `invite.py` 的 `_same_account_target` 用 `guild_perms`，改完後它的權限來源跟著換成 bot 判斷；它在 `DashboardError` 時導回清單，bot 還沒看到伺服器的情況已由 `_wait_for_bot` 先處理。T-02 前邀請流程仍可用，但仍會存 token。

**進度**：已完成。XingyuBot `481a806`、`0237754`、`ff71edd`；domalyze_frontend `ca8bcd8`。未勾的驗收條件需在真實 Discord 與瀏覽器上人工驗證。

### T-02 管理員從後台邀請 bot 走統一流程，完成後回到後台

**使用者價值**：網站只剩一條邀請流程；從後台邀請完成後直接進入該伺服器，網站也不再保存任何 Discord 授權。

**範圍**
- 包含：`/to/discordbot` 支援從後台發起並回到後台；移除 `/to/dashboard-invite`；上線時刪除既有的後台 Discord token。
- 不包含：官網首頁的邀請流程，完成頁維持現狀。

**驗收條件**
- [ ] 從清單頁按邀請，進入 Discord 的邀請頁，自行選擇伺服器。
- [x] 符合進入條件的帳號邀請完成後，回到網頁時直接在該伺服器頁；bot 還沒看到該伺服器時回到清單並提示稍後重新整理。
- [x] 不符合進入條件的帳號邀請完成後，回到清單並看到需要哪些權限的提示。
- [x] 在 Discord 邀請頁取消，回到伺服器清單。
- [x] 未登入時從官網首頁邀請，完成後看到的頁面與現在相同。
- [ ] 上線後資料庫裡沒有後台 Discord client 的 `OAuthToken`，之後登入、邀請也不再寫入。

**實作設計**
- 資料：上線時執行一次 `DELETE FROM credentials.oauth_token WHERE client_credential_id = <DISCORD_OAUTH_SEQ 對應的 credential id>;`（表名以 `TokensSchema` 實際位置為準），寫進部署步驟。只刪除，不呼叫 Discord 撤銷。
- 後端：
  - `bot_website.py` 的 `/to/discordbot` 新增選填 `origin`。帶 `origin` 時視為從後台發起：沿用 `auth.sanitize_origin`，寫 `dashboard_oauth` cookie（purpose=`invite`，`next` 固定 `/dashboard`），scope 與權限沿用現有邀請連結（`identify`、`applications.commands.permissions.update`、`bot`，permissions=8）；不帶 `origin` 時行為不變。
  - `invite.py`：移除 `/to/dashboard-invite`；`_handle_invite` 不再交換 code、不存 token；以 session 的 Discord 帳號判斷去向，沒有 session 時沿用 `_login_redirect`（T-04 改成導向登入頁）。Discord 回傳的 `guild_id` 沿用 `_same_account_target` 的等待與權限判斷。通知參數 `invite_pending`、`need_permissions` 照舊。
- 前端：`app/dashboard/page.tsx` 的 `inviteUrl` 改連 `/to/discordbot?origin=`，不再帶 `guild_id`。

**依賴**：T-01（權限改由 bot 判斷後，邀請完成才不需要使用者 token）

**風險 / 實作注意**：Discord 邀請授權回來時登入的可能是另一個 Discord 帳號；去向以 session 的帳號為準，不改 session。

**進度**：已完成。XingyuBot `7351b95`；domalyze_frontend `058d012`。未勾的驗收條件需在真實 Discord 上人工驗證。上線後執行：`DELETE FROM credentials.oauth_token t USING credentials.credential c WHERE t.client_credential_id = c.id AND c.source = 1 AND c.source_seq = 4;`（`source = 1` 是 `APIType.Discord`）。

### T-03 已連結析域帳號的人用 Discord 登入，session 帶上析域帳號並跟隨狀態

**使用者價值**：連結析域帳號的人不論怎麼登入都能用需要析域帳號的功能；帳號被停權、解除連結或合併後，網站在 60 秒內跟上。

**範圍**
- 包含：`DashboardSession` 新增析域帳號欄位；Discord 登入時反查；每次使用時重新確認，Discord 登入的 session 只降級或升級；`Account` 解析 Discord passport；`/dashboard/me` 回傳析域帳號。
- 不包含：析域登入與它的失效規則（T-04）；個人區畫面（T-05）。

**驗收條件**
- [x] 已連結析域帳號的 Discord 用 Discord 登入，`/dashboard/me` 回傳該域民的代號。
- [x] 未連結的 Discord 登入，`/dashboard/me` 的析域帳號為空，伺服器後台照常可用。
- [x] 登入後才到析域帳號頁連結這個 Discord，滿 60 秒後的下一次請求 `/dashboard/me` 帶上域民代號，不必重新登入。
- [x] 所連結的域民被停權或解除連結這個 Discord，滿 60 秒後析域帳號變為空，伺服器後台繼續可用。
- [x] 域民被合併、存續帳號仍連結這個 Discord，session 改帶存續帳號。
- [x] auth server 暫時不可用時，session 維持原本的析域帳號，請求不失敗。

**實作設計**
- 資料：`DashboardSession` 新增可為 null 的 `account_id`（UUID）與 `via_domalyze`（boolean，預設 false，表示這個 session 是析域登入建立的，T-04 使用）。部署前手動執行 `ALTER TABLE credentials.dashboard_session ADD COLUMN account_id uuid, ADD COLUMN via_domalyze boolean NOT NULL DEFAULT false;`。
- 後端：
  - `starlib/identity/client.py`：`Account` 新增 `discord_passports`，`_parse_account` 解析 `provider == "discord"`；新增 `find_by_username(username)`（`GET /v1/accounts?username=`，T-11 使用）。
  - `starlib/identity/resolver.py`：`_get_directory` 改名為公開的 `get_directory`，`starlib/identity/twitch.py` 的 import 一併改。
  - `session.py`：`SessionInfo` 新增 `account_id: UUID | None`、`account_username: str | None`、`via_domalyze: bool`、`discord_ids: tuple[int, ...]`、`stale: bool`；`create_session` 新增選填的 `account_id`、`via_domalyze`。
  - 新增 `session.py` 內的帳號跟隨：`require_session` 在 `_touch` 之後，距上次確認超過 60 秒才重新確認。確認結果以 session ID 為 key 存在記憶體，內容是 `checked_at`、`account_id`、`account_username`、`discord_ids`（該域民 `discord_passports` 的 Discord ID，依數值由小到大；沒有析域帳號時為空）、`stale`（布林）：
    - `via_domalyze` 為 false：`find_by_discord(discord_id)`，查到且未停權就寫入該 `account_id` 與上述欄位（含合併後的存續帳號），否則 `account_id` 寫 null。
    - `via_domalyze` 為 true：留給 T-04。
    - `DirectoryUnavailable` 時：記憶體有舊結果就沿用並設 `stale = true`；沒有（例如重啟後）就以資料庫的 `account_id` 為準，`account_username` 為 null、`discord_ids` 只含 session 的 Discord、`stale = true`。比照 `resolver.py` 的 backoff，60 秒內不再打 auth server。
  - `SessionInfo` 另帶 `discord_ids` 與 `stale`，供 T-05 的 `personal_scope` 使用，不另外打 auth server。
  - 有析域帳號但代號未知（上述重啟後的情況）時，`/dashboard/me` 的 `account` 回 `{username: null}`；前端顯示「代號暫時無法載入」，公開網址不顯示（T-05、T-11 照此處理）。
  - `auth.py` 的 `_handle_login`：建立 session 後立即做一次確認，`/dashboard/me` 回傳新增 `account`（`{username}` 或 null）。
- 前端：`components/dashboard/dashboard-header.tsx` 的 `DashboardUser` 型別加上 `account`，畫面不變。

**依賴**：T-01（同改 `auth.py` 的 `_handle_login` 與 `session.py`）

**風險 / 實作注意**：`DomalyzeIdentityClient` 預設逾時 1.5 秒，需要重新確認的請求最多多等這麼久。

**進度**：已完成。XingyuBot `1b528e7`、`9a1ebea`、`4a4eb54`、`f6af79c`；domalyze_frontend `189badc`。部署順序：先在正式 DB 執行實作設計中的 ALTER，再部署程式（`models.py` 已含新欄位，沒先 ALTER 後台會整個壞掉）。本機 dev DB 已執行。

### T-04 域民能用析域帳號登入網站

**使用者價值**：域民用析域帳號就能登入，連結的 Discord 不必事先授權過網站；連結多個 Discord 時可以選擇。

**範圍**
- 包含：登入頁（Discord 與析域並列）、析域 OIDC 登入、多個 Discord 的選擇畫面、析域登入 session 的失效規則、OIDC client 設定與環境變數。
- 不包含：登入後換 Discord（規格決定登出再登入）。

**驗收條件**
- [ ] 未登入打開需要登入的任一頁，出現登入頁，可選 Discord 或析域帳號；完成後回到原本要去的頁面。
- [x] 析域帳號連結一個 Discord：析域登入後直接以該 Discord 進入，過程沒有 Discord 授權畫面；該 Discord 從沒登入過網站也一樣。
- [x] 連結兩個以上 Discord：出現選擇畫面，每個顯示頭像與名稱；選了之後以該 Discord 進入並回到原本要去的頁面。直接呼叫 API 送出不在選項裡的 Discord ID 被拒絕。
- [x] 沒有連結 Discord：回到登入頁，提示先到析域帳號頁連結 Discord，或改用 Discord 登入。
- [ ] 停權的域民無法用析域登入：auth server 在登入步驟擋下時停在它的「已被停權」頁；帶 `access_denied` 回到網站時，登入頁提示無法以此帳號登入。
- [x] auth server 或 Hydra 暫時不可用：回到登入頁提示稍後再試；同時間 Discord 登入仍可用。
- [x] 在析域登入頁或選擇畫面停留超過 10 分鐘，或 `state` 不符：回到登入頁提示已逾時，重新開始後仍回到原本要去的頁面。
- [x] 用析域登入後，域民被停權或解除連結這個 Discord：滿 60 秒後的下一次請求回到登入頁。
- [ ] 伺服器後台的表單在編輯途中 session 過期，用析域重新登入回同一個 Discord，未存內容還在；換成另一個 Discord 時，未存內容丟棄並回到登入後首頁。
- [ ] 登入頁與選擇畫面在 360px 寬時可以完整操作。

**實作設計**
- 設定與部署：
  - domalyze-identity 的 `identity-clients.toml` 新增 `xingyu-website`：`client_name = "星羽網站"`，`first_party = true`，scope `openid profile`，`redirect_uris = ["https://api.domalyze.net/oauth/domalyze"]`，secret 由 Hydra 產生，以 `domalyze-identity client-secret xingyu-website` 取得；`identity-clients.preview.toml` 同步，redirect URI 用 `https://localhost:14000/oauth/domalyze`。
  - `starlib/settings.py` 新增 `DASHBOARD_OIDC_CLIENT_ID`、`DASHBOARD_OIDC_CLIENT_SECRET`、`DASHBOARD_OIDC_REDIRECT_URI`（`API_WEBSITE=true` 時必填，比照既有欄位）與 `DASHBOARD_OIDC_ISSUER`（預設 `https://auth.domalyze.net`）；`.env.example` 同步；補必填驗證的測試。discovery 結果成功後快取在記憶體，失敗不快取。
- 後端：新增 `starServer/dashboard/domalyze_login.py`，掛在 `to_router` 與 `router`：
  - `GET /to/dashboard-domalyze-login?next=&origin=`：沿用 `sanitize_next`、`sanitize_origin`；`dashboard_oidc` cookie 存 `state`、PKCE verifier、`next`、`origin`，10 分鐘，屬性同 `dashboard_oauth`，讀出時重新驗證；authlib `AsyncOAuth2Client`，PKCE S256，`client_secret_basic`。discovery 失敗導回登入頁帶 `domalyze_unavailable`。
  - `GET /oauth/domalyze`：驗 `state`；`error=access_denied` 帶 `domalyze_denied`，其他 error 或缺 `code` 帶 `domalyze_unavailable`；換 token、取 `/userinfo` 的 `sub`（`account_id`）；`find_by_account_id` 查無或 `suspended` 帶 `domalyze_denied`；取 `discord_passports`：0 個帶 `domalyze_no_discord`；1 個直接 `create_session(..., account_id=, via_domalyze=True)`，帶入舊 session，導回 `origin + next`；多個存待選資料（記憶體，隨機 key，10 分鐘，含 `account_id`、候選的 Discord ID、`next`、`origin`、舊 session ID），設 `dashboard_pick` cookie，導向 `origin + /dashboard-login/select?next=`。`state` 不符或 cookie 過期帶 `domalyze_expired`。成功與失敗都刪 `dashboard_oidc`。
  - 候選與 session 的名稱、頭像：在 bot 事件迴圈上以 `bot.get_user` 取得，取不到時呼叫 `fetch_user`；仍失敗時名稱用 Discord ID、頭像為 null（`DashboardSession.name` 不可為 null），選擇畫面同樣只顯示 Discord ID。
  - `GET /dashboard/login/candidates`、`POST /dashboard/login/select`（`{discord_user_id}`，沿用 `csrf.py` 的 Origin 檢查）：待選資料不存在回 401 `pick_expired`；ID 不在清單回 400 `invalid_candidate`；成功建立 session、刪除待選資料與 cookie，回 `{redirect}`。
  - `session.py` 的帳號跟隨補上 `via_domalyze` 為 true 的分支：`find_by_account_id(account_id)` 查無、`suspended`，或 `discord_passports` 不含此 Discord 時刪除這筆 session，設 `dashboard_clear_cookie`，拋 `401 session_expired`；合併時改寫成存續帳號的 `account_id`；通過時同樣寫入 T-03 的記憶體項目（`account_username`、`discord_ids`）；`DirectoryUnavailable` 放行，處理方式同 T-03。
- 前端：
  - 新增 `app/dashboard-login/page.tsx`（放在 `app/dashboard/` 外，避免被 layout 的 `/dashboard/me` 擋住）：兩個按鈕分別連 `/to/dashboard-login` 與 `/to/dashboard-domalyze-login`，都帶 `next` 與 `origin`；導向前把 `next` 存進 sessionStorage，收到 `domalyze_expired` 而網址沒有 `next` 時從 sessionStorage 取回，登入完成或改選另一種方式時清掉；讀 `notice` 顯示對應提示後從網址移除。
  - `invite.py` 的 `_login_redirect` 改導向前端的 `/dashboard-login`。
  - 新增 `app/dashboard-login/select/page.tsx`：載入候選、顯示頭像與名稱、送出選擇；`pick_expired` 導回登入頁帶 `domalyze_expired` 與 `next`；`invalid_candidate` 顯示錯誤並重新載入。
  - `lib/dashboard-api.ts` 的 `redirectToLogin` 改導向 `/dashboard-login?next=`，`beforeLoginRedirect` 與 `LAST_USER_KEY` 照舊。

**依賴**：T-03（`account_id`、`via_domalyze` 欄位與帳號跟隨）、T-02（同改 `invite.py`）

**風險 / 實作注意**
- `dashboard_oidc` cookie 沒有簽章，`state` 比對與 `next`、`origin` 的再次驗證都不能省。
- 上線順序：部署 auth server 的 client → 取得 secret → 寫入 `/etc/xingyubot/env` → 部署 XingyuBot → 部署前端。新欄位必填，env 沒先加 XingyuBot 會起不來。
- 待選資料在記憶體，服務重啟後失效，走 `pick_expired`。

**進度**：已完成。XingyuBot `de054cd`、`9d1b93f`、`5e8085c`、`fb02842`、`f9e6c51`；domalyze_frontend `0ee496d`、`d7d6f5c`；domalyze-identity 分支 `xingyu-website-client` 的 `5fc695b`。未勾的驗收條件需在真實瀏覽器與 auth server 上人工驗證。上線順序：合併並部署 domalyze-identity 的 client → `domalyze-identity client-secret xingyu-website` 取得 secret → 在 `/etc/xingyubot/env` 加上 `DASHBOARD_OIDC_CLIENT_ID`、`DASHBOARD_OIDC_CLIENT_SECRET`、`DASHBOARD_OIDC_REDIRECT_URI` → 部署 XingyuBot → 部署前端。

### T-05 登入的人在個人區看到自己的帳號、積分與寵物

**使用者價值**：每個登入的人都有自己的首頁，看得到積分與寵物；沒有析域帳號的人看得到連結後能多做什麼。

**範圍**
- 包含：個人區頁面與路由調整（登入後首頁改成個人區、伺服器清單移到 `/dashboard/guilds`）；登入後頁首的「我的」「伺服器」；官網 header 的登入狀態；帳號區塊與連結入口；積分、寵物；需要析域帳號的區塊的鎖定外框；可見範圍的共用判斷。
- 不包含：紀錄（T-06）、歌單（T-07）、雲端資料夾共用（T-08）、NetBird（T-09）、公開設定（T-11）。

**驗收條件**
- [ ] 登入後沒有指定要去的頁面時進入個人區；頁首有「我的」「伺服器」，「伺服器」打開原本的伺服器清單。
- [ ] 官網行銷頁未登入時 header 顯示「登入」，登入後顯示頭像，點下進入個人區。
- [ ] 沒有連結析域帳號的 Discord 登入，個人區顯示目前的 Discord、自己的積分與寵物；工具與公開設定的位置顯示鎖住，標示連結析域帳號後可用，附另開分頁前往 `auth.domalyze.net` 的入口。
- [x] 連結兩個 Discord 的域民，不論用哪個登入，帳號區塊顯示域民代號與兩個 Discord，積分與寵物依 Discord 分開顯示。
- [x] 積分與 `/user`、寵物與 `/pet` 查到的一致；沒有寵物時顯示沒有寵物。
- [x] auth server 暫時查不到連結了哪些 Discord 時，只顯示目前這個 Discord 的資料，並提示其他帳號的資料暫時無法載入。
- [x] 舊網址 `/dashboard?notice=need_permissions` 等清單通知仍能在伺服器清單看到。
- [x] 在 Discord 邀請頁取消、沒有權限打開伺服器頁、bot 已不在伺服器時，都回到伺服器清單，不是個人區。
- [ ] 360px 寬時可以完整操作。

**實作設計**
- 資料：不異動。
- 後端：新增 `starServer/dashboard/personal.py`：
  - 介面（T-06～T-11 共用）：`async def personal_scope(info: SessionInfo) -> PersonalScope`，只讀 `SessionInfo`（T-03 的記憶體結果），不另外打 auth server。`PersonalScope` 欄位：
    - `account_id: UUID | None`、`account_username: str | None`。
    - `discord_ids: list[int]`：帶析域帳號且 `info.discord_ids` 非空時用它（依 Discord ID 由小到大）；否則只有 session 的 Discord。
    - `partial: bool`：`account_id` 不為 null 且 `info.stale` 為 true、`info.discord_ids` 只有 session 的 Discord 時為 true。
    - `tool_user_id: UUID | None`：工具類資料（歌單、雲端資料夾共用、NetBird）讀寫用的 user_id。帶析域帳號時是 `account_id`；沒有時是 `resolve_identity(session 的 Discord, create=False)` 的 `user_id`（臨時 ID，唯讀），查無紀錄為 None，遇到 `IdentityUnavailable` 也為 None 並設 `tool_unavailable = true`。
    - `tools_writable: bool`：等於 `account_id is not None`。
    - `tool_unavailable: bool`：見上；為 true 時工具區塊顯示暫時無法載入。
  - `require_personal(write: bool = False)` dependency：`write=True` 且 `tools_writable` 為 false 時拋 `403 domalyze_required`。
  - `GET /dashboard/personal/overview`：回 `{account: {username} | null, partial, discords: [{id, name, avatar_url, points: {...}, pet: {...} | null}]}`；名稱與頭像經 bot 的 `get_user`／`fetch_user`；積分欄位與名稱以 `/user`（`starDiscord/cmds/system_user.py`）顯示的為準，寵物以 `/pet` 為準。
  - `auth.sanitize_next` 的預設值維持 `/dashboard`（此後代表個人區）。原本意思是「回清單」的導向都改成 `/dashboard/guilds`：`invite.py` 的 `_handle_invite` 取消分支、`_same_account_target` 的無 `guild_id` 與 `DashboardError` 分支與兩個 `notice` 導向。
  - 後端模組先建好 T-06～T-11 的空檔與 router 登記（`personal_records.py`、`personal_playlists.py`、`personal_drive.py`、`personal_netbird.py`、`personal_link_click.py`、`public_profile.py`），各卡只改自己的檔案。
  - 先做好 T-07、T-10 的資料表異動，讓同一並行組的卡不同時改 `models.py`：`MusicPlaylist` 新增 `version`（遞增邏輯屬 T-07），`BasicSchema` 新增 T-10 的 `website_weekly_activity`、`website_link_click`（欄位見 T-10）。`version` 的 `ALTER TABLE` 寫進部署步驟。
- 前端：
  - `app/dashboard/page.tsx` 改成個人區；原本的清單搬到 `app/dashboard/guilds/page.tsx`；`app/dashboard/page.tsx` 收到 `notice` 參數時轉到 `/dashboard/guilds` 並保留參數；`app/dashboard/guilds/[id]/layout.tsx` 的「伺服器清單」返回連結改指 `/dashboard/guilds`。
  - 新增 `components/dashboard/personal/`：帳號區塊、資產區塊，以及給 T-06～T-11 共用的區塊外框 `PersonalSection`（標題、內容；`locked` 時顯示鎖定說明與連結入口）。個人區頁面依固定順序放好各區塊，T-06～T-11 的區塊先建成各自獨立的空元件檔（`records.tsx`、`playlists.tsx`、`drive.tsx`、`netbird.tsx`、`public-settings.tsx`），各卡只改自己的檔案，不改頁面。
  - `lib/dashboard-api.ts` 的 `redirectToDashboard()` 改導向 `/dashboard/guilds`（`no_permission`、`bot_not_in_guild` 都走它）。
  - `components/dashboard/dashboard-header.tsx` 加「我的」「伺服器」入口。
  - `components/header.tsx`：「管理後台」改成依登入狀態顯示「登入」（連 `/dashboard-login`）或頭像（連 `/dashboard`）；登入狀態以 `/dashboard/me` 判斷，`session_expired` 視為未登入，不觸發導向。

**依賴**：T-02（同改 `app/dashboard/page.tsx` 與邀請的導向）、T-04（官網 header 的「登入」連到 T-04 的登入頁；session 的析域帳號來自 T-03、T-04）

**風險 / 實作注意**：官網 header 每頁都打一次 `/dashboard/me`，回應失敗時當成未登入，不能讓行銷頁出錯。

**進度**：已完成。XingyuBot `7d2e2e2`、`e4e3d1f`、`7a10f6d`、`74562fd`、`6102007`、`bd98cdf`、`a568fed`；domalyze_frontend `33a815d`、`94d35a4`、`496b852`、`b5db23b`、`2010219`、`975bfcb`。未勾的驗收條件需在真實瀏覽器上人工驗證。部署前先在正式 DB 執行 `ALTER TABLE users.music_playlist ADD COLUMN version integer NOT NULL DEFAULT 0;` 再部署程式（`models.py` 已含新欄位，沒先 ALTER 讀歌單的功能會全壞）；`website_weekly_activity`、`website_link_click` 由啟動時的 `create_all` 建立。本機 dev DB 已執行。

### T-06 個人區看得到語音時數、警告、投票、賭盤與抽獎紀錄

**使用者價值**：使用者第一次能在同一個地方看到自己在各伺服器的語音時數與各類紀錄，其中多數沒有指令可查。

**範圍**
- 包含：五類紀錄、分頁、取不到名稱的伺服器。
- 不包含：公開頁上的統計（T-11）。

**驗收條件**
- [ ] 語音時數依伺服器列出，格式「X 小時 Y 分」，依時間由多到少全部列出；在快樂營用 `/user` 查到的分鐘數換算後相同。
- [x] 警告與懲處每筆顯示伺服器、類型、時間、理由與時長，不顯示執行的管理員。
- [x] 投票顯示投票、選項與時間；賭盤顯示賭盤、選項、金額與時間；抽獎顯示抽獎與結果（中獎、未中獎、尚未開獎）。
- [x] 這些紀錄與資料庫裡該 Discord 的資料一致。
- [x] bot 已離開的伺服器顯示為「無法取得名稱的伺服器」。
- [ ] 語音時數以外的紀錄超過 20 筆時先顯示最近 20 筆，載入更多後看到更早的；沒有資料時顯示沒有紀錄。
- [ ] 帶析域帳號時，每個連結的 Discord 各自一組紀錄。
- [x] 同一場投票複選兩個選項，紀錄只出現一筆，列出兩個選項。
- [ ] 360px 寬時可以完整操作。

**實作設計**
- 資料：不異動。
- 後端：新增 `starServer/dashboard/personal_records.py`：
  - `GET /dashboard/personal/records/voice?discord_id=`：回各伺服器的分鐘數，伺服器名稱經 bot 取得，取不到回 null。
  - `GET /dashboard/personal/records/{kind}?discord_id=&offset=&limit=20`，`kind` 為 `warnings`、`polls`、`bets`、`giveaways`：依時間由新到舊，回 `{items, total}`。
  - `discord_id` 必須在 `personal_scope().discord_ids` 內，否則 `403 no_permission`。
  - 新增查詢方法（`starlib/database/postgresql/client.py`）：
    - 語音：新增 `list_voice_times(discord_id)`，回該 Discord 在所有伺服器的 `VoiceTime`（現有只有單一伺服器的 `get_voice_time`）。
    - 警告：`WarningRepository` 加分頁版的個人查詢，回應不含 `moderate_user`。
    - 投票：`PollRepository` 加 `list_user_polls(discord_id, offset, limit)`，以投票為單位分頁與計 `total`；`UserPoll` 的主鍵含 `vote_option`，同一場複選的多筆合併成一筆，選項文字從 `PollOption` 取，標題從 `Poll` 取，時間取最早一筆的 `vote_at`。
    - 抽獎：`PollRepository` 加 `list_user_giveaways`，`GiveawayUser`（`user_id` 是 Discord ID）對 `Giveaway` 判斷是否已開獎、是否在中獎名單。
    - 賭盤：`BetRepository` 加 `list_user_bets`，`UserBet` 對 `Bet`。
    - 投票、賭盤、抽獎沒有伺服器欄位時不顯示伺服器。
- 前端：`components/dashboard/personal/records.tsx`（T-05 建好的空檔）實作紀錄區塊，各類一個分頁或可展開的清單，「載入更多」以 `offset` 累加。

**依賴**：T-05（`personal_scope`、區塊外框）

**實作決定**
- 回應用 `guild_name`（取不到為 null），不回 `guild_id`；警告不回執行的管理員。投票、抽獎有 `guild_id` 所以顯示伺服器，賭盤沒有。
- 語音回分鐘數（無條件捨去），前端組成「X 小時 Y 分」；紀錄類 `limit` 上限 20，超過回 `400`（專案的驗證錯誤統一 400）。
- 警告查詢涵蓋該 Discord 收到的全部紀錄（含伺服器內警告），不做跨群過濾。投票以 poll 為單位 group by 分頁，`total` 為投票數，複選的選項依 `option_id` 排序；賭盤選項 1／2 對應 `blue_title`／`pink_title`。
- 抽獎 `result`：`is_on` 為真是 `pending`，否則依 `is_winner` 為 `won`／`lost`；抽獎主檔已刪除時為 `deleted`，前端顯示「抽獎已刪除」。投票、賭盤主檔已刪除時標題為 null，前端顯示「已刪除的…」。
- 審查修正：`BetRepository.place_bet` 原本用不存在的 `bet_time=`，被 SQLModel 默默丟掉，2026-05-31 起 `/bet place` 下的注 `bet_at` 都是 NULL；改為 `bet_at=`，API 對 NULL 回 `at: null`（前端顯示「時間不明」），排序 `nulls_last()`。舊資料不回填。
- 需要伺服器名稱而 bot 沒開或未 ready 時回 `503 bot_unavailable`（比照 `personal_drive`），避免把暫時狀態顯示成「bot 已離開」；沒有需要名稱的紀錄時不受影響，代價是 bot 離線時有紀錄的各分頁載入失敗。
- 前端「載入更多」以目前筆數當 `offset`，附加時以 `id` 去重（載入期間有新紀錄會使下一頁開頭重複一筆）；`lib/dashboard-records.ts` 放型別、API 呼叫與格式化。

**進度**：已完成。XingyuBot `541a40a`、`a9f8077`、`695f99a`（合併 `d04927c`、`d4cbd52`）；domalyze_frontend `bda737b`、`cf5859e`、`c7f9e6f`（合併 `4799fe7`、`4408a8a`）。與 T-08、T-10 一起審查兩輪，第 2 輪放行。已勾的條件由自動化測試涵蓋資料內容（API 回應與格式化函式），畫面呈現、分頁互動未有元件測試；未勾的條件需在真實 Discord、bot 與瀏覽器上人工驗證。`/bet place` 自 2026-05-31 起下的注 `bet_at` 為 NULL，舊資料未回填，顯示為「時間不明」。

### T-07 域民能在網頁管理歌單

**使用者價值**：域民不必一首一首下指令，能在網頁整理歌單：改名、排序、批次刪除。

**範圍**
- 包含：顯示歌單；建立、改名、刪除歌單；加入歌曲或外部歌單網址；刪除（含批次）；調整順序；同步外部歌單；以整份歌單為單位的衝突；沒有析域帳號但有臨時 ID 資料時唯讀顯示。
- 不包含：播放。

**驗收條件**
- [ ] 歌單內容與 `/playlist show` 一致。
- [ ] 在網頁建立歌單、加入歌曲、調整順序後，用 `/playlist show` 看到相同結果；改名後指令以新名稱找得到。
- [ ] 一次選三首刪除，二次確認後三首都被刪除；刪除歌單前同樣要二次確認。
- [ ] 同步外部歌單後，手動加入的歌曲仍在。
- [ ] 網頁打開歌單後，用指令加了一首歌；網頁接著做任一操作被擋下，看到已被修改的提示與最新內容。
- [ ] 沒有析域帳號、但已經用指令建了歌單的 Discord 登入，看得到歌單內容，沒有可操作的按鈕。
- [x] 直接呼叫 API 修改別人的歌單，或以沒有析域帳號的 session 呼叫寫入 API，都被拒絕。
- [ ] 360px 寬時可以完整操作。

**實作設計**
- 資料：`users.music_playlist.version`（T-05 已建）在任何對該歌單或其歌曲、來源的寫入時加一；網頁與指令走同一組 repository 方法，所以在 `MusicPlaylistRepository` 的寫入方法內處理。
- 後端：
  - `MusicPlaylistRepository` 補 `rename_music_playlist`、`remove_music_playlist_songs(playlist_id, song_ids)`、`reorder_music_playlist_songs(playlist_id, song_ids)`，以及「版本相符才寫入」的包裝，不符時回衝突。
  - 加入歌曲、匯入外部歌單、同步的流程目前在 `starDiscord/cmds/music.py`；抽出成指令與網頁共用的函式，放在新增的 `starlib/music_playlist.py`，指令改呼叫它，行為不變。
  - `starServer/dashboard/personal_playlists.py`（T-05 建好的空檔）：讀寫都以 `personal_scope().tool_user_id` 為準；寫入要 `require_personal(write=True)`，並確認歌單的 `user_id` 等於 `tool_user_id`。每個寫入請求帶 `version`，不符回 `409 conflict`；外形沿用 `conflict.py` 的 `{"error": "conflict", ...}`，但 `current` 放整份歌單的巢狀結構（歌單、歌曲、來源、`version`），不受 `Conflict.current` 的扁平型別限制。
- 前端：`components/dashboard/personal/playlists.tsx`（T-05 建好的空檔）實作歌單區塊：清單、歌曲表、拖拉排序、多選刪除、確認視窗、衝突提示（顯示最新內容）；`tools_writable` 為 false 時唯讀，`tool_unavailable` 時顯示暫時無法載入。

**依賴**：T-05（`personal_scope`、`require_personal`、區塊外框）

**風險 / 實作注意**：指令端也會遞增 `version`，抽共用函式時要確認 `/playlist add`、`save_current`、`save_queue`、`sync`、`remove`、`delete` 都走到遞增；`UserRepository.merge_user_data` 搬歌單（改 `user_id`、撞名時改名）不經過這些方法，也要遞增。

**實作決定**
- 版本與鎖：`MusicPlaylistRepository` 每個寫入都在單一交易內 `SELECT ... FOR UPDATE` 歌單列（指令與網頁都取，讓同一份歌單的寫入排隊），帶 `expected_version` 時才比對，不符拋 `MusicPlaylistConflict`（`starlib/exceptions.py`）並先 rollback；寫入後 `version+1`。`create_music_playlist` 不遞增（初值 0），空操作不遞增，`merge_user_data` 搬過去的歌單遞增。取鎖後所有路徑（含提早 return、例外）都經 `lock_music_playlist` context manager commit 或 rollback。
- 名稱空間：建立、改名的重名與 25 個上限檢查在使用者的 advisory lock 內做（與 `merge_user_data` 共用 `_advisory_lock_user`），順序一律先名稱鎖再歌單列鎖。
- 多步寫入單一交易：`import_music_playlist_source`（建來源＋加歌）、`sync_music_playlist_sources`（多來源一次替換、單次遞增）。網頁的同步先在交易外擷取全部來源，再在鎖內比對來源集合與版本後寫入；擷取期間來源增減視為衝突。原本的 `create_music_playlist_source`、`replace_music_playlist_source_songs` 已移除。
- `starlib/music_playlist.py` 只吃已擷取的資料（`Extracted`），不 import `starDiscord`；擷取由呼叫端做，網頁端呼叫 `starDiscord.music_player.extract_songs`。`MAX_PLAYLISTS=25`、`MAX_PLAYLIST_SONGS=500` 搬到 starlib，指令與網頁共用。
- API：`GET /dashboard/personal/playlists` 回 `{writable, unavailable, limits, playlists: [{id, name, version, song_count}]}`；`GET .../{id}` 回整份（歌曲、來源、`version`）；`POST` 建立、`PATCH /{id}` 改名、`DELETE /{id}?version=`、`POST /{id}/songs`（歌曲或外部歌單網址）、`POST /{id}/songs/remove`、`PUT /{id}/songs/order`（必須是全部歌曲）、`POST /{id}/sync`。寫入都帶 `version`，成功回整份最新歌單。
- 錯誤：`409 {"error": "conflict", "deleted", "current": 整份歌單 | null}`；輸入錯誤 `400 {"error": "invalid_playlist", "message"}`；別人的或不存在的歌單一律 `404 not_found`；沒有析域帳號的寫入 `403 domalyze_required`（先於歸屬檢查）。
- 前端：型別與 API 放 `lib/dashboard-playlists.ts`；不加依賴，桌面用原生 HTML5 拖拉（`sm` 以上顯示把手），每列另有上移／下移按鈕；衝突時直接換成最新內容並提示操作沒有套用；歌單詳情選取時才載入；沒有析域帳號但有臨時 ID 歌單時唯讀顯示。

**進度**：已完成。XingyuBot `00a37b1`、`df73e29`、`cb8bd86`、`4d86602`、`c20fcbb`（合併 `2e7713b`）；domalyze_frontend `6daa617`、`27fd42d`（合併 `246653f`）。審查三輪，最後一輪放行。未勾的驗收條件需在真實 Discord、bot 與瀏覽器上人工驗證（自動化測試以假擷取與假 API 涵蓋）。

### T-08 域民能在網頁設定雲端資料夾共用

**使用者價值**：符合資格的域民能在網頁設定、更換或取消雲端資料夾的共用 gmail，不必記指令格式。

**範圍**
- 包含：資格判斷、顯示、設定、更換、取消、輸入驗證、失敗處理、無析域帳號時唯讀。
- 不包含：指令的行為，維持現狀。

**驗收條件**
- [x] 可見的 Discord 都不在開放此功能的伺服器裡時，看不到這個區塊。
- [ ] 符合資格的人看到目前共用的 gmail，能設定、更換、取消；指令端看到相同結果。
- [x] 輸入 `abc` 共用給 `abc@gmail.com`；輸入 `abc@yahoo.com` 無法送出。
- [x] 共用失敗時看到原因，原本的設定不變。
- [ ] 沒有析域帳號但已用指令設定過的人，看得到目前的 gmail，不能操作。
- [ ] 360px 寬時可以完整操作。

**實作設計**
- 資料：不異動。
- 後端：
  - 抽出 `/drive` 的新增與移除共用（`XingyuGoogleCloud().add_file_permissions`／`remove_file_permissions` 與 `DriveShare` 寫入）成指令與網頁共用的函式，指令改呼叫它，行為不變。更換＝先新增新 gmail，成功後再移除舊的並寫入，新增失敗時原設定不動。
  - `starServer/dashboard/personal_drive.py`（T-05 建好的空檔）：資格＝`personal_scope().discord_ids` 中任一個在 `drive_share_guilds` 的伺服器成員快取裡；讀寫都以 `tool_user_id` 為鍵；`GET` 回 `{eligible, gmail | null}`；`PUT`（`{gmail}`）、`DELETE` 要 `require_personal(write=True)`。gmail 只接受 `^[^@\s]+$` 或 `^[^@\s]+@gmail\.com$`（不分大小寫），前者補上 `@gmail.com`，不符回 `400 invalid_gmail`；Google API 失敗回 `502 drive_failed`。
- 前端：`components/dashboard/personal/drive.tsx`（T-05 建好的空檔），表單即時檢查格式，失敗顯示原因。

**依賴**：T-05

**實作決定**
- 共用函式放 `starlib/drive_share.py`，拆成 DB 讀（`plan_share`）、Google HTTP（`request_share`／`request_remove`）、DB 寫（`save_share`）三段；指令用組合版 `set_drive_share`／`remove_drive_share`。網站端 Google HTTP 以 `asyncio.to_thread` 在 DB executor 外執行，不佔 DB 連線。資料夾 ID 常數搬到 `DRIVE_FOLDER_ID`。
- `GET /dashboard/personal/drive` 回 `{writable, unavailable, eligible, gmail}`，比卡上多 `writable`、`unavailable`，前端靠它們決定是否顯示表單與「暫時無法載入」；不符資格回 `eligible=false`、`gmail=null`，`PUT`／`DELETE` 不符資格回 `403 not_eligible`；bot 未就緒回 `503 bot_unavailable`；成功回最新狀態。
- 缺 Origin 的寫入由既有 csrf middleware 回 `400 invalid_request`。
- 更換的補償：舊權限移除失敗時收回剛新增的權限再回 `502`，避免兩個信箱同時有權限；同信箱（不分大小寫）視為無變動，不呼叫 Google。
- 審查修正：只有 Google 那段（`request_share`／`request_remove`）失敗回 `502 drive_failed`，DB 讀寫錯誤走一般 500，Google 已變更後 DB 寫入失敗會記錄「Google 端已變更但 DB 寫入失敗」；Google 端已不存在（404）的舊權限視為已收回，更換、取消、回滾都走這條。
- 前端：`lib/dashboard-drive.ts` 放型別與驗證（規則同後端）；`eligible=false` 時整個區塊不顯示（載入中也不顯示）；載入失敗顯示暫時無法載入；取消共用不加確認視窗。

**進度**：已完成。XingyuBot `c73fd33`、`9db0a2b`、`fe77226`（合併 `dd9283f`、`2d20b33`、`8e44a01`）；domalyze_frontend `547de58`（合併 `9b31720`）。與 T-06、T-10 一起審查兩輪，第 2 輪放行。未勾的驗收條件需以真實 Google Drive、bot 成員快取與瀏覽器人工驗證（自動化測試以假 Google 與假 bot 涵蓋）。

### T-09 域民能在網頁查看 NetBird 節點並取得安裝指令

**使用者價值**：域民能在網頁看到自己的 NetBird 節點狀態，也能直接取得安裝指令完成綁定。

**範圍**
- 包含：節點資訊、按下才產生的安裝指令、無析域帳號時唯讀。
- 不包含：解除綁定；domalyze-api 記錄的節點。

**驗收條件**
- [ ] 已綁定的人看到節點資訊，內容與 `/game netbird` 一致；綁定了但沒有節點時看到尚未偵測到節點的說明。
- [ ] 沒有綁定的人看到尚未綁定的說明。
- [ ] 打開頁面不會產生安裝指令；按下按鈕後才拿到指令與腳本下載，沒有綁定的人之後用 `/game netbird` 看得到綁定。
- [ ] NetBird API 連不上時看到稍後再試的提示。
- [ ] 沒有析域帳號、但已用指令綁定的人看得到節點資訊，沒有產生按鈕。
- [ ] 360px 寬時可以完整操作。

**實作設計**
- 資料：不異動。
- 後端：
  - 抽出 `/game netbird_setup` 的建立群組、建立 setup key、寫入 `NetBirdBinding`，以及 `/game netbird` 的節點查詢，成為共用函式；指令改呼叫它，行為不變。
  - `starServer/dashboard/personal_netbird.py`（T-05 建好的空檔）：`GET` 讀 `personal_scope().tool_user_id` 的綁定與節點；`POST /setup` 要 `require_personal(write=True)`，綁定寫到 `tool_user_id`（此時就是 `account_id`），回 `{command, bat}`，key 只出現在這次回應；`APINetworkError` 回 `502 netbird_unavailable`。
- 前端：`components/dashboard/personal/netbird.tsx`（T-05 建好的空檔），按鈕產生後顯示指令並提供 `.bat` 下載，提醒 24 小時內有效且只能用一次。

**依賴**：T-05

**實作決定**
- 共用函式放 `starlib/netbird_setup.py`，拆成 DB 讀（`plan_setup`、`plan_peers`）、NetBird HTTP（`request_setup_key`、`fetch_peers`）、DB 寫（`save_setup`）三段；指令用組合好的 `create_setup(user_id)`（回 `NetBirdSetup(command, bat)`）與 `list_peers(user_id)`（未綁定回 None、已綁定無節點回 `[]`）。網站端 DB 經 `run_db`，HTTP 以 `asyncio.to_thread` 在 DB executor 外執行，不佔 DB 連線；NetBird 全部成功後才寫入綁定。
- `GET /dashboard/personal/netbird` 回 `{writable, unavailable, bound, peers: [{name, ip, connected, last_seen, os, version}]}`；`writable` 即 `tools_writable`、`unavailable` 即 `tool_unavailable`；`tool_user_id` 為 None 或未綁定時 `bound=false`，不呼叫 NetBird。
- `POST /dashboard/personal/netbird/setup` 回 `{command, bat}`；兩個端點遇 `APINetworkError` 都回 `502 netbird_unavailable`，失敗時不留下綁定；Origin 檢查由既有 csrf middleware 套用。
- 前端：鎖定時仍顯示唯讀節點、不給按鈕；`.bat` 由前端以 Blob 下載（UTF-8 無 BOM，與指令附件一致）；產生成功後重新載入節點；再按一次會產生新的 key。

**進度**：已完成。XingyuBot `8f069fb`、`a617d39`、`22e889d`、`280d910`（合併 `a80fb74`）；domalyze_frontend `d60d23f`（合併 `442ad01`）。與 T-07 一起審查三輪，最後一輪放行。未勾的驗收條件需以真實 NetBird API 與瀏覽器人工驗證（自動化測試以假 NetBird API 涵蓋）。

### T-10 擁有者查得到每週的析域帳號連結率

**使用者價值**：擁有者能看出個人區有沒有讓更多人連結析域帳號。

**範圍**
- 包含：記錄每週有使用網站的 Discord、連結入口的點擊次數、擁有者指令。
- 不包含：對外顯示。

**驗收條件**
- [ ] 擁有者用擁有者指令查得到最近幾週每週的連結率與連結入口的點擊次數；週一 00:00 到週日 24:00，台灣時間。
- [x] 同一個 Discord 一週內在兩天各使用一次網站，只算一個帳號。
- [x] 連結率以該週結束時是否已連結析域帳號為準；之後才連結或解除連結，不改變過去幾週的數字。
- [x] 在個人區按一次連結入口，該週點擊次數加一。
- [x] 週結束時 auth server 不可用，該週標示尚未計算，恢復後補算。

**實作設計**
- 資料：`website_weekly_activity`（`week_start date`、`discord_id bigint`，主鍵兩者，`linked boolean` 可為 null）與 `website_link_click`（`week_start date` 主鍵、`count integer`），放在 `stardb_basic`（`BasicSchema`），由 T-05 建好 model，啟動時 `create_all` 建立。
- 後端：
  - `session.py` 的 `require_session` 在通過後記錄使用：以記憶體記下「這個 Discord 本週已記錄」，同一週只寫一次（`INSERT ... ON CONFLICT DO NOTHING`，`linked` 為 null）。
  - `starServer/dashboard/personal_link_click.py`（T-05 建好的空檔）：`POST /dashboard/personal/link-click`，該週 `count` 加一，不需要析域帳號。
  - 週結算：在 `starDiscord/cmds/task.py` 的 `scheduler.add_job` 加一個每小時的 cron 工作，對所有已結束的週（`week_start` 早於本週一，台灣時間）中 `linked` 為 null 的列，以 `find_by_discord` 查是否連結且未停權，寫入 `linked`；`DirectoryUnavailable` 時留 null，下一小時再補。
  - 擁有者指令加在 `starDiscord/cmds/owner.py`：列出最近 N 週（預設 8）的使用帳號數、已連結數量與比例、點擊次數；某週仍有 `linked` 為 null 的列時標示尚未計算完成。
- 前端：`components/dashboard/personal/` 的連結入口（T-05）按下時先送 `link-click`（不等回應）再開新分頁。

**依賴**：T-05（連結入口）

**風險 / 實作注意**：每週的帳號數大時逐一查 auth server 會慢；結算是背景排程，第一版逐一查即可。

**實作決定**
- 新增 `starlib/website_stats.py`（週界線、記錄、結算、報表）與 `WebsiteStatsRepository`，讓 `session.py`、`task.py`、`owner.py` 只呼叫窄介面。
- 週界線以 UTC+8 的 `nowtz()` 計算，`week_start` 為週一日期；本週的列 `linked` 必為 null，結算只處理 `week_start` 早於本週一的列，所以擁有者指令對本週一律顯示「尚未計算」。記錄失敗（DB 例外）只 log，不讓請求失敗；記憶體以「Discord ID + 週」去重，重啟後多一次 `ON CONFLICT DO NOTHING`，不改動已結算的 `linked`。
- 結算排程每小時 :05（jitter 60 秒），逐一 `find_by_discord`，第一個 `DirectoryUnavailable` 就中止這一輪，其餘留待下次；停權算未連結，事後連結或解除不改過去。
- 擁有者指令為 `/link_rate [週數 1–52，預設 8]`，限 owner、debug_guilds，結果只有自己看得到；沒有任何紀錄的週不列；有 null 的週比例顯示 `-` 並註明待查數。
- `POST /dashboard/personal/link-click` 回 `204`，無 body；前端 fire-and-forget，失敗不拋錯、session 過期不彈窗也不導向。
- 審查修正：`settle_weeks` 讀完待結算列後立刻 `release_session`（等 auth server 時不握交易），`finally` 再釋放一次，避免 bot 的 session 停在 idle in transaction 鎖住統計表。
- 測試用共用 fixture 調整：`test_dashboard_auth.py` 的 `dashboard_env` 多 patch `website_stats.sqldb` 並重設記憶體去重集合，避免既有 dashboard 測試把使用紀錄寫進真實 DB。

**進度**：已完成。XingyuBot `8b7479d`、`ecd350f`（合併 `05e524b`、`f54ac4a`）；domalyze_frontend `920d6fc`（合併 `17ac0da`）。與 T-06、T-08 一起審查兩輪，第 2 輪放行。未勾的驗收條件（擁有者指令實跑 `/link_rate`）需在真實 Discord 上人工驗證，另建議人工確認瀏覽器按連結入口時 POST 204 且新分頁照常開、週界線實際切換。

### T-11 域民能開啟公開頁並選擇公開的內容

**使用者價值**：域民能把自己選定的資料做成一個網址分享給別人。

**範圍**
- 包含：公開設定、公開頁、找不到與暫時無法顯示的頁面、不收錄、代號變更、合併、停權。
- 不包含：社群名片、排行。

**驗收條件**
- [x] 沒開啟公開頁時，`/u/<域民代號>` 看到找不到的頁面。
- [x] 開啟並只勾選積分後，未登入的訪客只看到代號與積分；勾選後不必另外存檔，訪客重新整理就看得到。
- [x] 開啟但沒勾任何區塊時，訪客只看到代號與「沒有公開的內容」。
- [x] 勾選語音時數只顯示各 Discord 的總時數；勾選投票、賭盤、抽獎只顯示各類參與次數；勾選歌單顯示歌單名稱與歌曲。
- [x] 警告、雲端資料夾共用與 NetBird 沒有可勾選的選項。
- [x] 不公開 Discord 名稱時以「帳號一」「帳號二」區分，Discord ID 較小的是帳號一。
- [ ] 公開頁帶有不讓搜尋引擎收錄的標示。
- [x] 域民被停權滿 60 秒後，公開頁變成找不到的頁面；改代號後舊網址找不到、新網址可用。
- [x] auth server 暫時不可用時打開公開頁，看到暫時無法顯示的頁面。
- [x] 兩位域民合併後，存續帳號的公開頁依存續帳號的設定，被併帳號的網址找不到。
- [ ] 沒有析域帳號的 session 看不到公開設定的內容，只看到鎖定說明。
- [ ] 公開設定與公開頁在 360px 寬時可以完整操作與閱讀。

**實作設計**
- 資料：新增 `users.public_profile`（`UsersSchema`）：`user_id uuid` 主鍵、`enabled boolean`、`sections text[]`（`points`、`pets`、`voice`、`participation`、`playlists`、`discord_names`）。合併時以存續帳號為準：`UserRepository.save_discord_identity` 搬資料時一律刪掉被併帳號的列，不搬；存續帳號沒有設定就維持預設關閉。
- 後端：
  - `starServer/dashboard/public_profile.py`（T-05 建好的空檔）：
    - `GET`／`PUT /dashboard/personal/public`：讀寫設定，`PUT` 要 `require_personal(write=True)`，`sections` 只接受上列值。
    - `GET /dashboard/public/{username}`（不需要 session）：`find_by_username`；查無、`suspended`、沒有設定或 `enabled` 為 false 一律回 `404 not_found`；`DirectoryUnavailable` 回 `503 directory_unavailable`。查到後以 `account_id` 的 `discord_passports`（依 Discord ID 由小到大）組出各區塊，只回勾選的；資料讀取重用 T-05 的資產、T-06 的語音與參與統計（只取總數）、T-07 的歌單讀取（以 `account_id` 為 `user_id`）。每次請求都即時查 auth server 與資料庫，不快取，勾選、停權與改代號都在下一次請求生效。
- 前端：
  - `components/dashboard/personal/public-settings.tsx`（T-05 建好的空檔）實作公開設定：開關與勾選，按下即送出；顯示公開網址。
  - 新增 `app/u/[username]/page.tsx`，`metadata` 設 `robots: { index: false, follow: false }`；404 與 503 各一個畫面。不需要登入，不載入 `app/dashboard/layout.tsx`。

**依賴**：T-06（語音與參與統計的讀取）、T-07（歌單讀取）

**風險 / 實作注意**：公開端點不經 `require_session`，`csrf.py` 只套在寫入端點；回應不得含 Discord ID 以外的識別資訊，`discord_names` 未勾時連 Discord ID 也不回。

**實作決定**
- 公開頁資料全由 `public_profile.py` 組裝，重用 `personal._assets`；新增 `PublicProfileRepository`（設定讀寫、語音總分鐘 `get_voice_total_minutes`、參與次數 `count_user_participation`，口徑同 T-06 紀錄的 total）。
- 合併一律刪被併帳號的 `public_profile`，存續帳號沒有設定維持關閉。
- 公開端點每次即時查 auth server 與 DB，無快取；停權以 `Account.suspended` 判斷，`username` 為 None 或代號超過 64 字也回 404。
- 公開頁回應不含 Discord ID：各 Discord 以 `label`（帳號一、帳號二…）區分；勾 `discord_names` 才回 `name`、`avatar_url`（名稱查不到時 `name` 為 null，前端退回標籤）。寵物只公開名稱與種類，不含 `food`。
- 設定 API 回 `{available, enabled, sections, username}`；沒有析域帳號 GET 回 `{available: false}`、PUT 回 403 `domalyze_required`。`sections` 以固定順序儲存並去重，勾選即 PUT，前端沒有存檔鈕。
- 前端公開頁是 client component 載入，HTTP 狀態碼為 200，以 noindex 與畫面區分 404、503。
- `users.public_profile` 由啟動時 `create_all` 建立，不需手寫 DDL。

**進度**：已完成。XingyuBot `2f0d272`；domalyze_frontend `44c8384`。未勾的驗收條件（noindex 標示、鎖定說明畫面、360px 寬）需在真實瀏覽器上人工驗證，另建議人工確認停權、改代號與 auth server 不可用的真實情境。

## 開工前待決

無。
