"""starlib.twitch_event_responses：預設文字、驗證與寫入（真實 PostgreSQL，綁外層交易，測完 rollback）。"""

import re

import pytest

from starlib import twitch_audit
from starlib import twitch_event_responses as responses
from starlib.messaging import cache_invalidation
from starlib.twitch_audit import AuditActor, list_changes
from starlib.twitch_event_responses import EventResponseInvalid, UnknownEventKind

TWITCH_ID = 2000000071
ACTOR = AuditActor("twitch", "1", "streamer")


@pytest.fixture(autouse=True)
def _env(monkeypatch, repo):
    monkeypatch.setattr(responses, "sqldb", repo)
    monkeypatch.setattr(twitch_audit, "sqldb", repo)
    invalidated: list[tuple[str, str | None]] = []
    monkeypatch.setattr(cache_invalidation, "invalidate", lambda cache, key=None, **_: invalidated.append((cache, key)))
    return invalidated


@pytest.fixture
def invalidated(_env):
    return _env


def save(kind="follow", enabled=True, template="歡迎 {user}", verify=None):
    return responses.save(TWITCH_ID, ACTOR, "dashboard", kind, enabled, template, verify)


def by_kind():
    return {r.kind: r for r in responses.list_responses(TWITCH_ID)}


def test_沒有資料列時六種都是預設文字且關閉():
    rows = responses.list_responses(TWITCH_ID)
    assert [r.kind for r in rows] == list(responses.KINDS)
    assert all(not r.enabled and r.is_default and r.template == responses.DEFAULTS[r.kind] for r in rows)


def test_每種事件的預設文字只用自己列出的變數():
    for kind, template in responses.DEFAULTS.items():
        listed = {v["token"] for v in responses.default_response(kind).variables}
        used = {"{" + name + "}" for name in re.findall(r"\{(\w+)\}", template)}
        assert used <= listed, kind


def test_新增自訂文字後有紀錄並通知_bot(invalidated):
    result = save()
    assert (result.enabled, result.template, result.is_default) == (True, "歡迎 {user}", False)
    assert by_kind()["follow"].template == "歡迎 {user}"
    [entry] = list_changes(TWITCH_ID)
    assert (entry.action, entry.target_kind, entry.target_key, entry.source) == (
        "create",
        "event_response",
        "follow",
        "dashboard",
    )
    assert entry.before is None and entry.after == {"enabled": True, "template": "歡迎 {user}"}
    assert invalidated == [("twitch_event_response", str(TWITCH_ID))]


def test_改文字與關閉記成_update():
    save()
    save(enabled=False, template="新的")
    [latest, _] = list_changes(TWITCH_ID)
    assert latest.action == "update"
    assert latest.before == {"enabled": True, "template": "歡迎 {user}"}
    assert latest.after == {"enabled": False, "template": "新的"}
    assert by_kind()["follow"].enabled is False


def test_關閉且文字是預設_等於沒有設定_刪列():
    save(enabled=False, template="自訂")
    result = save(enabled=False, template=responses.DEFAULTS["follow"])
    assert (result.enabled, result.is_default) == (False, True)
    assert by_kind()["follow"].is_default and not by_kind()["follow"].enabled
    assert list_changes(TWITCH_ID)[0].action == "delete"


def test_開啟且文字是預設_存成一列_之後仍是開啟():
    result = save(template=responses.DEFAULTS["follow"])
    assert (result.enabled, result.is_default) == (True, True)
    assert by_kind()["follow"].enabled is True
    [entry] = list_changes(TWITCH_ID)
    assert entry.action == "create" and entry.after == {"enabled": True, "template": responses.DEFAULTS["follow"]}


def test_有效設定沒變時不寫入也不留紀錄(invalidated):
    save(enabled=False, template=responses.DEFAULTS["follow"])  # 本來就是關閉加預設文字
    assert list_changes(TWITCH_ID) == [] and invalidated == []
    save()
    invalidated.clear()
    save()
    assert len(list_changes(TWITCH_ID)) == 1 and invalidated == []


def test_開啟時恢復預設只換文字_保留開關(invalidated):
    save()
    result = responses.reset(TWITCH_ID, ACTOR, "dashboard", "follow")
    assert (result.enabled, result.template, result.is_default) == (True, responses.DEFAULTS["follow"], True)
    assert by_kind()["follow"].enabled is True
    [entry, _] = list_changes(TWITCH_ID)
    assert entry.action == "update"
    assert entry.before == {"enabled": True, "template": "歡迎 {user}"}
    assert entry.after == {"enabled": True, "template": responses.DEFAULTS["follow"]}
    invalidated.clear()
    responses.reset(TWITCH_ID, ACTOR, "dashboard", "follow")  # 文字已是預設，冪等
    assert len(list_changes(TWITCH_ID)) == 2 and invalidated == []


def test_關閉時恢復預設等於刪列(invalidated):
    save(enabled=False, template="自訂")
    result = responses.reset(TWITCH_ID, ACTOR, "dashboard", "follow")
    assert (result.enabled, result.is_default) == (False, True)
    [entry, _] = list_changes(TWITCH_ID)
    assert (entry.action, entry.after) == ("delete", None)
    assert invalidated[-1] == ("twitch_event_response", str(TWITCH_ID))


@pytest.mark.parametrize("template", ["", "   ", "a" * 501])
def test_文字不合法(template):
    with pytest.raises(EventResponseInvalid) as exc:
        save(template=template)
    assert exc.value.field == "template"
    assert list_changes(TWITCH_ID) == []


def test_不認得的事件種類():
    with pytest.raises(UnknownEventKind):
        save(kind="nope")
    with pytest.raises(UnknownEventKind):
        responses.reset(TWITCH_ID, ACTOR, "dashboard", "nope")


def test_verify_以有效值為準_有衝突就不寫入():
    seen: list[dict] = []

    def verify(current):
        seen.append(current)
        raise RuntimeError("conflict")

    with pytest.raises(RuntimeError):
        save(verify=verify)
    assert seen == [{"enabled": "false", "response": responses.DEFAULTS["follow"]}]
    assert by_kind()["follow"].is_default and list_changes(TWITCH_ID) == []


def test_各頻道互不影響():
    save()
    assert not responses.list_responses(TWITCH_ID + 1)[1].enabled
