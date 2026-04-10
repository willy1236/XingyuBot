# XingyuBot 測試架構

## 📋 概述

本項目的測試計劃分為 5 個優先級，當前正在實施 **第 1 部分：模型驗證測試**。

## 🏗️ 目錄結構

```
tests/
├── conftest.py                      # Pytest 全域設定和 Fixtures
├── __init__.py
├── unit/                            # 單元測試
│   ├── __init__.py
│   ├── test_database_models.py      # ✅ 第 1 部分：模型驗證
│   ├── test_validators.py           # (待實施)
│   └── test_utils.py                # (待實施)
├── integration/                     # 整合測試
│   ├── test_postgresql.py           # ❌ 第 1 部分：DB 操作 (暫不實施)
│   ├── test_oauth.py                # ❌ 第 2 部分：OAuth 認證
│   └── test_api_providers.py        # ❌ 第 2 部分：外部 API
└── fixtures/                        # 測試資料和工廠
    ├── README.md
    ├── sample_users.json            # (待建立)
    ├── mocks.py                     # (待建立)
    └── factories.py                 # (待建立)
```

## 🧪 第 1 部分：模型驗證測試

### 目標
驗證資料庫模型定義的正確性，包括：
- ✅ Pydantic Schema 繼承結構
- ✅ 列舉值定義和常數
- ✅ Schema 命名空間配置
- ✅ 列舉映射關係
- ✅ 資料型別相容性

### 測試檔案
- **test_database_models.py** - 主要測試（32 個測試案例）

### 測試類別

| 類別 | 功能 | 案例數 |
|------|------|------:|
| `TestBaseSchema` | Schema 基類驗證 | 3 |
| `TestSchemaConfiguration` | Schema 配置檢查 | 10 |
| `TestNotifyCommunityType` | 通知類型列舉 | 4 |
| `TestNotifyChannelType` | 通知頻道列舉 | 3 |
| `TestDBCacheType` | 快取類型 StrEnum | 3 |
| `TestPlatformType` | 平台類型列舉 | 6 |
| `TestMcssServerAction` | 伺服器動作列舉 | 3 |
| `TestEnumEdgeCases` | 列舉邊界情況 | 4 |
| `TestSchemaValidation` | Schema 驗證規則 | 2 |
| `TestDataTypeCompatibility` | 資料型別相容性 | 2 |
| `TestEnumExhaustiveness` | 列舉完整性檢查 | 2 |

**總計：42 個測試案例**

## 🚀 如何執行

### 執行所有單元測試
```bash
pytest tests/unit/
```

### 執行特定測試類別
```bash
pytest tests/unit/test_database_models.py::TestPlatformType -v
```

### 執行特定測試案例
```bash
pytest tests/unit/test_database_models.py::TestPlatformType::test_enum_values -v
```

### 執行所有標記為 `@pytest.mark.unit` 的測試
```bash
pytest -m unit
```

### 生成覆蓋率報告
```bash
pytest tests/unit/ --cov=starlib.database.postgresql --cov-report=html
```

### 執行測試並顯示詳細輸出
```bash
pytest tests/unit/test_database_models.py -vv --tb=long
```

## 📄 全域 Fixtures (conftest.py)

### 可用的 Fixtures

| Fixture | 類型 | 用途 |
|---------|------|------|
| `test_timezone` | `timezone` | 測試用時區 (UTC) |
| `test_data_dir` | `Path` | 測試資料目錄 |
| `sample_datetime` | `datetime` | 範例 datetime |
| `sample_timestamps` | `dict` | 多個時戳 |
| `sample_user_ids` | `dict` | 各平台用戶 ID |
| `sample_guild_ids` | `dict` | Discord 伺服器資源 ID |
| `sample_enum_values` | `dict` | 列舉值集合 |
| `sample_strings` | `dict` | 各種字串範例 |
| `sample_numeric_values` | `dict` | 數值範例 |
| `reset_env` | - | 環境變數重置 (自動執行) |

### 使用範例

```python
def test_something(sample_user_ids, test_timezone):
    """使用 Fixtures 的測試"""
    discord_id = sample_user_ids["discord_id"]
    tz = test_timezone
    # ...
```

## 🔧 環境設定

### .env.test
```bash
DATABASE_URL=postgresql://test:test@localhost:5432/xingyu_test
LOG_LEVEL=DEBUG
TESTING=true
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=test_db_password
DB_NAME=xingyu_test
MC_SERVER_PASSWORD=test_mc_rcon_password
JWT_SECRET=test_jwt_secret
```

### pytest.ini
- 測試路徑：`tests/`
- 測試命名慣例：`test_*.py`, `Test*`, `test_*`
- 自訂標記：unit, integration, e2e, slow, db, external_api

## ⚠️ 注意事項

1. **第 1 部分的限制**
   - 不涉及實際資料庫操作
   - 不包含 PostgreSQL 或 MongoDB 連線
   - 純粹驗證模型定義

2. **後續部分**
   - 第 2 部分將測試 OAuth 流程
   - 第 3 部分將測試 Discord 命令
   - 第 4 部分將測試排程任務
   - 第 5 部分將進行端到端測試

3. **測試執行要求**
   - Python 3.10+
   - pytest>=7.0
   - sqlmodel、pydantic 等依賴已安裝

## 📊 測試覆蓋率目標

- **第 1 部分目標**：模型定義 100% 覆蓋
- **最終目標**：整個核心庫 80%+ 覆蓋率

## 🔗 相關文件

- [測試建議文檔](https://github.com/willy1236/XingyuBot/discussions) - 完整測試計劃
- [pytest 文檔](https://docs.pytest.org/) - 官方文檔
- [sqlmodel 文檔](https://sqlmodel.tiangolo.com/) - 模型 ORM 文檔

## ✅ 第 1 部分完成檢查清單

- [x] 建立 tests/ 目錄結構
- [x] 實施 conftest.py (全域 Fixtures)
- [x] 實施 test_database_models.py (第 1 部分)
- [x] 建立 pytest.ini 設定檔
- [x] 建立 .env.test 環境變數
- [x] 運行測試並驗證全部通過
- [x] **所有 41 個測試通過 (100%)**

## 📊 第 1 部分成果總結

| 指標 | 數值 |
|------|-----:|
| 測試類別 | 11 |
| 測試案例 | **41** |
| 通過率 | **100%** ✅ |
| 執行時間 | ~2.8 秒 |
| Schema 命名空間 | 10 個 |
| 列舉型別覆蓋 | 5 個 |

## 🚀 快速開始

### 執行測試

```bash
# 執行所有測試
python -m pytest tests/unit/ -v

# 快速執行第 1 部分
python -m pytest tests/unit/test_database_models.py -v

# 生成覆蓋率報告
python -m pytest tests/unit/ --cov=starlib --cov-report=html -v
```

### 故障排除

遇到 `Failed to canonicalize script path` 錯誤？
→ 使用 `python -m pytest` 而非直接執行 `pytest`

## 📚 相關文檔

- **[RUN_TESTS_README.md](../RUN_TESTS_README.md)** - 快速入門指南

## 📋 後續步驟

1. ✅ **完成**: 第 1 部分 - 模型驗證測試 (41 個測試)
2. 📋 **待實施**: 第 2 部分 - OAuth 認證測試
3. 📋 **待實施**: 第 3 部分 - Discord 命令測試
4. 📋 **待實施**: 第 4 部分 - 排程任務測試
5. 📋 **待實施**: 第 5 部分 - 端到端測試
