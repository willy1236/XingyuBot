# type: ignore
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import discord
import pytest
import yt_dlp

from starDiscord import music_player
from starDiscord.music_player import (
    LoopMode,
    MusicPlayer,
    Song,
    format_progress_bar,
    format_seconds,
    get_or_create_player,
    guild_playing,
)
from starDiscord.uiElement.music_panel import MusicPanelView
from starlib.exceptions import MusicPlayingError

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


# ─── MusicPlayer 狀態機（以假的 VoiceClient 驅動，不碰網路與 ffmpeg） ─────────────


class FakeVoiceClient:
    """模擬 pycord VoiceClient：stop()/disconnect() 會觸發 after 回呼。"""

    def __init__(self, members=None):
        # 預設頻道有一位真人聽眾
        self.channel = SimpleNamespace(members=list(members) if members is not None else [SimpleNamespace(bot=False)])
        self.connected = True
        self.played: list = []
        self._playing = False
        self._after = None

    def is_playing(self):
        return self._playing

    def is_paused(self):
        return False

    def play(self, source, after=None):
        if not self.connected:
            raise RuntimeError("Not connected to voice.")
        self.played.append(source)
        self._playing = True
        self._after = after

    def stop(self):
        if self._playing:
            self._playing = False
            after, self._after = self._after, None
            after(None)

    def finish(self):
        """模擬歌曲自然播完。"""
        self.stop()

    async def disconnect(self, force=False):
        self.stop()
        self.connected = False


class FakeChannel:
    def __init__(self):
        self.sent: list[str] = []

    async def send(self, content=None, **kwargs):
        embed = kwargs.get("embed")
        self.sent.append(content if content is not None else embed.title)


def _song(title: str, requester_id: int = 1) -> Song:
    requester = SimpleNamespace(id=requester_id, mention=f"<@{requester_id}>")
    return Song(f"https://example.com/{title}", None, title, requester=requester)


async def _fake_get_source(self, volume=0.5):
    if self.title.startswith("bad"):
        raise MusicPlayingError(f"無法取得串流：{self.title}")
    return SimpleNamespace(title=self.title, cleanup=lambda: None)


async def _settle(seconds: float = 0.05):
    """讓 after 排入的背景協程跑完。"""
    await asyncio.sleep(seconds)


def _make_player(vc: FakeVoiceClient | None = None, guild_id: int = 1) -> MusicPlayer:
    ctx = SimpleNamespace(channel=FakeChannel(), guild=SimpleNamespace(id=guild_id))
    player = get_or_create_player(vc or FakeVoiceClient(), ctx, asyncio.get_running_loop())
    player.after_delay = 0
    player.leave_delay = 0.05
    return player


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    monkeypatch.setattr(Song, "get_source", _fake_get_source)
    guild_playing.clear()
    yield
    guild_playing.clear()


class TestMusicPlayerLifecycle:
    def test_close_does_not_play_next_song(self):
        """/stop 時歌單還有歌：斷線觸發的 after 不應再播放或發「現在播放」。"""

        async def scenario():
            player = _make_player()
            player.add_song([_song("a"), _song("b")])
            await player.play_next()
            await player.close()
            await _settle()
            return player

        player = asyncio.run(scenario())
        assert [s.title for s in player.vc.played] == ["a"]
        assert player.channel.sent.count("現在播放") == 1
        assert "1" not in guild_playing

    def test_stale_player_replaced_when_voice_client_changes(self):
        """被踢出語音後重新連線，應建立綁定新連線的播放器。"""

        async def scenario():
            old = _make_player(FakeVoiceClient())
            old.add_song(_song("a"))
            new = _make_player(FakeVoiceClient())
            return old, new

        old, new = asyncio.run(scenario())
        assert new is not old
        assert old.closing and not old.playlist
        assert guild_playing["1"] is new

    def test_close_does_not_remove_other_player(self):
        async def scenario():
            old = _make_player()
            new = MusicPlayer(FakeVoiceClient(), SimpleNamespace(channel=FakeChannel(), guild=SimpleNamespace(id=1)), asyncio.get_running_loop())
            guild_playing["1"] = new
            await old.close()
            return new

        new = asyncio.run(scenario())
        assert guild_playing["1"] is new

    def test_new_song_during_leave_wait_cancels_leave(self):
        async def scenario():
            player = _make_player()
            player.add_song(_song("a"))
            await player.play_next()
            player.vc.finish()
            await _settle(0.01)  # 進入 wait_to_leave
            player.add_song(_song("b"))
            await player.play_next()
            await _settle(0.1)  # 超過 leave_delay
            return player

        player = asyncio.run(scenario())
        assert player.vc.connected
        assert not player.closing
        assert [s.title for s in player.vc.played] == ["a", "b"]

    def test_leave_after_queue_finished(self):
        async def scenario():
            player = _make_player()
            player.add_song(_song("a"))
            await player.play_next()
            player.vc.finish()
            await _settle(0.15)
            return player

        player = asyncio.run(scenario())
        assert player.closing
        assert not player.vc.connected
        assert "歌曲播放完畢 掰掰~" in player.channel.sent
        assert "1" not in guild_playing


class TestMusicPlayerPlayback:
    def test_unplayable_song_is_skipped(self):
        async def scenario():
            player = _make_player()
            player.add_song([_song("bad1"), _song("good")])
            await player.play_next()
            return player

        player = asyncio.run(scenario())
        assert [s.title for s in player.vc.played] == ["good"]
        assert "略過無法播放的歌曲：bad1" in player.channel.sent
        assert player.nowplaying.title == "good"

    def test_all_unplayable_songs_lead_to_leave(self):
        async def scenario():
            player = _make_player()
            player.add_song([_song("bad1"), _song("bad2")])
            await player.play_next()
            await _settle(0.15)
            return player

        player = asyncio.run(scenario())
        assert player.vc.played == []
        assert player.closing

    def test_skip_in_loop_mode_moves_to_next_song(self):
        async def scenario():
            player = _make_player()
            player.add_song([_song("a", requester_id=7), _song("b")])
            await player.play_next()
            player.loop_mode = LoopMode.SONG
            player.skip_song(SimpleNamespace(id=7, mention="<@7>"))
            await _settle()
            return player

        player = asyncio.run(scenario())
        assert [s.title for s in player.vc.played] == ["a", "b"]
        assert player.loop_mode is LoopMode.SONG

    def test_loop_turns_off_after_repeated_quick_failures(self):
        async def scenario():
            player = _make_player()
            player.add_song(_song("a"))
            player.loop_mode = LoopMode.SONG
            await player.play_next()
            for _ in range(MusicPlayer.QUICK_FAIL_LIMIT):
                player.vc.finish()
                await _settle()
            return player

        player = asyncio.run(scenario())
        assert player.loop_mode is LoopMode.OFF
        assert "歌曲連續無法正常播放，已關閉循環" in player.channel.sent
        # 首播 + 失敗上限前的重播次數
        assert len(player.vc.played) == MusicPlayer.QUICK_FAIL_LIMIT

    def test_queue_loop_requeues_finished_songs(self):
        async def scenario():
            player = _make_player()
            player.add_song([_song("a"), _song("b")])
            player.loop_mode = LoopMode.QUEUE
            await player.play_next()
            for _ in range(2):
                player.vc.finish()
                await _settle()
            return player

        player = asyncio.run(scenario())
        assert [s.title for s in player.vc.played] == ["a", "b", "a"]
        assert [s.title for s in player.playlist] == ["b"]
        assert player.loop_mode is LoopMode.QUEUE

    def test_loop_stops_when_channel_empty(self):
        async def scenario():
            player = _make_player(FakeVoiceClient([SimpleNamespace(bot=True)]))
            player.add_song([_song("a"), _song("b")])
            player.loop_mode = LoopMode.QUEUE
            await player.play_next()
            player.vc.finish()
            await _settle()
            return player

        player = asyncio.run(scenario())
        assert [s.title for s in player.vc.played] == ["a"]
        assert player.closing
        assert not player.vc.connected
        assert "語音頻道已經沒有人，停止循環播放 掰掰~" in player.channel.sent

    def test_no_loop_keeps_playing_when_channel_empty(self):
        """未開循環時歌單終究會播完，照常播下一首。"""

        async def scenario():
            player = _make_player(FakeVoiceClient([]))
            player.add_song([_song("a"), _song("b")])
            await player.play_next()
            player.vc.finish()
            await _settle()
            return player

        player = asyncio.run(scenario())
        assert [s.title for s in player.vc.played] == ["a", "b"]
        assert not player.closing

    def test_queue_loop_drops_unplayable_song(self):
        async def scenario():
            player = _make_player()
            player.add_song([_song("bad1"), _song("good")])
            player.loop_mode = LoopMode.QUEUE
            await player.play_next()
            player.vc.finish()
            await _settle()
            return player

        player = asyncio.run(scenario())
        assert [s.title for s in player.vc.played] == ["good", "good"]
        assert all(s.title != "bad1" for s in player.playlist)
        assert player.loop_mode is LoopMode.QUEUE

    def test_skip_vote_threshold_excludes_bots(self):
        async def scenario():
            members = [SimpleNamespace(bot=False), SimpleNamespace(bot=False), SimpleNamespace(bot=True)]
            player = _make_player(FakeVoiceClient(members))
            player.add_song(_song("a", requester_id=99))
            await player.play_next()
            return player.skip_song(SimpleNamespace(id=1))

        # 2 位真人 → 門檻 2//3+1 = 1，一票即跳過
        assert asyncio.run(scenario()).startswith("已達投票人數")


# ─── 音樂控制面板（Components V2） ─────────────────────────────────────────────


def _panel_items(view):
    container = view.children[0]
    return list(container.items), [item for item in view.walk_children() if isinstance(item, discord.ui.Button)]


def _panel_text(view) -> str:
    return "\n".join(item.content for item in view.walk_children() if isinstance(item, discord.ui.TextDisplay))


class TestMusicPanel:
    def test_section_with_thumbnail(self):
        async def scenario():
            player = _make_player()
            song = _song("a")
            song.thumbnail = "https://img/a"
            player.add_song([song, _song("b")])
            await player.play_next()
            return MusicPanelView(1)

        items, buttons = _panel_items(asyncio.run(scenario()))
        assert isinstance(items[0], discord.ui.Section)
        assert [b.label for b in buttons] == ["暫停", "跳過", "停止", "重新整理", "循環：關閉", "洗牌", "待播清單", "點歌", "我的歌單"]
        assert not any(b.disabled for b in buttons)

    def test_text_without_thumbnail_and_queue_preview(self):
        async def scenario():
            player = _make_player()
            player.add_song([_song(t) for t in "abcdef"])
            await player.play_next()
            player.loop_mode = LoopMode.QUEUE
            return MusicPanelView(1)

        view = asyncio.run(scenario())
        items, buttons = _panel_items(view)
        assert isinstance(items[0], discord.ui.TextDisplay)
        text = _panel_text(view)
        assert "1. b" in text and "3. d" in text and "4. e" not in text
        assert "共 5 首待播" in text
        assert "循環：整張" in [b.label for b in buttons]

    def test_no_player_shows_idle_panel(self):
        async def scenario():
            return MusicPanelView(1)

        view = asyncio.run(scenario())
        _, buttons = _panel_items(view)
        assert [b.label for b in buttons] == ["點歌", "我的歌單", "重新整理"]
        assert "目前沒有播放中的歌曲" in _panel_text(view)

    def test_closed_player_shows_idle_panel(self):
        async def scenario():
            player = _make_player()
            player.add_song(_song("a"))
            await player.play_next()
            view = MusicPanelView(1)
            await player.close()
            view.rebuild()
            return view

        _, buttons = _panel_items(asyncio.run(scenario()))
        assert [b.label for b in buttons] == ["點歌", "我的歌單", "重新整理"]

    def test_disable_all_items_reaches_nested_buttons(self):
        async def scenario():
            player = _make_player()
            player.add_song(_song("a"))
            await player.play_next()
            return MusicPanelView(1).disable_all_items()

        _, buttons = _panel_items(asyncio.run(scenario()))
        assert buttons and all(b.disabled for b in buttons)


# ─── Song.from_url 解析（mock 掉 yt-dlp 擷取） ───────────────────────────────────


class TestSongFromUrlParsing:
    def test_playlist_skips_broken_entries(self, monkeypatch):
        playlist = {
            "entries": [
                None,
                {"_type": "url", "url": "https://www.youtube.com/watch?v=aaa", "title": "A", "duration": 100},
                {"_type": "url", "url": "https://www.youtube.com/watch?v=bbb", "title": "[Private video]"},
                {"webpage_url": "https://www.youtube.com/watch?v=ccc", "title": "C", "url": "https://stream/ccc"},
            ]
        }

        async def fake_extract(url, opts):
            assert opts["extract_flat"] == "in_playlist"
            assert opts["ignoreerrors"] is True
            return playlist

        monkeypatch.setattr(music_player, "_extract", fake_extract)
        songs, skipped = asyncio.run(Song.from_url("https://www.youtube.com/playlist?list=PL1"))

        assert [s.title for s in songs] == ["A", "C"]
        assert skipped == 2
        assert songs[0].source_path is None
        assert songs[0].url == "https://www.youtube.com/watch?v=aaa"
        assert songs[1].source_path == "https://stream/ccc"

    def test_thumbnail_from_entry(self, monkeypatch):
        playlist = {
            "entries": [
                {"_type": "url", "url": "https://www.youtube.com/watch?v=aaa", "title": "A", "thumbnails": [{"url": "https://img/a-low"}, {"url": "https://img/a-high"}]},
                {"webpage_url": "https://www.youtube.com/watch?v=bbb", "title": "B", "url": "https://stream/bbb", "thumbnail": "https://img/b"},
                {"_type": "url", "url": "https://www.youtube.com/watch?v=ccc", "title": "C"},
            ]
        }

        async def fake_extract(url, opts):
            return playlist

        monkeypatch.setattr(music_player, "_extract", fake_extract)
        songs, _ = asyncio.run(Song.from_url("https://www.youtube.com/playlist?list=PL1"))

        assert [s.thumbnail for s in songs] == ["https://img/a-high", "https://img/b", None]

    def test_single_failure_raises_download_error(self, monkeypatch):
        calls = []

        async def fake_extract(url, opts):
            calls.append(opts["ignoreerrors"])
            if opts["ignoreerrors"]:
                return None
            raise yt_dlp.utils.DownloadError("ERROR: Video unavailable")

        monkeypatch.setattr(music_player, "_extract", fake_extract)
        with pytest.raises(yt_dlp.utils.DownloadError):
            asyncio.run(Song.from_url("https://www.youtube.com/watch?v=zzz"))
        assert calls == [True, False]

    def test_fresh_stream_fills_missing_title_and_duration(self, monkeypatch):
        url = "https://www.bilibili.com/video/BV1xx"

        async def fake_extract(u, opts):
            return {"title": "真標題", "duration": 180, "url": "https://stream/x"}

        monkeypatch.setattr(music_player, "_extract", fake_extract)
        song = Song(url, None, url)
        asyncio.run(song._fetch_fresh_stream())

        assert song.title == "真標題"
        assert song.duration == 180

    def test_fresh_stream_keeps_existing_title_and_duration(self, monkeypatch):
        url = "https://www.bilibili.com/video/BV1xx"

        async def fake_extract(u, opts):
            return {"title": "新標題", "duration": 180, "url": "https://stream/x"}

        monkeypatch.setattr(music_player, "_extract", fake_extract)
        song = Song(url, None, "原標題", duration=100)
        asyncio.run(song._fetch_fresh_stream())

        assert song.title == "原標題"
        assert song.duration == 100


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
        使用 --url 傳入的網址擷取，驗證回傳的每首歌均有 title / url。
        歌單為 flat 擷取，source_path 可能為 None（播放時才取串流）。

        若未傳入 --url，此測試會自動跳過。
        """
        url = request.config.getoption("--url")
        if not url:
            pytest.skip("未傳入 --url，跳過自訂網址測試")

        songs, skipped = asyncio.run(Song.from_url(url))

        assert songs, f"擷取失敗，回傳空清單（網址：{url}）"
        for song in songs:
            assert song.title, "title 不應為空"
            assert song.url.startswith("http"), f"url 應為 HTTP URL，實際為：{song.url!r}"
            assert song.duration is None or isinstance(song.duration, (int, float)), (
                f"duration 型態錯誤：{type(song.duration)}"
            )

        # 印出結果，方便人工確認
        print(f"\n擷取網址：{url}")
        print(f"共 {len(songs)} 首歌，略過 {skipped} 首")
        for i, s in enumerate(songs, 1):
            duration_str = f"{int(s.duration)}s" if s.duration else "unknown"
            print(f"  {i}. [{duration_str}] {s.title}")
            print(f"     顯示網址：{s.url}")

    def test_default_single_video(self, request):
        """單一影片網址應回傳 1 首歌，且基本欄位均有值。"""
        url = request.config.getoption("--url") or _DEFAULT_SINGLE_URL
        songs, _ = asyncio.run(Song.from_url(url))

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
        songs, _ = asyncio.run(Song.from_url(url))

        assert len(songs) >= 1
        for song in songs:
            assert song.title
            assert song.url.startswith("http")

    def test_playlist_entry_stream_resolved_on_play(self, request):
        """flat 項目沒有 source_path，播放前應能由 _fetch_fresh_stream 取得串流。"""
        url = request.config.getoption("--url") or _DEFAULT_PLAYLIST_URL
        songs, _ = asyncio.run(Song.from_url(url))

        source_path, _ = asyncio.run(songs[0]._fetch_fresh_stream())
        assert source_path and source_path.startswith("http")

    def test_youtube_mix_strips_radio_params(self, request):
        """YouTube Mix (list=RD*) 應自動去除電台參數後擷取。"""
        url = request.config.getoption("--url") or _DEFAULT_MIX_URL
        songs, _ = asyncio.run(Song.from_url(url))

        assert songs, f"擷取失敗（網址：{url}）"
        for song in songs:
            assert song.url.startswith("http")
