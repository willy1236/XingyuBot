import pytest

from starlib import twitch_moderation


@pytest.mark.parametrize("word", ["*", "***", "* *"])
def test_star_only_blocked_words_are_rejected(word):
    values = {"enabled": True, "exempt_level": "vip", "params": {"words": [word]}, "notice": None, "silent": True}
    with pytest.raises(twitch_moderation.InvalidField, match="非萬用字元"):
        twitch_moderation.validate_filter("blocked_word", values)


def test_existing_empty_patterns_do_not_match_every_message():
    assert not twitch_moderation.detect_blocked_word("Hello world", ["*", "**", "* *", "bad*word"])
    assert twitch_moderation.detect_blocked_word("Bad Word", ["*", "**", "bad*word"])
