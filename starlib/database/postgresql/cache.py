"""Caching utilities for DB query results."""

from __future__ import annotations

import time
from collections.abc import Hashable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Generic, TypeVar, overload

from .enums import DBCacheType
from .models import DynamicVoiceLobby, TwitchChatCommand

if TYPE_CHECKING:
    from collections.abc import Callable

T = TypeVar("T")
V = TypeVar("V")
_MISSING = object()
KT = TypeVar("KT")
VT = TypeVar("VT")
IT = TypeVar("IT")


class TTLCache(Generic[T]):
    """Per-key TTL 快取，適用於 per-user 資料（如權限、VIP 狀態）。

    Parameters
    ----------
    ttl:
        快取存活秒數，預設 300 秒（5 分鐘）。

    Usage
    -----
    ::

        cache: TTLCache[CloudUser | None] = TTLCache(ttl=300)

        user = cache.get(user_id)
        if user is _MISSING:
            user = db.get_user(user_id)
            cache.set(user_id, user)            # None 也會被快取
    """

    def __init__(self, ttl: int = 300) -> None:
        self._store: dict[object, tuple[T, float]] = {}
        self._ttl = ttl

    def get(self, key: object, default: object = _MISSING) -> T | object:
        """回傳快取值；若已過期或不存在則回傳 default（預設為 _MISSING 哨兵）。"""
        entry = self._store.get(key)
        if entry is None:
            return default
        value, expires = entry
        if time.monotonic() > expires:
            del self._store[key]
            return default
        return value

    def set(self, key: object, value: T) -> None:
        """寫入快取並設定到期時間。"""
        self._store[key] = (value, time.monotonic() + self._ttl)

    def invalidate(self, key: object) -> None:
        """手動失效指定 key（例如管理員修改用戶權限後呼叫）。"""
        self._store.pop(key, None)


class DictCache(Generic[KT, VT]):
    """字典型快取，支援全量載入、部分寫入與部分刪除"""

    def __init__(self) -> None:
        self._data: dict[KT, VT] | None = None

    @property
    def is_ready(self) -> bool:
        """快取是否已初始化"""
        return self._data is not None

    def load(self, data: dict[KT, VT]) -> None:
        """全量載入（取代現有資料）"""
        self._data = data

    def set(self, key: KT, value: VT) -> None:
        """部分寫入單筆（未初始化時靜默忽略）"""
        if self._data is not None:
            self._data[key] = value

    def delete(self, key: KT) -> None:
        """部分刪除單筆（未初始化或 key 不存在時靜默忽略）"""
        if self._data is not None:
            self._data.pop(key, None)

    def get(self, key: KT, default: VT | None = None) -> VT | None:
        if self._data is None:
            return default
        return self._data.get(key, default)

    def raw(self) -> dict[KT, VT] | None:
        """回傳原始字典，供舊有相容性存取"""
        return self._data

    def __getitem__(self, key: KT) -> VT:
        return self._data[key]  # type: ignore[index]

    def __setitem__(self, key: KT, value: VT) -> None:
        self.set(key, value)

    def __delitem__(self, key: KT) -> None:
        self.delete(key)

    def __contains__(self, key: object) -> bool:
        return self._data is not None and key in self._data

    def __iter__(self):
        return iter(self._data or {})


class ListCache(Generic[IT]):
    """清單型快取，支援全量載入、部分新增與部分刪除"""

    def __init__(self) -> None:
        self._data: list[IT] | None = None

    @property
    def is_ready(self) -> bool:
        """快取是否已初始化"""
        return self._data is not None

    def load(self, data: list[IT]) -> None:
        """全量載入（取代現有資料）"""
        self._data = list(data)

    def add(self, item: IT) -> None:
        """部分新增單筆（未初始化時靜默忽略）"""
        if self._data is not None:
            self._data.append(item)

    def discard(self, item: IT) -> None:
        """部分刪除單筆（未初始化或不存在時靜默忽略）"""
        if self._data is not None and item in self._data:
            self._data.remove(item)

    def raw(self) -> list[IT] | None:
        """回傳原始清單，供舊有相容性存取"""
        return self._data

    def __contains__(self, item: object) -> bool:
        return self._data is not None and item in self._data

    def __iter__(self):
        return iter(self._data or [])


class CacheStore:
    """統一管理所有快取項目，提供具名屬性存取與 DBCacheType 泛型介面"""

    __slots__ = ("dynamic_voice_lobby", "voice_log", "twitch_cmd", "dynamic_voice_room", "voice_time_counter", "_map")

    def __init__(self) -> None:
        self.dynamic_voice_lobby: DictCache[int, DynamicVoiceLobby] = DictCache()
        self.voice_log: DictCache[int, tuple[int, int | None]] = DictCache()
        self.twitch_cmd: DictCache[int, dict[str, TwitchChatCommand]] = DictCache()
        self.dynamic_voice_room: ListCache[int] = ListCache()
        self.voice_time_counter: ListCache[int] = ListCache()

        self._map: dict[DBCacheType, DictCache | ListCache] = {
            DBCacheType.DynamicVoiceLobby: self.dynamic_voice_lobby,
            DBCacheType.VoiceLog: self.voice_log,
            DBCacheType.TwitchCmd: self.twitch_cmd,
            DBCacheType.DynamicVoiceRoom: self.dynamic_voice_room,
            DBCacheType.VoiceTimeCounter: self.voice_time_counter,
        }

    def entry(self, key: DBCacheType) -> DictCache | ListCache | None:
        """取得指定快取項目"""
        return self._map.get(key)

    def load(self, key: DBCacheType, data) -> None:
        """全量載入指定快取"""
        e = self._map.get(key)
        if e is not None:
            e.load(data)

    def raw(self, key: DBCacheType):
        """取得指定快取的原始資料（未初始化時回傳 None）"""
        e = self._map.get(key)
        return e.raw() if e is not None else None

@dataclass
class CacheSlot(Generic[T]):
    # not in use.
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
