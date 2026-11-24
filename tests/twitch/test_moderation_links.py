"""白名單依 URL 的實際網域判斷。"""

from starlib.twitch_moderation import detect_link


def test_允許的網域出現在帳號欄位時仍會攔截未允許的網域():
    assert detect_link("https://youtube.com@example.org/video", ["youtube.com"])
