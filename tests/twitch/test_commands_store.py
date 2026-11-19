"""starlib.twitch_commands：自訂指令的驗證與寫入（真實 PostgreSQL，綁外層交易，測完 rollback）。"""

import pytest

from starlib import twitch_audit, twitch_commands
from starlib.messaging import cache_invalidation
from starlib.twitch_audit import AuditActor, list_changes
from starlib.twitch_commands import CommandFields, CommandInvalid, CommandMissing

TWITCH_ID = 2000000061
ACTOR = AuditActor("twitch", "1", "streamer")


@pytest.fixture(autouse=True)
def _env(monkeypatch, repo):
    monkeypatch.setattr(twitch_commands, "sqldb", repo)
    monkeypatch.setattr(twitch_audit, "sqldb", repo)
    invalidated: list[tuple[str, str | None]] = []
    monkeypatch.setattr(cache_invalidation, "invalidate", lambda cache, key=None, **_: invalidated.append((cache, key)))
    return invalidated


@pytest.fixture
def invalidated(_env):
    return _env


def make(name="hi", **kwargs):
    kwargs.setdefault("response", "hello")
    return twitch_commands.create(TWITCH_ID, ACTOR, "dashboard", name, CommandFields(**kwargs))


def test_新增後有紀錄_有預設值_並通知_bot(invalidated):
    row = make("!Hi")
    assert row.name == "hi"
    assert (row.aliases, row.enabled, row.global_cooldown, row.user_cooldown) == ([], True, 30, 0)
    assert (row.permission, row.use_count) == ("everyone", 0)
    [entry] = list_changes(TWITCH_ID)
    assert (entry.action, entry.target_kind, entry.target_key, entry.source) == ("create", "command", "hi", "dashboard")
    assert entry.before is None and entry.after["response"] == "hello"
    assert invalidated == [("twitch_cmd", str(TWITCH_ID))]


def test_名稱與別名正規化_別名去重(repo):
    row = make("Hi", aliases=("!H", "h", "Yo"))
    assert row.aliases == ["h", "yo"]


@pytest.mark.parametrize(
    ("name", "fields", "field"),
    [
        ("", {}, "name"),
        ("a" * 26, {}, "name"),
        ("a b", {}, "name"),
        ("hi", {"aliases": ("hi",)}, "aliases"),
        ("hi", {"aliases": tuple(f"a{i}" for i in range(11))}, "aliases"),
        ("hi", {"aliases": ("x" * 26,)}, "aliases"),
        ("hi", {"response": ""}, "response"),
        ("hi", {"response": "a" * 501}, "response"),
        ("hi", {"global_cooldown": -1}, "global_cooldown"),
        ("hi", {"global_cooldown": 3601}, "global_cooldown"),
        ("hi", {"user_cooldown": 3601}, "user_cooldown"),
        ("hi", {"permission": "admin"}, "permission"),
    ],
)
def test_格式與範圍不合法(name, fields, field):
    with pytest.raises(CommandInvalid) as e:
        make(name, **fields)
    assert e.value.field == field
    assert list_changes(TWITCH_ID) == []


def test_邊界值可以儲存():
    make("a" * 25, response="a" * 500, global_cooldown=0, user_cooldown=3600, permission="broadcaster")


@pytest.mark.parametrize(
    ("name", "aliases", "field"),
    [
        ("hi", (), "name"),  # 名稱撞名稱
        ("h", (), "name"),  # 名稱撞別名
        ("new", ("hi",), "aliases"),  # 別名撞名稱
        ("new", ("h",), "aliases"),  # 別名撞別名
        ("add_cmd", (), "name"),  # 撞內建
        ("new", ("list_cmd",), "aliases"),
    ],
)
def test_重複與內建指令同名被拒絕且不覆蓋(name, aliases, field):
    make("hi", aliases=("h",))
    with pytest.raises(CommandInvalid) as e:
        make(name, aliases=aliases)
    assert e.value.field == field
    assert [c.name for c in twitch_commands.list_commands(TWITCH_ID)] == ["hi"]
    assert len(list_changes(TWITCH_ID)) == 1


def test_validate_不寫入也能擋重複():
    make("hi", aliases=("h",))
    with pytest.raises(CommandInvalid):
        twitch_commands.validate(TWITCH_ID, "h", CommandFields("x"))
    twitch_commands.validate(TWITCH_ID, "hi", CommandFields("x", aliases=("h",)), current_name="hi")


def test_編輯保留使用次數並記前後(repo):
    make("hi")
    repo.increment_twitch_cmd_use_count(TWITCH_ID, "hi")
    row = twitch_commands.update(
        TWITCH_ID, ACTOR, "dashboard", "hi", "hi", CommandFields("bye", enabled=False, permission="mod")
    )
    assert (row.response, row.enabled, row.permission, row.use_count) == ("bye", False, "mod", 1)
    entry = list_changes(TWITCH_ID)[0]
    assert (entry.action, entry.before["response"], entry.after["response"]) == ("update", "hello", "bye")


def test_改名在同一次紀錄內_使用次數沿用(repo):
    make("hi")
    repo.increment_twitch_cmd_use_count(TWITCH_ID, "hi")
    repo.increment_twitch_cmd_use_count(TWITCH_ID, "hi")
    row = twitch_commands.update(TWITCH_ID, ACTOR, "dashboard", "hi", "hello", CommandFields("x"))
    assert (row.name, row.use_count) == ("hello", 2)
    assert [c.name for c in twitch_commands.list_commands(TWITCH_ID)] == ["hello"]
    entries = list_changes(TWITCH_ID)
    assert len(entries) == 2  # 新增一次、改名一次
    assert (entries[0].action, entries[0].target_key) == ("update", "hello")
    assert (entries[0].before["name"], entries[0].after["name"]) == ("hi", "hello")


def test_改名撞到別人_不排除自己的別名():
    make("hi", aliases=("h",))
    make("other")
    with pytest.raises(CommandInvalid):
        twitch_commands.update(TWITCH_ID, ACTOR, "dashboard", "other", "h", CommandFields("x"))
    # 自己改回自己的名稱或自己的別名不算重複
    twitch_commands.update(TWITCH_ID, ACTOR, "dashboard", "hi", "hi", CommandFields("x", aliases=("h", "j")))


def test_verify_衝突時不寫入(repo):
    make("hi")

    class Stop(Exception):
        pass

    def verify(current):
        assert current["response"] == "hello"
        raise Stop

    with pytest.raises(Stop):
        twitch_commands.update(TWITCH_ID, ACTOR, "dashboard", "hi", "hi", CommandFields("bye"), verify)
    assert twitch_commands.find(TWITCH_ID, "hi").response == "hello"
    assert len(list_changes(TWITCH_ID)) == 1


def test_指令已被刪除時_verify_收到_None():
    seen = []
    with pytest.raises(CommandMissing):
        twitch_commands.update(TWITCH_ID, ACTOR, "dashboard", "nope", "nope", CommandFields("x"), seen.append)
    assert seen == [None]


def test_刪除整個指令連別名(invalidated):
    make("hi", aliases=("h",))
    invalidated.clear()
    twitch_commands.delete(TWITCH_ID, ACTOR, "dashboard", "hi")
    assert twitch_commands.find(TWITCH_ID, "h") is None
    entry = list_changes(TWITCH_ID)[0]
    assert (entry.action, entry.after, entry.before["aliases"]) == ("delete", None, ["h"])
    assert invalidated == [("twitch_cmd", str(TWITCH_ID))]


def test_remove_指定別名只移除別名():
    make("hi", aliases=("h", "j"))
    result = twitch_commands.remove(TWITCH_ID, ACTOR, "chat", "!H")
    assert (result.kind, result.name) == ("alias", "hi")
    row = twitch_commands.find(TWITCH_ID, "hi")
    assert row.aliases == ["j"]
    entry = list_changes(TWITCH_ID)[0]
    assert (entry.action, entry.source, entry.target_key) == ("update", "chat", "hi")
    assert entry.before["aliases"] == ["h", "j"] and entry.after["aliases"] == ["j"]


def test_remove_指定名稱刪整個指令_不存在時_raise():
    make("hi", aliases=("h",))
    assert twitch_commands.remove(TWITCH_ID, ACTOR, "chat", "hi").kind == "command"
    assert twitch_commands.find(TWITCH_ID, "h") is None
    with pytest.raises(CommandMissing):
        twitch_commands.remove(TWITCH_ID, ACTOR, "chat", "hi")


def test_別的頻道的指令互不影響():
    make("hi")
    twitch_commands.create(TWITCH_ID + 1, ACTOR, "chat", "hi", CommandFields("x"))
    assert twitch_commands.find(TWITCH_ID + 1, "hi").response == "x"
    assert twitch_commands.find(TWITCH_ID, "hi").response == "hello"


def test_comparable_是字串且別名排序():
    values = {
        "name": "hi",
        "response": "a",
        "aliases": ["b", "a"],
        "enabled": True,
        "global_cooldown": 30,
        "user_cooldown": 0,
        "permission": "everyone",
    }
    assert twitch_commands.comparable(values) == {
        "name": "hi",
        "response": "a",
        "aliases": "a\nb",
        "enabled": "true",
        "global_cooldown": "30",
        "user_cooldown": "0",
        "permission": "everyone",
    }
