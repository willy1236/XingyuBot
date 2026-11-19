# 測試策略

## 執行

```bash
uv run pytest -m "not integration"          # 日常：不連外部服務，約 2.5 分鐘
uv run pytest tests/polls                    # 只跑一個功能
uv run pytest -m integration                 # 連真實外部服務（Rettiwt、yt-dlp、Twitch 等），需要對應憑證
```

前置條件：

- **PostgreSQL**：大部分測試用 `.env.development` 的本機 DB。`repo` fixture 把每個測試包在外層交易裡，結束時整個 rollback，不會留下資料。
- **Redis**：`tests/messaging/` 需要 `REDIS_URL`，沒設定或連不上時自動 skip。

## 目錄

依功能分目錄，一個功能從 starlib、Discord 指令到後台 API 的測試放在一起：

```
tests/
├── conftest.py          全樹共用 fixture：repo、dashboard_env、discord_env、spy、site
├── helpers/             跨功能共用的 helper（身分、後台登入、伺服器權限、假伺服器、網站帳號）
├── core/                DB session、log、Sentry、權限等基礎設施
├── messaging/           跨 process 訊息匯流排（Redis）
├── identity/            auth server 身分、綁定、資料合併與遷移
├── providers/           外部 API 供應層
├── dashboard/           後台框架：登入、伺服器清單、權限區塊、設定、預覽、邀請
├── accounts/            網站登入、個人區、公開頁、統計
├── notifies/            通知設定
├── twitch/              Twitch bot 與通知
├── polls/  reaction_roles/  tickets/  giveaways/  dynamic_voice/  moderation/  music/
```

各目錄的檔名慣例：

- `test_lib.py`、`test_core.py` 等：starlib 或 Discord 端的邏輯
- `test_dashboard*.py`：後台 API
- `*_helpers.py`：同目錄多個檔案共用的假物件與 fixture

## 共用 fixture 與 helper

- 全樹共用的 fixture 放 `tests/conftest.py`，測試直接用參數名稱取得，不要 import。
- 只有單一功能用到的 fixture 放該目錄的 `*_helpers.py`，由測試檔 import，import 那行要加 `# noqa: F401  (fixture)`。
- 測試檔之間不互相 import；要共用就抽到 helper。
- `dashboard_env` 會替換後台模組的 DB 與設定，並清空 dashboard session 與網站統計表，因為本機 DB 可能有手動測試留下的資料。需要它的檔案在開頭宣告 `pytestmark = pytest.mark.usefixtures("dashboard_env")`。

## 該寫哪些測試

測試的價值在於守住對外行為：

- 後台 API 對外開放，每個 endpoint 的權限檢查、輸入驗證、與 Discord／DB 的失敗處理都要有測試。
- 牽涉 DB 與 Discord 兩邊狀態的流程（發訊息後寫 DB、DB 失敗要收回訊息），每條失敗路徑各一個測試。
- 輸入格式的邊界用 `parametrize` 列表，不要一個值寫一個函式。
- 不測私有實作細節；讀原始碼比對字串的測試（如 `dashboard/test_preview.py` 確認預設文案與送出端一致）只在沒有其他方式時才用。
