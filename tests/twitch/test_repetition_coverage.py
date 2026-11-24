from itertools import product

from starlib.twitch_moderation import detect_repetition


def _covered_by_adjacent_copies(text: str) -> int:
    covered = set()
    for start in range(len(text)):
        for width in range(1, (len(text) - start) // 2 + 1):
            split, end = start + width, start + 2 * width
            if text[start:split] == text[split:end]:
                covered.update(range(start, end))
    return len(covered)


def test_repetition_preserves_character_coverage():
    messages = [
        *("".join(chars) for chars in product("哈a", repeat=10)),
        "甲乙丙甲乙丙 xxxxx 4554 안녕 안녕",
        "Mississippi committee",
        "abcdefabcdef12xyxyz",
        "abcdefghijklmnopqrstuvwxyz",
        "abcdefghijabcdefghij",
    ]
    for text in messages:
        percent = _covered_by_adjacent_copies(text) * 100 // len(text)
        if percent:
            assert detect_repetition(text, percent), text
        if percent < 100:
            assert not detect_repetition(text, percent + 1), text
