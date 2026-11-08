"""編輯衝突比對：以使用者打開表單時看到的值，比對資料庫目前的值。

不新增版本欄位（XingyuBot 沒有 migration 工具）。代價是偵測不到 A→B→A，也就是改過又改回原值。
"""

from dataclasses import dataclass

from .errors import DashboardError


@dataclass(frozen=True)
class Conflict:
    #: 目前的值；那一筆已被刪除時為 None
    current: dict[str, str | None] | None

    @property
    def deleted(self) -> bool:
        return self.current is None

    def to_error(self) -> DashboardError:
        """409 conflict：`{"error": "conflict", "deleted": bool, "current": {...} | null}`。"""
        return DashboardError(409, "conflict", deleted=self.deleted, current=self.current)


def _norm(value: object) -> str | None:
    return None if value is None else str(value)


def check_conflict(current: dict | None, original: dict) -> Conflict | None:
    """`original` 是打開表單時的值，只含該種類用得到的欄位；`current` 為 None 表示已被刪除。

    只比對 `original` 有的欄位；兩邊的 Discord ID 可能一邊是 int、一邊是字串，比對前先轉成字串。
    """
    if current is None:
        return Conflict(None)
    if any(_norm(current.get(k)) != _norm(v) for k, v in original.items()):
        return Conflict({k: _norm(v) for k, v in current.items()})
    return None
