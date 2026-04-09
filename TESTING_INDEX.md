# XingyuBot 測試檔案導覽

## 📁 測試資源位置

### 🚀 新手快速開始
👉 **[RUN_TESTS_README.md](./RUN_TESTS_README.md)** (2 分鐘內上手)
- 立即執行測試的方法
- 常見命令參考
- 故障排除指南

### 🏗️ 測試架構深入瞭解  
👉 **[tests/README.md](./tests/README.md)** (瞭解整個測試框架)
- 完整的目錄結構
- 5 部分測試計劃
- 第 1 部分詳細說明
- Fixtures 使用方法

### 🧪 測試執行
```bash
# 執行所有測試
python -m pytest tests/unit/ -v

# 快速執行第 1 部分 (推薦)
python -m pytest tests/unit/test_database_models.py -v

# 生成覆蓋率報告
python -m pytest tests/unit/ --cov=starlib --cov-report=html
```

---

## 📊 當前狀態

| 項目 | 狀態 |
|------|------|
| **第 1 部分** | ✅ 完成 (41/41 測試通過) |
| **架構框架** | ✅ 完成 |
| **文檔** | ✅ 整合完成 |
| **下一步** | 📋 第 2 部分 - OAuth 認證 |

---

## 📚 檔案說明

| 檔案 | 用途 |
|------|------|
| `tests/conftest.py` | 全域 Fixtures 配置 (10 個) |
| `tests/unit/test_database_models.py` | 模型驗證測試 (41 個案例) |
| `pytest.ini` | Pytest 設定檔 |
| `.env.test` | 測試環境變數 |
| `RUN_TESTS_README.md` | 快速入門指南 ⭐ |
| `tests/README.md` | 測試架構詳解 ⭐ |

---

## ⚡ 常用命令

```bash
# 執行所有測試
python -m pytest tests/unit/ -v --tb=short

# 執行特定測試類別
python -m pytest tests/unit/test_database_models.py::TestPlatformType -v

# 進入 debugger
python -m pytest tests/unit/ --pdb

# 生成覆蓋率報告
python -m pytest tests/unit/ --cov=starlib --cov-report=html -v
```

---

**提示**: 開始此前請確認虛擬環境已激活並安裝依賴 (`pip install -e ".[dev]"`)

*最後更新: 2024年4月10日*
