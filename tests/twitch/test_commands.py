"""twitch_bot.commands：自訂指令的觸發（開關、權限、冷卻、別名、使用次數）與聊天室管理指令（真實 PostgreSQL，測完 rollback）。"""

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from starlib import twitch_audit, twitch_commands
from starlib.database import TwitchBotJoinChannel, TwitchChatCommand
from starlib.messaging import cache_invalidation
from starlib.twitch_audit import list_changes
from starServer.twitch_bot import commands

TWITCH_ID = 2000000071
ROOM = SimpleNamespace(room_id=str(TWITCH_ID), name="host")


def run(coro):
    return asyncio.run(coro)


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture(autouse=True)
def _env(monkeypatch, repo):
    for module in (commands, twitch_commands, twitch_audit):
        monkeypatch.setattr(module, "sqldb", repo)
    monkeypatch.setattr(cache_invalidation, "invalidate", lambda *a, **k: None)
    # 本機 DB 可能留有手動測試的頻道列；在外層交易內換成 enabled 的，測完隨 rollback 還原
    existing = repo.session.get(TwitchBotJoinChannel, TWITCH_ID)
    if existing is not None:
        repo.session.delete(existing)
        repo.session.flush()
    repo.add(TwitchBotJoinChannel(twitch_id=TWITCH_ID, state="enabled"))
    monkeypatch.setattr(commands, "_global_used", {})
    monkeypatch.setattr(commands, "_user_used", {})
    clock = Clock()
    monkeypatch.setattr(commands, "_now", clock)
    monkeypatch.setattr(commands.speech, "say", AsyncMock(return_value=True))
    monkeypatch.setattr(commands, "check_template", AsyncMock(return_value="ok"))
    return clock


@pytest.fixture
def clock(_env):
    return _env


def add(repo, name="hi", **kwargs):
    kwargs.setdefault("response", "hello {user}")
    repo.save_twitch_chat_command(TwitchChatCommand(twitch_id=TWITCH_ID, name=name, **kwargs))
    repo.cache.twitch_cmd.load(repo.get_raw_chat_command_all())


def chatter(name="viewer", *, uid="100", mod=False, vip=False, subscriber=False):
    return SimpleNamespace(id=uid, name=name, display_name=name.title(), mod=mod, vip=vip, subscriber=subscriber)


def message(text="!hi", user=None):
    return SimpleNamespace(text=text, room=ROOM, user=user or chatter(), reply=AsyncMock())


def trigger(text="!hi", user=None) -> bool:
    msg = message(text, user)
    commands.speech.say.reset_mock()
    run(commands.respond_to_chat_command(msg))
    return commands.speech.say.await_count == 1


# ── 觸發 ──


def test_觸發時把變數交給_say(repo):
    add(repo, response="{user} 說 {args}，第 {count} 次")
    msg = message("!hi 你好 世界", chatter("viewer"))
    run(commands.respond_to_chat_command(msg))
    [call] = commands.speech.say.await_args_list
    assert call.args[:3] == ("host", TWITCH_ID, "{user} 說 {args}，第 {count} 次")
    ctx = call.args[3]
    assert (ctx.user, ctx.args, ctx.count, ctx.channel, ctx.twitch_id) == ("Viewer", "你好 世界", 1, "host", TWITCH_ID)
    assert call.kwargs == {"source_kind": "command", "source_key": "hi", "reply_to": msg}


def test_沒有參數時_args_是空字串(repo):
    add(repo)
    run(commands.respond_to_chat_command(message("!hi")))
    assert commands.speech.say.await_args.args[3].args == ""


def test_不存在_內建名稱_不是指令的訊息都不回應(repo):
    add(repo)
    assert not trigger("!nope")
    assert not trigger("hi")
    assert not trigger("!add_cmd hi x")


def test_指令名稱不分大小寫(repo):
    add(repo)
    assert trigger("!HI")


def test_關閉後不回應_重新打開後恢復(repo):
    add(repo, enabled=False)
    assert not trigger()
    add(repo, enabled=True)
    assert trigger()


def test_別名與主名稱同樣回應_次數一起累加(repo):
    add(repo, aliases=["h"], global_cooldown=0)
    trigger("!h")
    assert commands.speech.say.await_args.args[3].count == 1
    trigger("!hi")
    assert commands.speech.say.await_args.args[3].count == 2
    assert repo.get_chat_command("hi", TWITCH_ID).use_count == 2


def test_指令在計次前被刪除時不發言(repo):
    add(repo)
    repo.delete_twitch_chat_command(TWITCH_ID, "hi")
    assert not trigger()


# ── 權限 ──

BROADCASTER = chatter("host", uid=str(TWITCH_ID))
VIEWERS = {
    "everyone": chatter(),
    "subscriber": chatter(subscriber=True),
    "vip": chatter(vip=True),
    "mod": chatter(mod=True),
    "broadcaster": BROADCASTER,
}


@pytest.mark.parametrize("required", list(VIEWERS))
@pytest.mark.parametrize("who", list(VIEWERS))
def test_權限層級是單選且有高低(repo, required, who):
    add(repo, permission=required, global_cooldown=0)
    allowed = list(VIEWERS).index(who) >= list(VIEWERS).index(required)
    assert trigger(user=VIEWERS[who]) is allowed


def test_mod_權限一般觀眾與_vip_不回應_mod_與實況主會(repo):
    add(repo, permission="mod", global_cooldown=0)
    assert not trigger(user=chatter())
    assert not trigger(user=chatter(vip=True))
    assert trigger(user=chatter(mod=True))
    assert trigger(user=BROADCASTER)


def test_實況主以_user_id_判斷而不是名稱(repo):
    add(repo, permission="broadcaster")
    assert not trigger(user=chatter("host", uid="1"))


# ── 冷卻 ──


def test_全體冷卻_期間內一般觀眾不回應_過了恢復(repo, clock):
    add(repo, global_cooldown=30)
    assert trigger(user=chatter("a", uid="1"))
    clock.now += 29
    assert not trigger(user=chatter("b", uid="2"))
    clock.now += 2
    assert trigger(user=chatter("b", uid="2"))


def test_冷卻是每個指令各自計算(repo, clock):
    add(repo, "hi", global_cooldown=30)
    add(repo, "yo", global_cooldown=30)
    assert trigger("!hi")
    assert trigger("!yo")


def test_別名與主名稱共用冷卻(repo):
    add(repo, aliases=["h"], global_cooldown=30)
    assert trigger("!hi")
    assert not trigger("!h")


def test_實況主與_mod_不受冷卻限制_也不會觸發冷卻(repo):
    add(repo, global_cooldown=30, user_cooldown=30)
    assert trigger(user=BROADCASTER)
    assert trigger(user=BROADCASTER)
    assert trigger(user=chatter(mod=True))
    assert trigger(user=chatter(mod=True))
    assert trigger(user=chatter())  # mod 觸發沒有佔走一般觀眾的冷卻


def test_個人冷卻_同一人被擋_其他人可以(repo, clock):
    add(repo, global_cooldown=0, user_cooldown=60)
    alice, bob = chatter("alice", uid="1"), chatter("bob", uid="2")
    assert trigger(user=alice)
    assert not trigger(user=alice)
    assert trigger(user=bob)
    clock.now += 61
    assert trigger(user=alice)


def test_冷卻為_0_不限制(repo):
    add(repo, global_cooldown=0, user_cooldown=0)
    assert trigger()
    assert trigger()


def test_沒通過冷卻不計次(repo):
    add(repo, global_cooldown=30)
    trigger()
    trigger()
    assert repo.get_chat_command("hi", TWITCH_ID).use_count == 1


# ── 快取失效 ──


def test_收到失效通知後重讀該頻道(repo):
    repo.cache.twitch_cmd.load({})
    repo.save_twitch_chat_command(TwitchChatCommand(twitch_id=TWITCH_ID, name="hi", response="x", aliases=["h"]))
    commands._reload(str(TWITCH_ID))
    assert repo.get_twitch_cmd_response_cache(TWITCH_ID, "h").response == "x"
    repo.delete_twitch_chat_command(TWITCH_ID, "hi")
    commands._reload(str(TWITCH_ID))
    assert repo.get_twitch_cmd_response_cache(TWITCH_ID, "hi") is None


def test_失效通知沒有_key_時重讀全部(repo):
    repo.save_twitch_chat_command(TwitchChatCommand(twitch_id=TWITCH_ID, name="hi", response="x"))
    commands._reload(None)
    assert repo.get_twitch_cmd_response_cache(TWITCH_ID, "hi").response == "x"


# ── 聊天室管理指令 ──


def command(parameter, user=None):
    return SimpleNamespace(parameter=parameter, room=ROOM, user=user or chatter(mod=True), reply=AsyncMock())


def replied(cmd) -> str:
    return cmd.reply.await_args.args[0]


def test_add_cmd_新增並記在聊天室來源(repo):
    cmd = command("Hi 哈囉 {user}")
    run(commands.add_chat_command(cmd))
    assert replied(cmd) == "已新增指令：hi"
    row = twitch_commands.find(TWITCH_ID, "hi")
    assert (row.response, row.global_cooldown, row.permission, row.enabled) == ("哈囉 {user}", 30, "everyone", True)
    [entry] = list_changes(TWITCH_ID)
    assert (entry.source, entry.action) == ("chat", "create")
    assert (entry.actor.platform, entry.actor.id, entry.actor.name) == ("twitch", "100", "Viewer")


def test_觀眾輸入_uptime_不會觸發舊的同名自訂指令(repo):
    # 模擬尚有舊指令的資料，驗證內建名稱優先。
    add(repo, "uptime")
    assert not trigger("!uptime")


@pytest.mark.parametrize("name", ["title", "permit", "regular"])
def test_add_cmd_拒絕與新內建指令同名的自訂指令(repo, name):
    cmd = command(f"{name} hello", BROADCASTER)
    run(commands.add_chat_command(cmd))
    assert "內建指令" in replied(cmd)
    assert twitch_commands.find(TWITCH_ID, name) is None


def test_管理指令只有實況主與_mod_能用(repo):
    for handler in (commands.add_chat_command, commands.edit_chat_command, commands.remove_chat_command):
        cmd = command("hi x", chatter())
        run(handler(cmd))
        cmd.reply.assert_not_awaited()
    assert twitch_commands.list_commands(TWITCH_ID) == []
    run(commands.add_chat_command(command("hi x", BROADCASTER)))
    assert twitch_commands.find(TWITCH_ID, "hi") is not None


@pytest.mark.parametrize("state", ["inactive", "disabled", None])
def test_頻道不是_enabled_時管理指令拒絕寫入(repo, state):
    """後台刪除或停用資料後、bot 離開聊天室之前，聊天室的管理指令不能把資料寫回去。"""
    add(repo, response="原本")
    row = repo.session.get(TwitchBotJoinChannel, TWITCH_ID)
    if state is None:
        repo.delete(row)
    else:
        row.state = state
        repo.merge(row)
    for handler, text in (
        (commands.add_chat_command, "new 新的"),
        (commands.edit_chat_command, "hi 新的"),
        (commands.remove_chat_command, "hi"),
    ):
        cmd = command(text, BROADCASTER)
        run(handler(cmd))
        assert replied(cmd) == "星羽目前未啟用，無法修改指令"
    assert [(c.name, c.response) for c in twitch_commands.list_commands(TWITCH_ID)] == [("hi", "原本")]
    assert list_changes(TWITCH_ID) == []


def test_關閉_mod_協作後_mod_的管理指令回覆權限不足_實況主照常(repo):
    add(repo, response="原本")
    row = repo.session.get(TwitchBotJoinChannel, TWITCH_ID)
    row.mod_collab_enabled = False
    repo.merge(row)
    for handler, text in (
        (commands.add_chat_command, "new 新的"),
        (commands.edit_chat_command, "hi 新的"),
        (commands.remove_chat_command, "hi"),
    ):
        cmd = command(text)
        run(handler(cmd))
        assert replied(cmd).startswith("權限不足")
    assert [(c.name, c.response) for c in twitch_commands.list_commands(TWITCH_ID)] == [("hi", "原本")]
    assert list_changes(TWITCH_ID) == []

    viewer = command("new 新的", chatter())
    run(commands.add_chat_command(viewer))
    viewer.reply.assert_not_awaited()

    run(commands.add_chat_command(command("new 新的", BROADCASTER)))
    assert twitch_commands.find(TWITCH_ID, "new") is not None

    listing = command("")
    run(commands.list_chat_command(listing))
    assert "hi" in replied(listing)


def test_重新開啟_mod_協作後_mod_又能管理指令(repo):
    row = repo.session.get(TwitchBotJoinChannel, TWITCH_ID)
    row.mod_collab_enabled = False
    repo.merge(row)
    run(commands.add_chat_command(command("new 新的")))
    row.mod_collab_enabled = True
    repo.merge(row)

    cmd = command("new 新的")
    run(commands.add_chat_command(cmd))

    assert replied(cmd) == "已新增指令：new"


def test_add_cmd_同名或同別名拒絕不覆蓋_與內建同名拒絕(repo):
    add(repo, aliases=["h"], response="原本")
    for name in ("hi", "h", "add_cmd", "edit_cmd"):
        cmd = command(f"{name} 新的")
        run(commands.add_chat_command(cmd))
        assert twitch_commands.find(TWITCH_ID, "hi").response == "原本"
        assert name in replied(cmd)
        commands.check_template.assert_not_awaited()  # 擋在 AutoMod 檢查之前，不花額度
    assert len(twitch_commands.list_commands(TWITCH_ID)) == 1


@pytest.mark.parametrize(("result", "text"), [("blocked", "擋下"), ("unavailable", "稍後再試")])
def test_add_cmd_AutoMod_擋下或無法檢查時不儲存(repo, result, text):
    commands.check_template.return_value = result
    cmd = command("hi 壞話")
    run(commands.add_chat_command(cmd))
    assert text in replied(cmd)
    assert twitch_commands.list_commands(TWITCH_ID) == []


def test_add_cmd_缺參數時顯示用法(repo):
    cmd = command("hi")
    run(commands.add_chat_command(cmd))
    assert "用法" in replied(cmd)


def test_edit_cmd_只改回應_其他欄位與次數不動(repo):
    add(repo, aliases=["h"], global_cooldown=5, user_cooldown=6, permission="mod", enabled=False, use_count=9)
    cmd = command("H 新的回應")
    run(commands.edit_chat_command(cmd))
    assert replied(cmd) == "已修改指令：hi"
    row = twitch_commands.find(TWITCH_ID, "hi")
    assert (row.response, row.aliases, row.global_cooldown, row.user_cooldown) == ("新的回應", ["h"], 5, 6)
    assert (row.permission, row.enabled, row.use_count) == ("mod", False, 9)
    [entry] = list_changes(TWITCH_ID)
    assert (entry.action, entry.source, entry.target_key) == ("update", "chat", "hi")
    assert (entry.before["response"], entry.after["response"]) == ("hello {user}", "新的回應")


def test_edit_cmd_不存在與內建指令拒絕(repo):
    for name in ("nope", "add_cmd"):
        cmd = command(f"{name} x")
        run(commands.edit_chat_command(cmd))
        assert name in replied(cmd)
    assert list_changes(TWITCH_ID) == []


@pytest.mark.parametrize(("result", "text"), [("blocked", "擋下"), ("unavailable", "稍後再試")])
def test_edit_cmd_AutoMod_擋下或無法檢查時不改(repo, result, text):
    add(repo, response="原本")
    commands.check_template.return_value = result
    cmd = command("hi 壞話")
    run(commands.edit_chat_command(cmd))
    assert text in replied(cmd)
    assert twitch_commands.find(TWITCH_ID, "hi").response == "原本"


def test_edit_cmd_回應超過_500_字拒絕(repo):
    add(repo, response="原本")
    cmd = command("hi " + "a" * 501)
    run(commands.edit_chat_command(cmd))
    assert twitch_commands.find(TWITCH_ID, "hi").response == "原本"
    commands.check_template.assert_not_awaited()


def test_edit_cmd_檢查期間後台改過同一個指令時不蓋掉(repo):
    add(repo, response="原本")

    async def edited_meanwhile(*_):
        row = twitch_commands.find(TWITCH_ID, "hi")
        twitch_commands.update(
            TWITCH_ID,
            twitch_audit.AuditActor("discord", "1", "web"),
            "dashboard",
            "hi",
            "hi",
            twitch_commands.CommandFields("後台改的", enabled=row.enabled),
        )
        return "ok"

    commands.check_template.side_effect = edited_meanwhile
    cmd = command("hi 聊天室改的")
    run(commands.edit_chat_command(cmd))
    assert "再試一次" in replied(cmd)
    assert twitch_commands.find(TWITCH_ID, "hi").response == "後台改的"


def test_remove_cmd_指定別名只移除別名(repo):
    add(repo, aliases=["h"])
    cmd = command("!H")
    run(commands.remove_chat_command(cmd))
    assert "別名" in replied(cmd)
    assert twitch_commands.find(TWITCH_ID, "h") is None
    assert twitch_commands.find(TWITCH_ID, "hi") is not None


def test_remove_cmd_指定名稱移除整個指令_不存在時提示(repo):
    add(repo, aliases=["h"])
    run(commands.remove_chat_command(command("hi")))
    assert twitch_commands.find(TWITCH_ID, "h") is None
    cmd = command("hi")
    run(commands.remove_chat_command(cmd))
    assert "不存在" in replied(cmd)


def test_list_cmd_不列出關閉的指令_也查不到(repo):
    add(repo, "on")
    add(repo, "off", enabled=False)
    cmd = command("")
    run(commands.list_chat_command(cmd))
    assert "on" in replied(cmd) and "off" not in replied(cmd)
    cmd = command("off")
    run(commands.list_chat_command(cmd))
    assert "不存在" in replied(cmd)
    run(commands.list_chat_command(cmd := command("on")))
    assert replied(cmd) == "on：hello {user}"


def test_list_cmd_沒有指令時提示(repo):
    cmd = command("")
    run(commands.list_chat_command(cmd))
    assert "沒有" in replied(cmd)


# ── 寫入後 bot 本機先更新快取 ──


def test_聊天室新增後不靠_Redis_通知本機快取就更新(repo):
    # _env 已把 invalidate 換成什麼都不做，等同 Redis 連不上
    repo.cache.twitch_cmd.load({})
    run(commands.add_chat_command(command("hi 哈囉")))
    assert repo.get_twitch_cmd_response_cache(TWITCH_ID, "hi").response == "哈囉"


def test_聊天室修改與移除後本機快取也立即更新(repo):
    add(repo, aliases=["h"])
    run(commands.edit_chat_command(command("hi 新的")))
    assert repo.get_twitch_cmd_response_cache(TWITCH_ID, "h").response == "新的"
    run(commands.remove_chat_command(command("h")))
    assert repo.get_twitch_cmd_response_cache(TWITCH_ID, "h") is None
    assert repo.get_twitch_cmd_response_cache(TWITCH_ID, "hi") is not None
    run(commands.remove_chat_command(command("hi")))
    assert repo.get_twitch_cmd_response_cache(TWITCH_ID, "hi") is None


# ── DB 工作不在 event loop thread 上做 ──


def test_管理指令的資料庫讀寫在別的_thread_並在該_thread_釋放_session(repo, monkeypatch):
    loop_thread = threading.get_ident()
    db_threads: set[int] = set()
    released: list[int] = []
    for name in ("validate", "create", "find", "update", "remove", "list_commands"):
        original = getattr(twitch_commands, name)

        def spy(*args, _original=original, **kwargs):
            db_threads.add(threading.get_ident())
            return _original(*args, **kwargs)

        monkeypatch.setattr(twitch_commands, name, spy)
    original_release = repo.release_session
    monkeypatch.setattr(
        repo, "release_session", lambda: (released.append(threading.get_ident()), original_release())[1]
    )

    run(commands.add_chat_command(command("hi 哈囉")))
    run(commands.edit_chat_command(command("hi 新的")))
    run(commands.list_chat_command(command("")))
    run(commands.list_chat_command(command("hi")))
    run(commands.remove_chat_command(command("hi")))

    assert db_threads and loop_thread not in db_threads
    assert set(released) >= db_threads
