"""C-02 連結過濾的白名單與裸網域判定。"""

from importlib import import_module
from importlib.util import find_spec

import pytest


@pytest.mark.parametrize(
    ("text", "whitelist", "violates"),
    [
        pytest.param("看 https://m.youtube.com/watch", ["youtube.com"], False, id="allowed-subdomain"),
        pytest.param("看 https://www.twitter.com/abc/status/1", ["twitter.com/abc"], False, id="allowed-path"),
        pytest.param("看 twitter.com/abcdef", ["twitter.com/abc"], True, id="different-path-segment"),
        pytest.param("看 abc.com", [], True, id="bare-domain"),
        pytest.param("看 youtube.com 和 abc.com", ["youtube.com"], True, id="one-unlisted-link"),
        pytest.param("今天沒有分享連結", [], False, id="plain-text"),
    ],
)
def test_連結過濾只判定不在白名單的連結(text, whitelist, violates):
    module = "starlib.twitch_moderation"
    assert find_spec(module) is not None, "C-02 尚未提供連結判定介面"
    detect_link = import_module(module).detect_link
    assert detect_link(text, whitelist) is violates
