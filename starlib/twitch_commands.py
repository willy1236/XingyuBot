"""Twitch 自訂指令的驗證與寫入。後台端點與聊天室的 `!add_cmd`、`!remove_cmd` 都經這裡，規則只有一份。

每次寫入在同一個交易內：取頻道的鎖、讀目前的指令、驗證、寫入、`twitch_audit.record_change`、commit，
最後通知 Twitch bot 重讀該頻道的指令快取。驗證不過 raise `CommandInvalid`，不存在 raise `CommandMissing`，
後台的編輯衝突由呼叫端傳入的 `verify` 判斷。這些函式是同步的，要在 DB worker thread 上呼叫。
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlmodel import select

from starlib.database import TwitchChatCommand, sqldb
from starlib.messaging import cache_invalidation
from starlib.twitch_audit import AuditActor, AuditSource, record_change
from starlib.utils import nowtz

#: 內建指令由 chat.register_command 處理，自訂指令不可同名
BUILTIN_COMMANDS = frozenset({"add_cmd", "edit_cmd", "remove_cmd", "list_cmd", "title", "game", "uptime", "permit", "regular"})
#: 層級由低到高：所有人 < 訂閱者 < 常客 < VIP < mod < 實況主
PERMISSIONS = ("everyone", "subscriber", "regular", "vip", "mod", "broadcaster")

NAME_MAX = 25
RESPONSE_MAX = 500
COOLDOWN_MAX = 3600
ALIASES_MAX = 10

#: 後台用：目前的值（`comparable` 的形狀），已被刪除時為 None；有衝突就 raise
type Verify = Callable[[dict[str, str | None] | None], None]


@dataclass(frozen=True, slots=True)
class CommandFields:
    """指令可編輯的欄位；預設值等同聊天室 `!add_cmd` 新增的指令。"""

    response: str
    aliases: tuple[str, ...] = ()
    enabled: bool = True
    global_cooldown: int = 30
    user_cooldown: int = 0
    permission: str = "everyone"


class CommandInvalid(Exception):
    """欄位不合法或名稱重複。field 是 name、aliases、response、global_cooldown、user_cooldown 或 permission。"""

    def __init__(self, field: str, reason: str):
        super().__init__(f"{field}: {reason}")
        self.field = field
        self.reason = reason


class CommandMissing(Exception):
    """頻道沒有這個指令。"""


@dataclass(frozen=True, slots=True)
class Removed:
    """`remove` 的結果：kind 是 `command`（整個指令）或 `alias`（只移除別名，name 是別名所屬的指令）。"""

    kind: str
    name: str


def normalize_name(raw: str) -> str:
    """小寫、去掉頭尾空白與開頭的 `!`。"""
    return raw.strip().removeprefix("!").lower()


def _check_name(value: str, field_name: str) -> None:
    if not value:
        raise CommandInvalid(field_name, "名稱不能是空的")
    if len(value) > NAME_MAX:
        raise CommandInvalid(field_name, f"名稱不能超過 {NAME_MAX} 字")
    if any(c.isspace() for c in value) or value.startswith("!"):
        raise CommandInvalid(field_name, "名稱不能含空白，也不能以 ! 開頭")


def _normalized(name: str, fields: CommandFields) -> tuple[str, CommandFields]:
    """正規化名稱與別名並驗證格式與範圍，不查資料庫。"""
    name = normalize_name(name)
    _check_name(name, "name")
    aliases: list[str] = []
    for raw in fields.aliases:
        alias = normalize_name(raw)
        _check_name(alias, "aliases")
        if alias == name:
            raise CommandInvalid("aliases", f"別名 {alias} 與指令名稱相同")
        if alias not in aliases:
            aliases.append(alias)
    if len(aliases) > ALIASES_MAX:
        raise CommandInvalid("aliases", f"別名最多 {ALIASES_MAX} 個")
    if not fields.response.strip():
        raise CommandInvalid("response", "回應不能是空的")
    if len(fields.response) > RESPONSE_MAX:
        raise CommandInvalid("response", f"回應不能超過 {RESPONSE_MAX} 字")
    for key in ("global_cooldown", "user_cooldown"):
        if not 0 <= getattr(fields, key) <= COOLDOWN_MAX:
            raise CommandInvalid(key, f"冷卻要在 0 到 {COOLDOWN_MAX} 秒之間")
    if fields.permission not in PERMISSIONS:
        raise CommandInvalid("permission", "不認得的權限")
    return name, CommandFields(
        fields.response,
        tuple(aliases),
        fields.enabled,
        fields.global_cooldown,
        fields.user_cooldown,
        fields.permission,
    )


def _check_taken(name: str, fields: CommandFields, rows: list[TwitchChatCommand], own: str | None) -> None:
    """名稱與別名不能撞內建指令，也不能撞頻道內其他指令的名稱或別名；own 是正在編輯的指令（排除在外）。"""
    taken: dict[str, str] = {}
    for row in rows:
        if row.name == own:
            continue
        taken[row.name] = row.name
        for alias in row.aliases:
            taken[alias] = row.name
    for value, field_name in [(name, "name"), *((a, "aliases") for a in fields.aliases)]:
        if value in BUILTIN_COMMANDS:
            raise CommandInvalid(field_name, f"{value} 是內建指令，不能使用")
        if value in taken:
            owner = taken[value]
            reason = f"{value} 已經是指令 {owner} 的{'名稱' if owner == value else '別名'}"
            raise CommandInvalid(field_name, reason)


def _rows(twitch_id: int, *, lock: bool = False) -> list[TwitchChatCommand]:
    """頻道目前的指令，一律重讀資料庫；lock 為真時鎖住這些列，之後的更新才不會與觸發指令的計數交錯。"""
    stmt = (
        select(TwitchChatCommand)
        .where(TwitchChatCommand.twitch_id == twitch_id)
        .order_by(TwitchChatCommand.name)
        .execution_options(populate_existing=True)
    )
    if lock:
        stmt = stmt.with_for_update()
    return list(sqldb.session.exec(stmt).all())


def validate(twitch_id: int, name: str, fields: CommandFields, *, current_name: str | None = None) -> None:
    """儲存前的檢查（格式、範圍、名稱與別名有沒有重複），不寫入、不鎖；寫入時會在鎖內再檢查一次。

    先用它擋掉明顯的錯誤，再花 AutoMod 檢查的額度。current_name 是編輯中的指令，檢查重複時排除它。
    """
    name, fields = _normalized(name, fields)
    _check_taken(name, fields, _rows(twitch_id), normalize_name(current_name) if current_name else None)


def snapshot(row: TwitchChatCommand) -> dict[str, Any]:
    """修改紀錄的欄位快照：可編輯的欄位，不含 use_count 與 updated_at。"""
    return {
        "name": row.name,
        "response": row.response,
        "aliases": list(row.aliases),
        "enabled": row.enabled,
        "global_cooldown": row.global_cooldown,
        "user_cooldown": row.user_cooldown,
        "permission": row.permission,
    }


def comparable(values: dict[str, Any]) -> dict[str, str | None]:
    """比對編輯衝突用的字串形式（`conflict.check_conflict` 比的是字串）：別名排序後以換行連接，布林是 true／false。"""
    return {
        "name": values["name"],
        "response": values["response"],
        "aliases": "\n".join(sorted(values["aliases"])),
        "enabled": "true" if values["enabled"] else "false",
        "global_cooldown": str(values["global_cooldown"]),
        "user_cooldown": str(values["user_cooldown"]),
        "permission": values["permission"],
    }


def list_commands(twitch_id: int) -> list[TwitchChatCommand]:
    """頻道的全部指令，依名稱排序。"""
    return _rows(twitch_id)


def find(twitch_id: int, name_or_alias: str) -> TwitchChatCommand | None:
    """以名稱或別名找指令。"""
    target = normalize_name(name_or_alias)
    for row in _rows(twitch_id):
        if row.name == target or target in row.aliases:
            return row
    return None


def _begin(twitch_id: int) -> list[TwitchChatCommand]:
    """取頻道的指令寫入鎖，回傳鎖住的指令列；鎖與列鎖隨 commit 或 rollback 釋放。"""
    sqldb.lock_twitch_commands(twitch_id)
    return _rows(twitch_id, lock=True)


def _finish(twitch_id: int) -> None:
    sqldb.commit()
    cache_invalidation.invalidate("twitch_cmd", str(twitch_id))


def _transaction[**P, R](func: Callable[P, R]) -> Callable[P, R]:
    """任何例外都 rollback，不讓取到的鎖留在交易裡。"""

    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return func(*args, **kwargs)
        except BaseException:
            sqldb.session.rollback()
            raise

    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__
    return wrapper


@_transaction
def create(
    twitch_id: int, actor: AuditActor, source: AuditSource, name: str, fields: CommandFields
) -> TwitchChatCommand:
    """新增指令。名稱或別名重複、與內建指令同名時 raise CommandInvalid，不覆蓋。"""
    name, fields = _normalized(name, fields)
    rows = _begin(twitch_id)
    _check_taken(name, fields, rows, None)
    row = TwitchChatCommand(
        twitch_id=twitch_id,
        name=name,
        response=fields.response,
        aliases=list(fields.aliases),
        enabled=fields.enabled,
        global_cooldown=fields.global_cooldown,
        user_cooldown=fields.user_cooldown,
        permission=fields.permission,
        updated_at=nowtz(),
    )
    sqldb.session.add(row)
    sqldb.session.flush()
    record_change(twitch_id, actor, source, "command", name, "create", None, snapshot(row))
    _finish(twitch_id)
    return row


def _locate(rows: list[TwitchChatCommand], name: str, verify: Verify | None) -> TwitchChatCommand:
    """依名稱找指令；找不到時，有 verify 就讓它判斷（通常 raise 已被刪除的衝突），否則 raise CommandMissing。"""
    row = next((r for r in rows if r.name == name), None)
    if row is None:
        if verify is not None:
            verify(None)
        raise CommandMissing(name)
    if verify is not None:
        verify(comparable(snapshot(row)))
    return row


@_transaction
def update(
    twitch_id: int,
    actor: AuditActor,
    source: AuditSource,
    name: str,
    new_name: str,
    fields: CommandFields,
    verify: Verify | None = None,
) -> TwitchChatCommand:
    """編輯指令，new_name 與 name 不同就是改名（同一個交易內刪舊列、新增新列，使用次數沿用，紀錄記成一次 update）。"""
    name = normalize_name(name)
    new_name, fields = _normalized(new_name, fields)
    rows = _begin(twitch_id)
    old = _locate(rows, name, verify)
    _check_taken(new_name, fields, rows, name)
    before = snapshot(old)
    if new_name == name:
        row = old
    else:
        use_count = old.use_count
        sqldb.session.delete(old)
        sqldb.session.flush()
        row = TwitchChatCommand(twitch_id=twitch_id, name=new_name, response="", use_count=use_count)
        sqldb.session.add(row)
    row.response = fields.response
    row.aliases = list(fields.aliases)
    row.enabled = fields.enabled
    row.global_cooldown = fields.global_cooldown
    row.user_cooldown = fields.user_cooldown
    row.permission = fields.permission
    row.updated_at = nowtz()
    row.builtin_conflict = None
    sqldb.session.flush()
    record_change(twitch_id, actor, source, "command", new_name, "update", before, snapshot(row))
    _finish(twitch_id)
    return row


@_transaction
def delete(twitch_id: int, actor: AuditActor, source: AuditSource, name: str, verify: Verify | None = None) -> None:
    """刪除整個指令（連同別名）。"""
    name = normalize_name(name)
    rows = _begin(twitch_id)
    row = _locate(rows, name, verify)
    before = snapshot(row)
    sqldb.session.delete(row)
    sqldb.session.flush()
    record_change(twitch_id, actor, source, "command", name, "delete", before, None)
    _finish(twitch_id)


@_transaction
def remove(twitch_id: int, actor: AuditActor, source: AuditSource, name_or_alias: str) -> Removed:
    """聊天室的 `!remove_cmd`：指定名稱就刪整個指令，指定別名就只移除這個別名，指令本身保留。"""
    target = normalize_name(name_or_alias)
    rows = _begin(twitch_id)
    row = next((r for r in rows if r.name == target), None)
    if row is not None:
        before = snapshot(row)
        sqldb.session.delete(row)
        sqldb.session.flush()
        record_change(twitch_id, actor, source, "command", target, "delete", before, None)
        _finish(twitch_id)
        return Removed("command", target)
    owner = next((r for r in rows if target in r.aliases), None)
    if owner is None:
        raise CommandMissing(target)
    before = snapshot(owner)
    owner.aliases = [a for a in owner.aliases if a != target]
    owner.updated_at = nowtz()
    sqldb.session.flush()
    record_change(twitch_id, actor, source, "command", owner.name, "update", before, snapshot(owner))
    _finish(twitch_id)
    return Removed("alias", owner.name)
