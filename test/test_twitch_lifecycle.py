"""T-05：Twitch bot 的結束碼、放棄重連、信號與清理。"""

import ast
import asyncio
import importlib
import signal
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import starServer.twitch_chatbot as chatbot


def make_thread(monkeypatch, *, connected=False, reachable=True) -> chatbot.TwitchBotThread:
    monkeypatch.setattr(chatbot.TwitchBotThread, "_CHAT_CHECK_INTERVAL", 0.01)
    monkeypatch.setattr(chatbot.TwitchBotThread, "_CHAT_DEAD_CHECKS", 2)
    monkeypatch.setattr(chatbot.TwitchBotThread, "_CHAT_START_TIMEOUT", 0.2)
    monkeypatch.setattr(chatbot, "_can_reach", lambda host, port: reachable)
    thread = chatbot.TwitchBotThread()
    thread.chat = MagicMock()
    thread.chat.is_connected.return_value = connected
    return thread


@pytest.fixture
def sentry(monkeypatch):
    exc_mock, msg_mock = MagicMock(), MagicMock()
    monkeypatch.setattr(chatbot, "capture_exception_safe", exc_mock)
    monkeypatch.setattr(chatbot, "capture_message_safe", msg_mock)
    return exc_mock, msg_mock


def test_restart_timeout_reports_and_marks_abnormal(monkeypatch, sentry):
    thread = make_thread(monkeypatch)
    blocker = threading.Event()
    thread.chat.start.side_effect = lambda: blocker.wait(5)

    thread._watch_chat()

    blocker.set()
    assert thread.abnormal
    sentry[1].assert_called_once()
    assert sentry[1].call_args.kwargs["level"] == "error"


def test_stop_failure_reports_and_marks_abnormal(monkeypatch, sentry):
    thread = make_thread(monkeypatch)
    thread.chat.stop.side_effect = RuntimeError("boom")

    thread._watch_chat()

    assert thread.abnormal
    sentry[0].assert_called_once()


def test_network_down_keeps_waiting(monkeypatch, sentry):
    thread = make_thread(monkeypatch, reachable=False)
    worker = threading.Thread(target=thread._watch_chat, daemon=True)
    worker.start()
    time.sleep(0.3)
    assert worker.is_alive()
    thread.stop()
    worker.join(2)

    assert not worker.is_alive()
    assert not thread.abnormal
    thread.chat.stop.assert_not_called()


def test_run_exception_reports_and_skips_cleanup(monkeypatch, sentry):
    async def failing_run():
        raise RuntimeError("init failed")

    monkeypatch.setattr(chatbot, "run", failing_run)
    thread = chatbot.TwitchBotThread()
    thread.cleanup = MagicMock()

    thread.run()

    assert thread.abnormal
    assert not thread.ready.is_set()
    sentry[0].assert_called_once()
    thread.cleanup.assert_not_called()


def test_normal_stop_runs_cleanup(monkeypatch, sentry):
    async def fake_run():
        return MagicMock(), MagicMock(), MagicMock()

    monkeypatch.setattr(chatbot, "run", fake_run)
    thread = make_thread(monkeypatch, connected=True)
    cleaned = []

    async def cleanup():
        cleaned.append(True)

    thread.cleanup = cleanup
    thread.stop()
    thread.run()

    assert cleaned and not thread.abnormal and thread.ready.is_set()


def test_import_does_not_touch_db():
    tree = ast.parse(Path(chatbot.__file__).read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Import, ast.ImportFrom)):
            continue
        names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
        assert "sqldb" not in names and "sclient" not in names, ast.dump(node)[:120]


def test_load_join_channels_populates_module_globals(monkeypatch):
    data = {123: MagicMock(action_channel_id=456), 789: MagicMock(action_channel_id=None)}
    monkeypatch.setattr(chatbot.sclient.sqldb, "get_bot_join_channel_all", lambda: data)
    for name in ("join_channels", "TARGET_CHANNEL", "TARGET_CHANNEL_IDS"):
        monkeypatch.setattr(chatbot, name, getattr(chatbot, name))  # 登記，測試結束還原

    chatbot.load_join_channels()

    assert chatbot.join_channels is data
    assert chatbot.TARGET_CHANNEL == {123: 456, 789: None}
    assert chatbot.TARGET_CHANNEL_IDS == ["123", "789"]


# ---- twitch_main ----


class FakeThread:
    """可控的 TwitchBotThread 替身。"""

    def __init__(self, *, ready=True, run_for=0.0, abnormal=False, die_on_stop=True, hang_cleanup=False):
        self.ready = threading.Event()
        self._ready_on_start = ready
        self.abnormal = abnormal
        self.stopped = threading.Event()
        self._run_for = run_for
        self._die_on_stop = die_on_stop
        self._hang_cleanup = hang_cleanup
        self._done = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self.cleanup_calls = 0

    def _run(self):
        if self._ready_on_start:
            self.ready.set()
        if self._die_on_stop:
            self.stopped.wait(self._run_for or 30)
        else:
            time.sleep(self._run_for)
        self._done.set()

    def start(self):
        self._thread.start()

    def is_alive(self):
        return self._thread.is_alive()

    def join(self, timeout=None):
        self._thread.join(timeout)

    def stop(self):
        self.stopped.set()

    async def cleanup(self):
        self.cleanup_calls += 1
        if self._hang_cleanup:
            await asyncio.sleep(30)


@pytest.fixture
def tm(monkeypatch, request):
    import bootstrap

    monkeypatch.setattr(bootstrap, "setup_runtime", lambda service: None)
    module = importlib.import_module("twitch_main")
    # main() 會替換 SIGINT／SIGTERM handler，測試結束要還原
    for sig in (signal.SIGINT, signal.SIGTERM):
        request.addfinalizer(lambda sig=sig, previous=signal.getsignal(sig): signal.signal(sig, previous))
    module._shutdown.clear()
    monkeypatch.setattr(module, "_thread", None)
    bus = MagicMock()
    monkeypatch.setattr(module, "get_bus", lambda: bus)
    monkeypatch.setattr(module.sclient.sqldb, "init_cache", lambda: None)
    monkeypatch.setattr(module, "capture_exception_safe", MagicMock())
    monkeypatch.setattr(module, "flush_safe", lambda timeout=2: None)
    exits = []
    monkeypatch.setattr(module, "_hard_exit", lambda code: exits.append(code))
    module.bus = bus
    module.exits = exits
    return module


def install(monkeypatch, fake):
    monkeypatch.setattr(chatbot, "TwitchBotThread", lambda: fake)


def test_sigterm_stops_thread_and_exits_zero(tm, monkeypatch):
    fake = FakeThread()
    install(monkeypatch, fake)
    threading.Timer(0.3, lambda: tm._on_signal(15, None)).start()

    with pytest.raises(SystemExit) as info:
        tm.main()

    assert info.value.code == 0
    assert fake.stopped.is_set()
    tm.bus.start.assert_called_once_with("twitch")
    tm.bus.close.assert_called_once()
    assert tm.exits == []


def test_signal_during_thread_construction_still_stops_thread(tm, monkeypatch):
    fake = FakeThread()

    def factory():
        tm._on_signal(15, None)  # handler 此時 _thread 還是 None，只能設旗標
        return fake

    monkeypatch.setattr(chatbot, "TwitchBotThread", factory)

    with pytest.raises(SystemExit) as info:
        tm.main()

    assert info.value.code == 0
    assert fake.stopped.is_set()


def test_startup_failure_exits_nonzero_without_hanging(tm, monkeypatch):
    # thread 在 ready 之前就結束（啟動拋例外）
    fake = FakeThread(ready=False, run_for=0.2, die_on_stop=False)
    fake.abnormal = True
    install(monkeypatch, fake)
    monkeypatch.setattr(tm, "ABNORMAL_CLEANUP_TIMEOUT", 0.2)

    tm.main()

    assert tm.exits == [1]
    tm.bus.start.assert_not_called()


def test_abnormal_end_after_ready_exits_nonzero(tm, monkeypatch):
    fake = FakeThread(run_for=0.2, abnormal=True, die_on_stop=False)
    install(monkeypatch, fake)

    tm.main()

    assert tm.exits == [1]
    assert fake.cleanup_calls == 1
    tm.bus.close.assert_called_once()


def test_main_thread_exception_reports_and_exits_nonzero(tm, monkeypatch):
    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(tm.sclient.sqldb, "init_cache", boom)

    tm.main()

    assert tm.exits == [1]
    tm.capture_exception_safe.assert_called_once()


def test_stuck_cleanup_still_exits_in_time(tm, monkeypatch):
    fake = FakeThread(run_for=0.1, abnormal=True, die_on_stop=False, hang_cleanup=True)
    install(monkeypatch, fake)
    monkeypatch.setattr(tm, "ABNORMAL_CLEANUP_TIMEOUT", 0.3)

    start = time.monotonic()
    tm.main()

    assert tm.exits == [1]
    assert time.monotonic() - start < 3


def test_shutdown_grace_expires_as_abnormal(tm, monkeypatch):
    fake = FakeThread(run_for=30, die_on_stop=False)  # 收到 stop 也不結束
    install(monkeypatch, fake)
    monkeypatch.setattr(tm, "SHUTDOWN_GRACE", 0.3)
    monkeypatch.setattr(tm, "ABNORMAL_CLEANUP_TIMEOUT", 0.2)
    threading.Timer(0.3, lambda: tm._on_signal(15, None)).start()

    tm.main()

    assert tm.exits == [1]
