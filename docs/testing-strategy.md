# 測試策略筆記

## 專案架構概述

```
main.py
├── starDiscord  ← Discord bot 層（UI、指令、事件）
├── starServer   ← 非 Discord 服務（Twitch、Web API）
└── starlib      ← 共用基礎層（database、providers、utils、pubsub）
```

`starlib` 同時被 `starDiscord` 和 `starServer` 依賴，不適合合併進任何一方。

---

## 現階段測試結論

**現階段幾乎不值得導入完整的自動化測試流程。**

這個專案是單人維護的個人 bot，開發者對每一行程式都有完整的心智模型。完整測試流程解決的核心問題是「多人協作時，我不知道你的改動有沒有壞掉我的東西」，這個問題目前不存在。

寫測試的時間成本高於它能帶來的效益。

---

## 唯一值得做的測試

針對 `sqldb` 的讀取方法做幾個整合測試，目的只有一個：**改 schema 後快速確認沒壞。**

- 直接對真實 DB 執行，不用 mock
- 只測讀取操作（無副作用）
- 用自己的 Discord ID 作為固定測試資料
- 有需要時再寫，不需要提前規劃

設置只需要：
1. `pyproject.toml` 加 `testpaths = ["test"]` 和 integration marker
2. 一個 `test/test_sqldb.py` 檔案

---

## 觸發導入完整測試的條件

以下任一條件出現時，測試的價值才會超過成本：

1. **有其他人開始貢獻程式碼** — 測試從「保護自己」變成「溝通契約」
2. **`starServer` 的 API 對外公開** — 外部服務依賴你的 endpoint，需要確保不會無聲地壞掉
3. **RPG / 經濟系統的商業邏輯複雜到難以手動驗證** — 數值計算正確性需要測試保證

---

## 未來往商業系統發展的方向

拆系統和導入測試會自然地同步發生，因為兩件事的驅動力相同。

可能的拆分方向：
- `starlib/database` → 獨立的資料服務
- `starlib/providers` → 各平台的整合服務
- `starServer` → 對外的 API 層
- `starDiscord` → 只剩 Discord 的 UI 邏輯

**原則：每條服務邊界出現的時候，那條邊界的測試就應該跟著出現。** 不是「到時候補測試」，而是「拆邊界和寫邊界的測試是同一件事」。

現在最值得做的是保持 `starlib` 的架構乾淨，因為那決定了以後拆系統的難度。
