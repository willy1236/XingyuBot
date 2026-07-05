# type: ignore
from __future__ import annotations

import asyncio

import pytest

from starDiscord.music_player import Song, format_progress_bar, format_seconds

# ─── format_seconds ───────────────────────────────────────────────────────────


class TestFormatSeconds:
    def test_none_returns_placeholder(self):
        assert format_seconds(None) == "--:--"

    def test_zero(self):
        assert format_seconds(0) == "00:00"

    def test_minutes_and_seconds(self):
        assert format_seconds(65) == "01:05"

    def test_exactly_one_hour(self):
        assert format_seconds(3600) == "1:00:00"

    def test_hours_minutes_seconds(self):
        assert format_seconds(3661) == "1:01:01"

    def test_negative_treated_as_zero(self):
        assert format_seconds(-10) == "00:00"

    def test_float_truncated(self):
        assert format_seconds(90.9) == "01:30"


# ─── format_progress_bar ─────────────────────────────────────────────────────


class TestFormatProgressBar:
    def test_none_duration_returns_dash_bar(self):
        bar, text = format_progress_bar(30, None)
        assert bar == "[----------------]"
        assert "--:--" in text
        assert "00:30" in text

    def test_zero_position(self):
        bar, text = format_progress_bar(0, 240)
        assert "▅" not in bar
        assert "00:00" in text
        assert "04:00" in text

    def test_full_position(self):
        bar, text = format_progress_bar(240, 240)
        inner = bar[1:-1]  # strip [ ]
        assert "-" not in inner
        assert inner == "▅" * 16

    def test_half_position(self):
        bar, _ = format_progress_bar(120, 240)
        assert bar.count("▅") == 8
        assert bar.count("-") == 8

    def test_custom_width(self):
        bar, _ = format_progress_bar(25, 100, width=10)
        assert bar.count("▅") == 2
        assert bar.count("-") == 8

    def test_overflow_current_clamped_to_total(self):
        bar, _ = format_progress_bar(300, 240)
        inner = bar[1:-1]
        assert "-" not in inner


# ─── Integration tests（實際網路擷取，驗證回傳資料結構） ────────────────────────
#
# 執行方式：
#   pytest test/test_music.py -m integration                      ← 使用預設網址
#   pytest test/test_music.py -m integration --url <你的網址>     ← 使用自訂網址
#
# --url 支援任何 yt-dlp 能處理的格式：
#   YouTube 單曲  https://www.youtube.com/watch?v=...
#   YouTube 歌單  https://www.youtube.com/playlist?list=...
#   Bilibili      https://www.bilibili.com/video/BV...
#   搜尋語法      ytsearch3:lofi music


_DEFAULT_SINGLE_URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
_DEFAULT_PLAYLIST_URL = "ytsearch3:lofi music study"
_DEFAULT_MIX_URL = (
    "https://www.youtube.com/watch?v=jNQXAC9IVRw"
    "&list=RDjNQXAC9IVRw&start_radio=1"
)


@pytest.mark.integration
class TestSongFromUrlIntegration:
    def test_custom_url(self, request):
        """
        使用 --url 傳入的網址擷取，驗證回傳的每首歌均有 title / source_path。

        若未傳入 --url，此測試會自動跳過。
        """
        url = request.config.getoption("--url")
        if not url:
            pytest.skip("未傳入 --url，跳過自訂網址測試")

        songs = asyncio.run(Song.from_url(url))

        assert songs, f"擷取失敗，回傳空清單（網址：{url}）"
        for song in songs:
            assert song.title, "title 不應為空"
            assert song.url, "url 不應為空"
            assert song.source_path.startswith("http"), (
                f"source_path 應為 HTTP URL，實際為：{song.source_path!r}"
            )
            assert song.duration is None or isinstance(song.duration, (int, float)), (
                f"duration 型態錯誤：{type(song.duration)}"
            )

        # 印出結果，方便人工確認
        print(f"\n擷取網址：{url}")
        print(f"共 {len(songs)} 首歌")
        for i, s in enumerate(songs, 1):
            duration_str = f"{int(s.duration)}s" if s.duration else "unknown"
            print(f"  {i}. [{duration_str}] {s.title}")
            print(f"     顯示網址：{s.url}")

    def test_default_single_video(self, request):
        """單一影片網址應回傳 1 首歌，且基本欄位均有值。"""
        url = request.config.getoption("--url") or _DEFAULT_SINGLE_URL
        songs = asyncio.run(Song.from_url(url))

        assert songs, f"擷取失敗，回傳空清單（網址：{url}）"
        song = songs[0]
        assert isinstance(song.title, str) and song.title
        assert isinstance(song.url, str) and song.url
        assert isinstance(song.source_path, str) and song.source_path.startswith("http")
        assert isinstance(song.headers, dict)
        assert song.duration is None or isinstance(song.duration, (int, float))

    def test_default_playlist(self, request):
        """歌單或搜尋語法應回傳多首歌，每首均有基本欄位。"""
        # --url 若傳入則同時作為歌單測試，否則用預設搜尋語法
        url = request.config.getoption("--url") or _DEFAULT_PLAYLIST_URL
        songs = asyncio.run(Song.from_url(url))

        assert len(songs) >= 1
        for song in songs:
            assert song.title
            assert song.source_path.startswith("http")

    def test_youtube_mix_strips_radio_params(self, request):
        """YouTube Mix (list=RD*) 應自動去除電台參數後擷取。"""
        url = request.config.getoption("--url") or _DEFAULT_MIX_URL
        songs = asyncio.run(Song.from_url(url))

        assert songs, f"擷取失敗（網址：{url}）"
        for song in songs:
            assert song.source_path.startswith("http")
