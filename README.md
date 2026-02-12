# Xingyu-Bot

一個功能豐富的多平台機器人，以 Discord Bot 為核心，同時整合 Twitch Chat Bot、LINE Bot 與 Web API 服務。

## 功能總覽

### 伺服器管理

- **跨群警告系統**：整合各 Discord 伺服器的警告紀錄，一個伺服器的違規可同步到其他伺服器
- **管理指令**：訊息清理、禁言、踢除、停權，並支援自訂刪除訊息時間範圍
- **反應身分組**：透過反應自助取得身分組
- **私人頻道（Ticket）系統**：使用者可建立私人頻道與管理員溝通
- **動態語音頻道**：有人進入大廳時自動建立語音房，無人時自動刪除

### 自動通知

- **社群通知**：Twitch 開台 / 新影片 / 新剪輯、YouTube 影片、Twitter/X 推文
- **天氣通知**：中央氣象署地震報告、天氣預報、天氣警特報（自動排程檢查）
- **伺服器事件**：成員加入 / 離開通知、語音進出紀錄、全群公告廣播

### 遊戲系統

- **遊戲資料查詢**：League of Legends（Riot API）、Osu、Apex Legends、Steam、Dead by Daylight
- **玩家資料庫**：綁定遊戲帳號後可快速查詢自己或他人的遊戲資訊
- **LOL 詳細戰績**：對戰紀錄、時間軸分析、英雄數據
- **Minecraft 伺服器管理**：伺服器狀態查詢、RCON 遠端指令、MCSS API 整合

### 經濟與互動系統

- **經濟系統**：星塵（⭐）、PT 點數、Rcoin 三種貨幣，支援轉帳與查詢
- **賭盤系統**：類似 Twitch 實況預測的投注系統
- **投票 & 抽獎**：建立互動式投票與抽獎活動
- **寵物系統**：認養、查看寵物資訊
- **RPG 冒險系統**：角色、裝備、冒險玩法（開發中）

### 音樂系統

- 支援 YouTube 等平台的音樂播放，具備歌曲佇列、循環、隨機播放等功能
- 使用 yt-dlp 與 FFmpeg 進行音訊串流

### AI 整合

- **Google Gemini AI**：對話、貢丸偵測等功能
- **Pydantic AI Agent**：支援 MCP（Model Context Protocol）、DuckDuckGo / Tavily 搜尋工具
- **LINE Bot 防詐分析**：自動分析使用者提供的網址，評估詐騙風險（開發中）

### Web API 服務

- 基於 **FastAPI** 的 Web 伺服器，提供 OAuth 認證、Webhook 接收等功能
- 支援 **Discord / Twitch / Google OAuth** 授權流程
- **YouTube PubSubHubbub** 推播接收
- **LINE Messaging API** Webhook 整合

### Twitch Chat Bot

- 與 Discord Bot 連動的 Twitch 聊天機器人
- 支援 EventSub 事件監聽（追隨、開台等）
- 可自訂頻道指令與管理功能

## 技術架構

```plaintext
XingyuBot/
├── main.py                      # 程式進入點，啟動各服務
├── pyproject.toml               # 專案設定與依賴管理
├── starDiscord/                 # Discord Bot 模組
│   ├── bot.py                   # Bot 主類別（基於 Py-cord）
│   ├── checks.py               # 權限檢查與裝飾器
│   ├── command_options.py       # 指令選項定義
│   ├── extension.py             # Cog 擴充基底類別
│   ├── cmds/                    # Slash Command 指令集
│   └── uiElement/               # UI 元件
├── starlib/                     # 核心函式庫
│   ├── base/                    # 基礎類別（BaseThread、BaseAPI 等）
│   ├── core/                    # 核心管理物件（StarController）
│   ├── database/                # 資料庫層
│   │   ├── postgresql/          #   PostgreSQL 操作、模型、列舉、快取
│   │   └── mongodb/             #   MongoDB 操作
│   ├── providers/               # 外部 API 資料供應層
│   │   ├── game/                #   遊戲 API（Riot、Osu、Apex、Steam 等）
│   │   ├── social/              #   社群 API（Twitch、YouTube、Twitter 等）
│   │   ├── general/             #   通用 API（天氣、Google Cloud、Notion 等）
│   │   └── web.py               #   HTTP 請求工具
│   ├── fileDatabase/            # 檔案資料庫（JSON、CSV）
│   ├── oauth/                   # OAuth 認證模組（Discord、Twitch、Google）
│   ├── utils/                   # 工具函式與日誌系統
│   ├── exceptions.py            # 自訂例外
│   ├── instance.py              # 全域 API 實例與設定
│   ├── settings.py              # 時區等基礎設定
│   ├── starAI.py                # Google Gemini AI 整合
│   ├── starAgent.py             # Pydantic AI Agent（Discord）
│   └── starAgent_line.py        # Pydantic AI Agent（LINE 防詐分析）
├── starServer/                  # 伺服器服務
│   ├── auth.py                  # OAuth 客戶端設定（Authlib）
│   ├── bot_website.py           # FastAPI Web 服務
│   ├── scheduler.py             # APScheduler 排程器
│   ├── twitch_chatbot.py        # Twitch Chat Bot
│   └── tunnel_threads.py        # Ngrok 隧道管理
├── database/                    # 設定檔與靜態資料
├── scripts/                     # 啟動與更新腳本
└── test/                        # 測試
```

## 技術堆疊

| 類別 | 技術 |
| ------ | ------ |
| 語言 | Python 3.13 |
| Discord 框架 | [Py-cord](https://github.com/Pycord-Development/pycord) |
| Web 框架 | FastAPI + Uvicorn |
| 主要資料庫 | PostgreSQL（SQLModel / SQLAlchemy） |
| 排程 | APScheduler |
| TwitchBot | TwitchAPI（EventSub + Chat） |
| Twitter/X | Tweepy |
| LINE | LINE Bot SDK v3 |
| 音樂 | yt-dlp + FFmpeg |
| 認證 | OAuth 2.0（Discord / Twitch / Google）、JWT |

## 環境需求

- Python ~3.13.0
- PostgreSQL
- FFmpeg（音樂功能需要）

## 安裝與執行

```bash
# 安裝依賴
uv sync

# 啟動機器人
uv run main.py
```

或使用提供的腳本：

```bash
scripts/run_main.bat
```

## 設定

機器人的設定透過 `database/setting.json` 進行配置，主要設定項包含：

- `bot_code`：Bot 識別碼
- `api_website`：是否啟動 Web API 服務
- `twitch_bot`：是否啟動 Twitch Chat Bot
- `debug_mode`：除錯模式開關
- `SQLsettings`：PostgreSQL 連線設定
- 各項 API Token 儲存於資料庫中

## 授權

本專案為私人專案。

[[使用素材]](/docs/material.md)
