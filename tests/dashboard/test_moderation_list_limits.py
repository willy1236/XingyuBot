import pytest

from tests.dashboard.test_channel_moderation import EDITABLE, channel_id, host, put_filter, settings  # noqa: F401


@pytest.mark.parametrize(("kind", "key"), [("link", "whitelist"), ("blocked_word", "words")])
@pytest.mark.parametrize("oversize", ["count", "length"])
def test_moderation_list_limit_returns_422_and_field_hint(host, kind, key, oversize):
    (row,) = (entry for entry in settings(host)["filters"] if entry["kind"] == kind)
    original = {name: row[name] for name in EDITABLE}
    prefix = "example.com/"
    entries = [f"{prefix}{index}" for index in range(101)] if oversize == "count" else [prefix.ljust(101, "字")]

    response = put_filter(host, {"params": {key: entries}}, kind=kind, original=original)

    assert response.status_code == 422
    assert response.json()["field"] == key
    assert "100 項" in response.json()["reason"]
    assert "100 字" in response.json()["reason"]


def test_wildcard_only_blocked_word_returns_422_and_words_field(host):
    (row,) = (entry for entry in settings(host)["filters"] if entry["kind"] == "blocked_word")
    original = {name: row[name] for name in EDITABLE}

    response = put_filter(host, {"params": {"words": ["* *"]}}, kind="blocked_word", original=original)

    assert response.status_code == 422
    assert response.json() == {"error": "invalid_field", "field": "words", "reason": "每個禁字至少需要一個非萬用字元"}


@pytest.mark.parametrize(("kind", "key"), [("link", "whitelist"), ("blocked_word", "words")])
def test_moderation_list_accepts_exactly_100_entries_of_100_characters(host, kind, key):
    (row,) = (entry for entry in settings(host)["filters"] if entry["kind"] == kind)
    original = {name: row[name] for name in EDITABLE}
    entries = [f"example.com/{index}/".ljust(100, "x") for index in range(100)]

    response = put_filter(host, {"params": {key: entries}}, kind=kind, original=original)

    assert response.status_code == 200, response.text
    assert response.json()["filter"]["params"][key] == entries
