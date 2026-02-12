from __future__ import annotations

from collections.abc import Hashable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Generic, TypeVar, overload

if TYPE_CHECKING:
    from collections.abc import Callable

T = TypeVar("T")
V = TypeVar("V")
_MISSING = object()


@dataclass
class CacheSlot(Generic[T]):
    """宣告式快取描述符

    資料儲存在實例屬性 ``obj._cache_{name}`` 上，透過 Python descriptor
    protocol 提供惰性載入、失效重建、局部更新等功能。

    Parameters
    ----------
    loader:
        全量重建 — 從 DB 載入完整快取，簽名 ``(self) -> T``。
    key_loader:
        局部重建 — 從 DB 載入單一 key 的值，簽名 ``(self, key) -> value``。
        僅適用於 dict 型快取。呼叫 ``rebuild_key`` 時使用。

    Usage
    -----
    ::

        class SQLRepository:
            twitch_cmd = CacheSlot[dict[int, dict[str, str]]](
                loader=lambda self: self.get_raw_chat_command_all(),
                key_loader=lambda self, key: self.get_raw_chat_command_channel(key),
            )

            def add_twitch_cmd(self, channel_id, cmd, resp):
                ...  # DB 寫入
                # 局部重建：只需提供 key
                type(self).twitch_cmd.rebuild_key(self, channel_id)

            def nuke_twitch_cmd_cache(self):
                del self.twitch_cmd  # 全量失效，下次讀取自動重建
    """

    loader: Callable[..., T]
    key_loader: Callable[..., object] | None = None

    _attr: str = field(init=False, default="")

    # ── descriptor protocol ────────────────────────────

    def __set_name__(self, owner: type, name: str) -> None:
        self._attr = f"_cache_{name}"

    @overload
    def __get__(self, obj: None, objtype: type = ...) -> CacheSlot[T]: ...
    @overload
    def __get__(self, obj: object, objtype: type = ...) -> T: ...

    def __get__(self, obj: object | None, objtype: type | None = None) -> CacheSlot[T] | T:
        if obj is None:
            return self  # 類別層級存取 → 回傳描述符本身
        value = getattr(obj, self._attr, _MISSING)
        if value is _MISSING:
            # 惰性載入
            value = self.loader(obj)
            setattr(obj, self._attr, value)
        return value  # type: ignore[return-value]

    def __set__(self, obj: object, value: T) -> None:
        setattr(obj, self._attr, value)

    def __delete__(self, obj: object) -> None:
        """刪除快取 → 下次讀取時透過 loader 自動重建"""
        try:
            delattr(obj, self._attr)
        except AttributeError:
            pass

    # ── 快取操作 ───────────────────────────────────────

    def rebuild(self, obj: object) -> None:
        """全量重建快取"""
        value = self.loader(obj)
        setattr(obj, self._attr, value)

    def rebuild_key(self, obj: object, key: Hashable) -> None:
        """局部重建：只重新載入指定 key 的快取

        從 ``key_loader(obj, key)`` 取得新值，寫入 ``cache[key]``。
        """
        if self.key_loader is None:
            raise TypeError(f"CacheSlot '{self._attr}' 未定義 key_loader，無法局部重建")
        cache = self.__get__(obj, type(obj))
        cache[key] = self.key_loader(obj, key)  # type: ignore[index]

    def pop_key(self, obj: object, key: Hashable, default: V | None = None) -> V | None:
        """從快取中移除指定 key"""
        cache = self.__get__(obj, type(obj))
        return cache.pop(key, default)  # type: ignore[union-attr]
