# 🧪 XingyuBot 測試快速入門

> 💡 **完整索引**: 查看 [TESTING_INDEX.md](./TESTING_INDEX.md) 了解所有測試資源

## 立即執行測試

```bash
# 執行所有測試
python -m pytest tests/unit/ -v

# 快速執行 (第 1 部分)
python -m pytest tests/unit/test_database_models.py -v

# 執行並生成覆蓋率報告
python -m pytest tests/unit/ --cov=starlib --cov-report=html -v
```

---

## 📊 第 1 部分測試狀態

✅ **41 個測試全部通過**

```
tests/unit/test_database_models.py
├── TestBaseSchema (3/3)
├── TestSchemaConfiguration (10/10)
├── TestNotifyCommunityType (4/4)
├── TestNotifyChannelType (3/3)
├── TestDBCacheType (3/3)
├── TestPlatformType (5/5)
├── TestMcssServerAction (3/3)
├── TestEnumEdgeCases (4/4)
├── TestSchemaValidation (2/2)
├── TestDataTypeCompatibility (2/2)
└── TestEnumExhaustiveness (2/2)
```

---

## ⚠️ 故障排除

### 錯誤: "Failed to canonicalize script path"

**原因**: 直接執行 `pytest` 時的 Windows 虛擬環境路徑問題

**✅ 解決方案**: 改用 `python -m pytest`

```bash
# ❌ 不要用
pytest tests/unit/

# ✅ 改用這個
python -m pytest tests/unit/ -v
```

---

## 🔍 常用命令參考

| 目的 | 命令 |
|------|------|
| 執行所有測試 | `python -m pytest tests/unit/ -v` |
| 執行特定類別 | `python -m pytest tests/unit/test_database_models.py::TestPlatformType -v` |
| 執行特定測試 | `python -m pytest tests/unit/test_database_models.py::TestPlatformType::test_enum_values -v` |
| 詳細輸出 | `python -m pytest tests/unit/ -vv --tb=long` |
| 打印輸出 | `python -m pytest tests/unit/ -v -s` |
| 覆蓋率報告 | `python -m pytest tests/unit/ --cov=starlib --cov-report=html` |
| 進入 debugger | `python -m pytest tests/unit/ --pdb` |
| 上次失敗 | `python -m pytest --lf -v` |

---

## 📚 詳細文檔

- [TESTING_GUIDE.md](./TESTING_GUIDE.md) - 完整的測試指南和最佳實踐
- [TESTING_STATISTICS.md](./TESTING_STATISTICS.md) - 詳細的測試統計報告
- [tests/README.md](./tests/README.md) - 測試架構和目錄說明

---

## ✅ 檢查清單

執行測試前確認：

- [x] Python 3.10+ 已安裝
- [x] 虛擬環境已建立 (`.venv/`)
- [x] pytest 已安裝 (`pip install -e ".[dev]"`)
- [x] `.env.test` 已建立
- [x] `pytest.ini` 已設定

---

## 🚀 後續步驟

1. ✅ **第 1 部分**: 模型驗證測試 (完成)
2. 📋 **第 2 部分**: OAuth 認證測試 (待實施)
3. 📋 **第 3 部分**: Discord 命令測試 (待實施)
4. 📋 **第 4 部分**: 排程任務測試 (待實施)
5. 📋 **第 5 部分**: 端到端測試 (待實施)

---

**最後更新**: 2024年4月9日
