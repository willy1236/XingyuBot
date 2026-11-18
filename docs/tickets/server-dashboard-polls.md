# 伺服器管理後台（投票）任務拆解

規格書：[docs/spec/server-dashboard-polls-spec.md](../spec/server-dashboard-polls-spec.md)

## 現況與前提

- 技術棧與共通規則沿用[第三案任務拆解](server-dashboard-roles-tickets-moderation.md)〈現況與前提〉：
  - 跨 thread 一律經 `access.on_guild`／`on_guild_async`，DB 一律經 `db.run_db`。
  - Discord ID 一律用字串；錯誤一律 `raise DashboardError`。
  - router 檔由 `starServer/dashboard/__init__.py` 自動掃描。
  - 權限只經 `require_section`；網頁上的限制在 API 端都要再檢查一次。
  - 沒有 migration 工具：改既有表要在卡內附 ALTER，部署時先手動執行，再部署 code。
- 既有相關機制：
  - **投票資料**（`starlib/database/postgresql/models.py`）：
    - `Poll`（`stardb_basic.poll_data`）：poll_id、title、creator_id、created_at、guild_id、message_id、end_at（null 代表進行中）與各項設定。沒有頻道欄位，也沒有截止時間。
    - `PollOption`（`poll_options`）、`PollRole`（`poll_role`：is_only_role、role_magnification）、`UserPoll`（`discord_users.user_poll`：一人一選項一列，vote_magnification 是權重）。
  - **存取**：`client.py` 的 `PollRepository`（約 1540 行起）。
    - `get_poll_vote_count`、`get_users_poll` 依 `ban_alternate_account_voting` 排除小帳。
    - `remove_poll` 沒有地方呼叫，而且寫壞了：刪 `UserPoll`／`PollOption` 時的條件寫成 `Poll.poll_id`，也沒有刪 `PollRole`。不能沿用。
    - 個人區的投票紀錄是 `list_user_polls`（約 1671 行）。
  - **按鈕與結果**：`starDiscord/uiElement/view.py` 的 `PollView`。
    - 按鈕有 `PollOptionButton`、`PollEndButton`、`PollResultButton`、`PollCanenlButton`、`PollNowButton`。
    - `results_embed(interaction, with_chart)` 需要 interaction 才拿得到 guild；`generate_chart` 用 matplotlib 畫圓餅圖。
    - `PollEndButton` 結算時直接改 `end_at`，沒有鎖也沒有重讀。
  - **指令**：`starDiscord/cmds/command.py` 的 `/poll create|view|result`（約 398–475 行）。
    - `create_poll` 把 `ctx.respond(...)` 的回傳值當成訊息存進 `message_id`。實際上 py-cord 第一次回應時，回傳的是 `Interaction`（`discord/interactions.py` 的 `send_message` 回傳 `self._parent`），所以存下的是 interaction ID，不是訊息 ID。
    - 選項限制只有 1–20 項，標題長度、重複選項、權重範圍都沒檢查。
  - **啟動**：`starDiscord/cmds/bot_event.py` 約 121–131 行。建立超過 28 天的進行中投票直接設 `end_at`、不更新訊息，其餘以 `add_view(..., message_id=poll.message_id)` 載入。
  - **可照抄的模式**：抽獎（`starServer/dashboard/giveaways.py`，以及 `view.py` 的 `GiveawayView`）。
    - 清單分頁與 90 天篩選。
    - `missing_permissions`：抽獎頻道的權限警告。
    - `giveaway_lock` 加上 `reload()`：開獎只發生一次。
    - `schedule_end`：用 `bot.scheduler`（APScheduler）的 `DateTrigger` 排到期，啟動時在 `starDiscord/cmds/task.py` 約 84 行重排。
    - `publish`：更新訊息，並回傳失敗原因代碼。
    - 前端是 `lib/dashboard-giveaways.ts`（含 `formatDateTime`、`missingPermissionsText`）、`components/dashboard/giveaway-list.tsx`、`giveaway-detail.tsx`、`app/dashboard/guilds/[id]/giveaways/page.tsx`。
  - **從後台發訊息的模式**：`starServer/dashboard/reaction_roles.py` 的 `create_reaction_role`。
    - 用 `require_session` 取得操作者，`_actor` 取得 Member。
    - 先檢查 bot 在頻道的權限（`starlib/reaction_roles.py` 的 `bot_permission_issues`）。
    - `channel.send` 之後再寫 DB；DB 寫失敗就刪掉訊息。
  - **抽獎的時間輸入**：`/giveaway create` 的結束時間用 `parse_datetime`，接受「2026-11-07 20:00」「明天 20:00」「3d」「2小時」等寫法。
  - **前端區塊**：`lib/dashboard-sections.ts` 的 `SectionKey`、`NAV_ITEMS`（`ready` 旗標）；後端是 `access.py` 的 `Section`、`SECTION_RULES`。
  - **bot owner**：`sclient.bot.is_owner(user)`，與 `PollEndButton` 的判斷相同。
  - **測試**：後端在 `test/test_dashboard_*.py`（真實 PostgreSQL、假 Discord）；前端是 `lib/*.test.ts`（vitest）。
- 這次會動到的既有部位：
  - XingyuBot：`models.py`、`client.py`、`view.py`、`command.py`、`bot_event.py`、`task.py`、`starServer/dashboard/access.py`；新增 `starlib/polls.py`、`starServer/dashboard/polls*.py`。
  - domalyze_frontend：`lib/dashboard-sections.ts`；新增 `app/dashboard/guilds/[id]/polls/`、`components/dashboard/poll-*.tsx`、`lib/dashboard-polls.ts`。
- 已定案的技術前提：API 放 XingyuBot 的 web 服務，前端放 domalyze_frontend `main`，與前幾案相同。

## 實作順序總覽

| # | 卡號 | 進度 | 標題 | 依賴 | 並行組 | 備註 |
|---|---|---|---|---|---|---|
| 1 | V-00 | 實作完成 | [共用] 投票核心：資料欄位、結果與可見範圍、結算、建立 | 無 | — | 其餘卡都依賴 |
| 2 | V-01 | 實作完成 | 管理員能看投票清單與詳細頁 | V-00 | — | 骨架切片 |
| 3 | V-02 | 未完成 | 發起人能從後台結算與刪除投票 | V-01 | A | |
| 4 | V-03 | 未完成 | 管理員能從後台發起投票 | V-01 | A | |
| 5 | V-05 | 未完成 | 管理員能匯出投票結果 | V-01 | A | |
| 6 | V-04 | 未完成 | 投票可以設截止時間並自動結算 | V-03、V-02 | — | 在 V-03 的表單加欄位；與 V-02 都改 `view.py` |

並行組 A 的分工：V-02、V-03、V-05 各自新增 router 檔，分別是 `polls_actions.py`、`polls_create.py`、`polls_export.py`。前端的部分：V-01 先建好兩個空元件 `poll-actions.tsx`、`poll-export-link.tsx`，並放進詳細頁；V-02、V-05 只改各自的元件檔。V-03 用自己的頁面，以及 `poll-list.tsx` 的發起按鈕。三張卡互不重疊。

## 任務卡

### V-00 [共用] 投票核心：資料欄位、結果與可見範圍、結算、建立

**使用者價值**：V-01～V-05 共用同一套資料欄位、結果計算、可見範圍判斷、結算流程與建立流程。指令、Discord 按鈕和後台各寫一份的話，結果會對不上，結算也可能發生兩次。

**範圍**
- 包含：
  - `Poll` 新增欄位與 ALTER。
  - 結果計算與可見範圍判斷，加上「能否管理」的判斷。
  - 結算流程（鎖、重讀、更新訊息）。指令與按鈕改用它。
  - 建立流程，含欄位驗證。`/poll create` 改用它，並存正確的訊息與頻道。
  - 啟動時的 30 天規則，結算時更新訊息。
  - 新增後端 `Section.POLLS`，前端 `SectionKey`／`NAV_ITEMS` 加上 polls（`ready: false`）。
- 不包含：
  - 截止時間的排程、指令選項與訊息顯示（V-04）。
  - 刪除（V-02）。

**驗收條件**
- [ ] 用 `/poll create` 建立的新投票，DB 裡的 message_id 是投票訊息本身的 ID，channel_id 是所在頻道；bot 重啟後，按鈕仍能投票。
- [ ] `/poll create` 填超過 45 字的標題、重複的選項、超過 80 字的選項，或權重超出 1–10，會被擋下並顯示原因。
- [ ] 發起人在 Discord 上按「結算投票」，結果與現在相同：訊息改成結果與圓餅圖。
- [x] 同一個投票同時被兩個來源結算，只結算一次。
- [ ] 把一個進行中投票的 created_at 改成 31 天前，bot 啟動後投票被結算，訊息改成結果；改成 29 天前則不會。

**實作設計**
- 資料：
  - `Poll` 新增 `channel_id: int | None`（BigInteger）、`deadline: datetime | None`（timestamptz，V-04 起寫入）、`message_failure: str | None`。`message_failure` 記結算時訊息沒能更新的原因代碼，沒問題時是 null。
  - 手動 ALTER：
    ```sql
    ALTER TABLE stardb_basic.poll_data ADD COLUMN channel_id bigint;
    ALTER TABLE stardb_basic.poll_data ADD COLUMN deadline timestamptz(0);
    ALTER TABLE stardb_basic.poll_data ADD COLUMN message_failure text;
    ```
  - 既有投票的 channel_id 維持 null，代表「頻道未知」。它們的 message_id 是 interaction ID，不能拿來找訊息，所以 channel_id 為 null 的投票一律當作沒有訊息。
  - repository 新增：
    - `get_poll_fresh(poll_id)`：`populate_existing`，與 `get_giveaway_fresh` 同一個做法。
    - 投票身分組沿用既有的 `get_poll_role(poll_id, is_only_role=None)`，不新增同義方法。
    - `delete_poll(poll_id)`：同一個 transaction 刪 `UserPoll`、`PollOption`、`PollRole`、`Poll`，條件各自用該表的 poll_id。V-00 的 `create_and_send` 發送失敗時用它回滾，V-02 直接沿用，只需移除寫壞的 `remove_poll`。
    - `poll_vote_rows(poll_id, include_alt: bool)`：成員、選項、權重、投票時間。
    - `count_poll_voters(polls: list[Poll]) -> dict[int, int]`：各投票不重複的成員數，依各投票自己的 `ban_alternate_account_voting` 排除小帳。
- 後端：新增 `starlib/polls.py`，純函式，web 與 bot 共用。
  - `PollResults`：各選項的加權票數、投票人數（不重複成員）、逐票列。依 `ban_alternate_account_voting` 排除小帳。
  - `viewer_role(poll, user_id, *, is_owner, creator_in_guild) -> "creator" | "member"`：發起人、bot owner，以及發起人不在伺服器時的管理員，都算 creator。
  - `visibility(poll, role) -> (counts: bool, names: bool)`：照規格〈結果的可見範圍〉的表。`check_results_in_advance` 為 false 時，一律歸為「結束才公佈」。匿名投票的 names 恆為 false。
  - `can_manage(role) -> bool`：結算、刪除用，就是 role 為 creator。
  - `validate_poll_input(title: str, options: list[str], number_of_user_votes: int, role_weights: dict[int, int], deadline: datetime | None, now: datetime)`：回傳欄位錯誤清單。限制是標題與選項先去掉前後空白，標題不得為空且 45 字以內，選項 1–20 項、每項不得為空且 80 字以內、不重複，每人可投票數在 1 到選項數之間，權重 1–10。deadline 有值時，秒數捨去後必須晚於 now，且不超過 now 加 30 天。指令與後台都只經這個函式驗證。
- bot（`view.py`）：
  - `PollView` 加 `reload()`、`poll_lock(poll_id)`，以及 `async finish(edit: Callable[..., Awaitable] | None = None) -> PollOutcome`。`finish` 在鎖內重讀；已結算時回 `already_ended`，否則設 `end_at`、呼叫 `publish`。`edit` 是呼叫端提供的更新訊息方式：`PollEndButton` 傳入以 `interaction.edit_original_response` 更新的函式，`publish` 有 `edit` 時用它、不 fetch 訊息，所以舊投票（channel_id 為 null）與缺少讀取訊息歷史權限時，按鈕結算照樣更新得了訊息；不傳時照下面的 fetch 流程（V-02、V-04 呼叫 `finish()` 不帶參數）。
  - `publish`：channel_id 或 message_id 為 null 時回 `message_unknown`。抓得到訊息就清掉按鈕，換成結果 embed 與圓餅圖。失敗時依情況回 `channel_missing`、`message_missing`、`no_permission`、`failed`。這五種代碼都寫進 `message_failure`，成功時清成 null。頻道用 `get_channel_or_thread`／`fetch_channel` 取得，討論串也適用。
  - `results_embed(guild, with_chart=False, show_name: bool | None = None)`：改成吃 `guild` 而不是 interaction，保留 `show_name` 覆寫參數，資料來源是 `PollResults`。呼叫點有 `PollResultButton`、`/poll result`（`command.py` 約 475 行）與 `publish`，都要改。
  - `PollEndButton` 改用 `finish`，權限判斷不變。callback 先 `interaction.response.defer()` 再呼叫 `finish`，與 `GiveawayEndButton` 相同；`already_ended` 時用 followup 回 ephemeral 的「此投票已結算」。
  - `PollView.create(...)` 改成 `async create_and_send(send, channel_id, ...)`：寫 DB 後呼叫 `send(embed, view)` 發出訊息，送出後存訊息 ID 與 channel_id。發送失敗就刪掉剛寫的 DB 資料，並丟出原因。`send` 由呼叫端決定：指令沿用 interaction 回應，後台用 `channel.send`。V-03 的後台建立也呼叫它。
  - `missing_permissions(channel, perms)`：檢查檢視頻道、讀取訊息歷史、發送訊息；討論串改查 `send_messages_in_threads`。寫法同 `GiveawayView.missing_permissions`。
- 指令（`command.py`）：`create_poll` 先用 `validate_poll_input` 驗證，失敗時用 ephemeral 回原因。通過後呼叫 `create_and_send`，`send` 傳入「`ctx.respond(embed=..., view=...)` 之後 `await ctx.interaction.original_response()`」，回傳真正的訊息。這樣維持現行行為：投票訊息仍是指令的回應，星羽在頻道沒有「發送訊息」權限也能建立。channel_id 存 `ctx.channel_id`，討論串也照樣存。`PollSendError` 時用 ephemeral 回 `MESSAGE_FAILURE_TEXT` 對應的原因。
- 啟動（`bot_event.py`）：28 天改成 30 天。超過的投票用 `asyncio.create_task(view.finish())` 結算並更新訊息，其餘的投票才 `add_view`。channel_id 為 null 的舊投票照舊以 message_id 載入，維持現狀。
- 後端存取：`access.py` 的 `Section` 加 `POLLS = "polls"`，放在 `GIVEAWAYS` 之後。`SECTION_RULES` 是 `{"view", "create", "end", "delete", "export"}`，全部 `MANAGE_MESSAGES`。發起人條件不在這裡判斷，交給 `can_manage`。
- 前端：`lib/dashboard-sections.ts` 的 `SectionKey` 加 `"polls"`。`NAV_ITEMS` 在抽獎後面插入 `{ key: "polls", label: "投票", path: "/polls", ready: false }`，並同步更新 `lib/dashboard-sections.test.ts` 裡斷言 key 清單的測試。
- 介面：
  - `starlib/polls.py`：`PollResults.load(sqldb, poll) -> PollResults`，含 `options: list[{option_id, name, count}]`、`voter_count: int`、`votes: list[{user_id, option_id, weight, voted_at}]`；`viewer_role`、`visibility`、`can_manage`、`validate_poll_input`，錯誤格式為 `[{"path", "reason"}]`，與 `reaction_roles._field` 相同。
  - `view.py`：`PollView.finish(edit=None) -> PollOutcome(status: "ok" | "already_ended" | "not_found", message_failure: str | None)`；`PollView.create_and_send(send: Callable[[discord.Embed, PollView], Awaitable[discord.Message]], channel_id: int, *, bot: DiscordBot, creator_id: int, guild_id: int, title: str, options: list[str], show_name: bool, check_results_in_advance: bool, results_only_initiator: bool, number_of_user_votes: int, ban_alternate_account_voting: bool, only_roles: list[int], role_weights: dict[int, int], deadline: datetime | None = None) -> Poll`。建立 view 與取得伺服器都需要 `bot`，所以加上 keyword 參數 `bot`。`can_change_vote` 一律存 None，與現行指令相同，兩種來源的訊息外觀一致。驗證不在這裡做，呼叫端先跑 `validate_poll_input`。失敗時丟 `PollSendError(code)`，code 為 `channel_missing`、`no_permission`、`failed`；`PollView.missing_permissions(channel, perms) -> list[str]`；`MESSAGE_FAILURE_TEXT: dict[str, str]`，原因代碼對應的中文。
  - 呼叫順序：結算一律經 `finish`，不直接改 `end_at`。`finish` 必須在 bot loop 上執行。

**依賴**：無

**風險 / 實作注意**：
- `generate_chart` 會阻塞 event loop，結算次數不多，可以接受，但不要在清單或詳細頁呼叫。
- `poll_lock` 以 poll_id 為 key，寫法同 `giveaway_lock`。
- `remove_poll` 留給 V-02 取代，這張卡不碰。

**進度**：實作完成（2026-11-18）
- commit：63554b3、dd79b8d、888a313、ac7f46e
- 未驗：待人工驗證——`/poll create` 在 Discord 實機建立後的 message_id 與 channel_id、bot 重啟後按鈕仍能投票、指令擋下不合格欄位並顯示原因、按「結算投票」後的圓餅圖與訊息、bot 啟動時 30 天規則（31 天前結算、29 天前不結算）。

### V-01 管理員能看投票清單與詳細頁

**使用者價值**：有 Manage Messages 的管理員能看到伺服器裡所有投票、各選項的票數，以及實名投票的明細，不必翻頻道找訊息。

**範圍**
- 包含：
  - 投票區塊頁與清單：進行中的在最上面，已結算的每頁 20 筆，預設 90 天、可以切換成全部。
  - 詳細頁：投票設定、依可見範圍顯示的票數與明細、30 秒自動更新、手動重新整理、「訊息未更新」標示。
  - bot 權限警告、頻道未知、頻道已不存在、已刪除的身分組、已離開的成員。
  - 側欄的 polls 改成 `ready: true`。
- 不包含：結算與刪除（V-02）、發起（V-03）、匯出（V-05）、截止時間（V-04 會補上清單與詳細頁的截止時間顯示）。

**驗收條件**
- [ ] 用指令建立一個「所有人都能預先查看結果」的投票，清單上看得到，詳細頁的票數與 Discord 上「查看結果」一致。
- [ ] 匿名投票的詳細頁與 API 回應都沒有投票人。
- [ ] 「結果將在結束時公佈」的投票，進行中時詳細頁與 API 都沒有票數，詳細頁說明結算後公佈；結算後看得到。
- [x] 「僅限發起人能預先查看結果」的投票進行中時，發起人看得到票數，其他管理員看不到；發起人離開伺服器後，其他管理員看得到。
- [ ] 詳細頁開著時，另一人在 Discord 投票，30 秒內票數與實名明細都更新；已結算的不再自動更新。
- [x] 超過 20 筆已結算投票時分頁正確；90 天前建立的已結算投票預設不列出，切換成全部後出現。
- [ ] 本功能上線前建立的投票顯示「頻道未知」、沒有訊息連結。
- [ ] 投票所在頻道被刪除後，清單與詳細頁顯示「頻道已不存在」，不顯示權限警告。
- [ ] 360px 寬的畫面能完成清單與詳細頁的檢視。
- [ ] 拿掉星羽在投票頻道的「讀取訊息歷史」後，清單顯示簡短警告，詳細頁顯示缺哪些權限與後果。
- [ ] 沒有投票時顯示說明；沒有 Manage Messages 的人看不到區塊，直接呼叫 API 回 403；其他伺服器的投票回 404。

**實作設計**
- 資料：repository 新增 `list_active_guild_polls(guild_id)`、`list_guild_polls(guild_id, since, offset, limit)`，已結算的依 `end_at` 由新到舊排序。
- 後端：新增 `starServer/dashboard/polls.py`。
  - `GET /dashboard/guilds/{id}/polls?all=&page=`：回傳格式照 `giveaways.py` 的清單。每筆有 id、title、status、voter_count、creator_id／creator_name、channel_id／channel_name、channel_state（`ok`｜`unknown`：channel_id 為 null｜`missing`：頻道已不存在）、missing_permissions（channel_state 不是 ok 時為 null）、message_url、created_at、ended_at、deadline。頻道用 `get_channel_or_thread` 查。看不到票數的投票，照樣回傳 voter_count。
  - `GET /dashboard/guilds/{id}/polls/{poll_id:int}`（路徑參數一律寫成 `:int`，`/polls/options` 等固定路徑才不會被攔走）：回傳清單每筆的全部欄位，再加上設定（show_name、results_visibility、number_of_user_votes，以及 only_roles／role_weights 的 `{id, name | null}`）。另外回傳 `viewer: {role, can_manage}`、`counts`（看不到時為 null）、`votes`（看不到或匿名時為 null，每列有 user_id、name、left、option_id、weight、voted_at）、message_failure 與 message_failure_text。
  - 操作者用 `require_session` 取得。bot owner 用 `sclient.bot.is_owner`，發起人是否在伺服器用 `guild.get_member(creator_id)`，三者合起來交給 `viewer_role`。
  - 權限 `require_section(Section.POLLS)`。
- 前端：
  - 新增 `app/dashboard/guilds/[id]/polls/page.tsx`（清單）、`app/dashboard/guilds/[id]/polls/[pollId]/page.tsx`（詳細頁，有自己的網址；抽獎是同一頁切換，這裡不照抄）、`components/dashboard/poll-list.tsx`、`poll-detail.tsx`、`lib/dashboard-polls.ts`。型別、`statusLabel`、`missingPermissionsText` 的寫法照抽獎；`formatDateTime` 固定傳 `"Asia/Taipei"`。
  - 新增 `components/dashboard/poll-actions.tsx`、`poll-export-link.tsx`，先回傳 null，props 是 `{ guildId, detail, onChanged }`；需要離開詳細頁時，元件自己用 `useRouter` 導到清單。`poll-detail.tsx` 在操作區放這兩個元件；V-02、V-05 只改元件檔本身。
  - 30 秒更新用 `setInterval` 呼叫 `useLoad` 的 `reload`，只在 status 為 active 時執行。分頁在背景時暫停（`document.visibilityState`）。
  - 清單有「發起投票」按鈕，連到 `/polls/new`。這張卡先不放這個按鈕，由 V-03 加上。
  - `NAV_ITEMS` 的 polls 改成 `ready: true`，同步更新 `lib/dashboard-sections.test.ts`。

**依賴**：V-00（欄位、`PollResults`、可見範圍、Section）

**進度**：實作完成（2026-11-18）
- commit：後端 861ed76；前端（domalyze_frontend）b1fe773、c6dc408
- 未驗：待人工驗證——Discord 實機建立的投票與「查看結果」一致、詳細頁的畫面呈現（結束才公佈的說明、頻道未知、頻道已不存在、權限警告、無投票說明、區塊顯示與隱藏）、30 秒自動更新、360px 畫面。以上項目的 API 部分已有自動測試，畫面部分未驗。

### V-02 發起人能從後台結算與刪除投票

**使用者價值**：發起人在網頁上就能收尾。發起人離開伺服器後，管理員也能結算或清掉投票，不會永遠停在進行中。

**範圍**
- 包含：
  - 結算：二次確認，訊息更新失敗時照樣結算並告知原因，已結算視為成功。
  - 刪除：二次確認，一併刪掉 Discord 訊息與全部資料；訊息刪不掉時照樣刪資料並告知原因；已刪除視為成功。
  - 留在 Discord 上的訊息，有人按按鈕時回「此投票已不存在」。
- 不包含：自動結算（V-04）。

**驗收條件**
- [ ] 發起人在後台結算，Discord 訊息改成結果，詳細頁顯示最新結果。
- [ ] 非發起人的管理員看不到結算、刪除按鈕，直接呼叫 API 回 403 `not_poll_manager`；發起人離開伺服器後重新整理，按鈕出現且操作成功。
- [ ] bot owner 在後台可以結算、刪除任何投票。
- [ ] 先在 Discord 刪掉投票訊息再從後台結算，投票照樣結算，並顯示訊息沒有更新的原因。
- [ ] 發起人剛在 Discord 按了結算，後台再按結算，視為成功並顯示最新結果。
- [ ] 刪除前的確認視窗寫明無法復原；刪除後 Discord 訊息消失，回到清單，個人區不再顯示這筆投票，公開頁的投票參與次數減少。
- [ ] 本功能上線前建立的投票，從後台結算時照樣結算並說明訊息沒有更新；刪除時照樣刪除資料。
- [ ] 360px 寬的畫面能完成結算與刪除。
- [ ] 拿掉星羽在頻道的權限後刪除，資料照樣刪除，畫面說明訊息沒刪掉；之後有人按那則訊息的按鈕，收到「此投票已不存在」，bot 重啟後再按也一樣。

**實作設計**
- 資料：`delete_poll(poll_id)` 已在 V-00 提供（同一個 transaction 刪四張表，條件各自用該表的 poll_id），這張卡直接使用。移除寫壞的 `remove_poll`。
- 後端：新增 `starServer/dashboard/polls_actions.py`。
  - `POST .../polls/{poll_id:int}/end`（`require_section(Section.POLLS, "end")`）：在 bot loop 上重讀，算出 `viewer_role`，`can_manage` 為否時回 403 `not_poll_manager`，否則呼叫 `PollView.finish()`。回傳 `{status, message_failure, message_failure_text}`。
  - `DELETE .../polls/{poll_id:int}`（`require_section(Section.POLLS, "delete")`）：發起人判斷同上。在 bot loop 上先刪訊息：channel_id 為 null 時跳過，記 `message_unknown`；NotFound 視為成功；Forbidden 等錯誤記下原因。接著 `run_db(delete_poll)`，再移除排程 job `poll_end_{id}`（V-04 起才有，job 不在時忽略）。不呼叫 view 的 `stop()`：已註冊的 view 要留著，留在 Discord 上的按鈕才會走到 callback 回「此投票已不存在」。回傳 `{status: "ok" | "already_deleted", message_failure, message_failure_text}`。
  - 投票不存在或屬於其他伺服器時，結算回 404，刪除回 `already_deleted`。
- bot（`view.py`）：`PollOptionButton`、`PollResultButton`、`PollCanenlButton`、`PollNowButton`、`PollEndButton` 的 callback 開頭先檢查投票是否存在，可共用 `PollView.reload()`。投票不存在時回 ephemeral 的「此投票已不存在」，並嘗試 `interaction.message.edit(view=None)`，失敗時忽略。
- bot 重啟後，被刪除的投票不會再 `add_view`，留下的按鈕沒有 view 接。所以另外在 `bot_event.py` 加一個 `on_interaction` listener：component 的 custom_id 符合投票按鈕的格式（`poll_`、`end_poll_`、`poll_result_`、`vote_canenl_`、`vote_now_` 開頭），而且對應的投票已不存在、interaction 還沒被回應時，回同一句話並嘗試移除按鈕。
- 前端：在 `poll-actions.tsx` 放「結算」「刪除」按鈕與確認視窗，只在 `viewer.can_manage` 為真時顯示；結算只在進行中顯示。完成後，結算重新載入詳細頁，刪除導回清單。`message_failure_text` 有值時顯示提示。

**依賴**：V-01（詳細頁、`poll-actions.tsx`、`viewer`）

**風險 / 實作注意**：刪訊息與刪資料不在同一個 transaction。先刪訊息再刪資料：資料刪除失敗時，訊息已經不在，回 500 讓使用者重試，重試時 NotFound 視為成功。

**進度**：未完成

### V-03 管理員能從後台發起投票

**使用者價值**：管理員用表單設定選項、身分組與權重，不必在指令裡用逗號拼字串。

**範圍**
- 包含：
  - 發起頁 `/polls/new`：欄位與預設值照規格〈發起投票〉，不含截止時間與「小帳不算有效票」。
  - 頻道選單只列文字頻道與公告頻道；星羽或操作者不能發言的頻道停用，並標示原因。
  - 送出後由星羽發出訊息；失敗時不建立投票，並顯示原因。
  - 清單的「發起投票」按鈕。
- 不包含：截止時間欄位（V-04）。

**驗收條件**
- [ ] 從後台發起一個投票，指定頻道出現投票訊息，發起人顯示為操作的管理員；他在 Discord 上能按「結算投票」。
- [ ] 選項重複、超過 20 項、標題超過 45 字、每人可投數超過選項數、權重超出 1–10 時，表單擋下並指出欄位；直接呼叫 API 也一樣被擋。
- [ ] bot 沒有發言權限的頻道在選單上停用並標示原因；直接呼叫 API 指定這個頻道，回錯誤，投票沒有建立。
- [ ] 操作者自己不能發言的頻道停用；直接呼叫 API 也被擋。
- [ ] 360px 寬的畫面能完成發起。

**實作設計**
- 後端：新增 `starServer/dashboard/polls_create.py`。
  - `GET .../polls/options`：回傳可選頻道 `{id, name, type, disabled_reason | null}`（文字頻道與公告頻道，`disabled_reason` 標出星羽或操作者缺發言權限），以及可選身分組 `{id, name, color}`，排除 @everyone 與 managed 身分組。
  - `POST .../polls`：body 是 `{channel_id, title, options[], show_name, check_results_in_advance, results_only_initiator, number_of_user_votes, only_roles[], role_weights[{role_id, weight}]}`。
    - 用 `validate_poll_input` 驗證，失敗時回 400 `invalid_request` 與 fields。
    - 在 bot loop 上檢查頻道類型、星羽與操作者的發言權限，再呼叫 `PollView.create_and_send`，`creator_id` 是操作者，`ban_alternate_account_voting` 固定 false。
    - `PollSendError` 轉成 400，帶上原因。
    - 回傳 `{poll_id, message_url}`。
  - 權限 `require_section(Section.POLLS, "create")`。
- 前端：新增 `app/dashboard/guilds/[id]/polls/new/page.tsx`、`components/dashboard/poll-form.tsx`。
  - 選項用可增減的列表，最多 20 列。
  - 身分組沿用 `role-multi-select.tsx`；權重是身分組加上 1–10 的數字列。
  - 標題與選項用 `LabelWithCount` 顯示字數。
  - 送出成功後導到詳細頁。
  - `poll-list.tsx` 加「發起投票」按鈕。

**依賴**：V-01（區塊頁與清單）

**風險 / 實作注意**：`create_and_send` 由 V-00 提供，這張卡不改它；需要調整的話回 V-00 的介面討論。

**進度**：未完成

### V-04 投票可以設截止時間並自動結算

**使用者價值**：發起人不用記得回來結算，到時投票自動收尾。

**範圍**
- 包含：
  - 後台表單的截止時間欄位，以及 `/poll create` 的截止時間選項。
  - 投票訊息顯示截止時間。
  - 到期自動結算、bot 停機後補結算、啟動時先補結算再套 30 天規則。
  - 自動結算時訊息更新失敗，照樣結算並標示「訊息未更新」。
  - 清單與詳細頁顯示截止時間。
- 不包含：建立後修改截止時間（非目標）。

**驗收條件**
- [ ] `/poll create` 設 2 分鐘後截止，訊息上顯示截止時間，到時自動結算，訊息改成結果。
- [ ] 後台發起時選了截止時間，清單與詳細頁顯示截止時間，到時自動結算。
- [ ] 截止時間設在過去或超過建立後 30 天，後台與指令都會擋下。
- [ ] 截止前停掉 bot、過了截止時間再啟動，上線後自動補結算。
- [ ] 到期前在 Discord 刪掉投票訊息，到期後照樣結算，詳細頁標示「訊息未更新」與原因。
- [ ] 截止前手動結算後，到期時不會再結算一次。

**實作設計**
- 資料：寫入 V-00 新增的 `Poll.deadline`。
- bot（`view.py`）：
  - `PollView` 加 `schedule_end()`，寫法同 `GiveawayView.schedule_end`：`DateTrigger(max(deadline, now + 10s))`，job id 是 `poll_end_{id}`，`replace_existing`。
  - `auto_end` 呼叫 `finish()`，失敗時寫 log。
  - 手動結算後移除 job，job 不在時忽略。
  - `embed()` 有 deadline 時加上「截止時間：<t:…:f>（<t:…:R>）」。
  - `create_and_send` 有 deadline 時，發送成功後呼叫 `schedule_end`。
- 啟動：`bot_event.py` 載入投票時，對有 deadline 的進行中投票，用同一個 `add_view` 註冊的 PollView instance 呼叫 `schedule_end`，已到期的排在 10 秒後補結算。30 天規則跳過有 deadline 的投票，所以兩條規則不會作用在同一個投票上；有 deadline 的投票本來就不會超過建立後 30 天。`auto_end` 走 `finish` 會重讀 DB，instance 舊了也沒關係。`bot.scheduler` 由 `task.py` 啟動，確認載入順序時 scheduler 已存在即可，job 可在 start 前加入。
- 指令：`create_poll` 新增選填的「截止時間」選項，沿用 `/giveaway create` 的 `parse_datetime`，時長與日期時間都能輸入；選項說明照抄抽獎的範例寫法。解析不出來時用 ephemeral 回錯誤。解析結果交給 `validate_poll_input` 驗證：秒數捨去後必須晚於現在、不超過 30 天；`30s` 這類不足 1 分鐘的時長拒收。
- 後端：`polls_create.py` 的 body 加 `deadline`（帶時區的 ISO 字串，可省略），交給 `validate_poll_input` 驗證。
- 前端：`poll-form.tsx` 加 `datetime-local` 選擇器，可以清空。輸入值視為台灣時間，送出時轉成帶 `+08:00` 的 ISO 字串。清單與詳細頁顯示 deadline，沒設時顯示「沒有截止時間」。

**依賴**：V-03（表單；`polls_create.py` 的 body）、V-02（兩張卡都改 `view.py` 的 `PollView`）

**風險 / 實作注意**：排程只存在記憶體，所以 bot 重啟時一定要重排，job 不能只在建立時排一次。job 的移除放在 `finish` 裡：狀態為 ok 時呼叫 `bot.scheduler.remove_job("poll_end_{id}")`，job 不存在（例如正是 `auto_end` 自己觸發的那次）時忽略 `JobLookupError`。刪除時的移除寫在 V-02。

**進度**：未完成

### V-05 管理員能匯出投票結果

**使用者價值**：管理員能把結果帶到試算表整理或存檔。

**範圍**
- 包含：詳細頁的「匯出 CSV」按鈕，內容與格式照規格〈匯出〉；看不到票數的投票不能匯出。
- 不包含：批次匯出多個投票。

**驗收條件**
- [ ] 實名投票的匯出檔用 Excel 開啟中文正常，開頭是各選項票數，空一列後是逐票明細，內容與當下詳細頁一致；已離開的成員寫「已離開的成員」。
- [ ] 匿名投票的匯出檔只有各選項票數。
- [ ] 「結果將在結束時公佈」的投票進行中時，詳細頁沒有匯出按鈕，直接呼叫 API 回 403。
- [ ] 檔名含投票 ID 與標題，時間以台灣時間顯示。
- [ ] 360px 寬的畫面能完成匯出。

**實作設計**
- 後端：新增 `starServer/dashboard/polls_export.py`。
  - `GET .../polls/{poll_id:int}/export.csv`：可見範圍判斷與 V-01 的詳細頁相同（`viewer_role`、`visibility`），看不到票數時回 403 `results_hidden`。
  - 用 `PollResults` 產生 CSV，UTF-8 含 BOM，時間轉成 Asia/Taipei。
  - `Content-Disposition` 用 RFC 5987 的 `filename*` 帶中文檔名，例如 `poll-<id>-<標題>.csv`，標題去掉檔名不允許的字元。
  - 權限 `require_section(Section.POLLS, "export")`。
- 前端：在 `poll-export-link.tsx` 放「匯出 CSV」按鈕，只在 `counts` 不為 null 時顯示。用 `lib/dashboard-api.ts` 的 API base 組網址，以 fetch（帶 credentials）取得後轉成 blob 下載；session 過期等錯誤照 `dashboardFetch` 的方式處理，不讓瀏覽器直接打開 JSON 錯誤頁。API 與前端不同源，讀不到 `Content-Disposition`，所以檔名由前端用 detail 的 id 與 title 組成 `poll-<id>-<標題>.csv`，標題去掉檔名不允許的字元；後端照樣送這個 header，給直接呼叫 API 的人用。

**依賴**：V-01（詳細頁、`poll-export-link.tsx`）

**進度**：後端進行中（2026-11-18），前端由另一位 worker 負責
- commit：後端 `polls_export.py`（本 commit）
- 決定：從 `polls.py` 直接匯入 `_load_detail`、`_member_name`，不複製；成員名稱與選項名稱以 `=`、`+`、`-`、`@`、Tab、CR 開頭時前面補單引號，防試算表公式注入，數字欄不動；時間格式 `YYYY-MM-DD HH:MM:SS`；`Content-Disposition` 同時送 ASCII fallback `filename` 與 `filename*`；看不到票數回 403 `results_hidden`。
- 續做：後端測試 `test/test_dashboard_polls_export.py`

## 開工前待決

目前沒有待決事項。
