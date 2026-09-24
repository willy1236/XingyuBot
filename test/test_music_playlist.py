"""個人歌單：repository（真實 PostgreSQL，交易結束後 rollback）與 music cog 輔助函式。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from sqlmodel import Session

from starDiscord import music_player
from starDiscord.cmds import music as music_cog
from starDiscord.music_player import ExtractResult, Song, guild_playing
from starlib import sqldb
from starlib.database import CloudUser
from starlib.database.postgresql.client import SQLRepository
from starlib.exceptions import MusicCommandError

# ─── Repository ─────────────────────────────────────────────────────────────


@pytest.fixture
def repo():
    """綁在外層交易上的 repository，repository 內的 commit 只會提交 savepoint，測試結束整個 rollback。"""
    connection = sqldb.engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    repository = SQLRepository(sqldb.engine, session)
    try:
        yield repository
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def user_id(repo: SQLRepository) -> int:
    user = CloudUser(name="playlist-test")
    repo.add(user)
    return user.id


def _rows(n: int, prefix: str = "song") -> list[tuple[str, str, int | None]]:
    return [(f"https://example.com/{prefix}{i}", f"{prefix}{i}", 60 + i) for i in range(n)]


class TestMusicPlaylistRepository:
    def test_create_and_list(self, repo, user_id):
        a = repo.create_music_playlist(user_id, "A")
        b = repo.create_music_playlist(user_id, "B")

        assert [p.name for p in repo.get_music_playlists(user_id)] == ["A", "B"]
        assert repo.get_music_playlist(user_id, "B").id == b.id
        assert repo.get_music_playlist(user_id, "C") is None
        assert a.id != b.id

    def test_add_songs_appends_in_order(self, repo, user_id):
        playlist = repo.create_music_playlist(user_id, "A")
        repo.add_music_playlist_songs(playlist.id, _rows(2, "x"))
        repo.add_music_playlist_songs(playlist.id, _rows(2, "y"))

        songs = repo.get_music_playlist_songs(playlist.id)
        assert [s.title for s in songs] == ["x0", "x1", "y0", "y1"]
        assert [s.position for s in songs] == [0, 1, 2, 3]
        assert repo.count_music_playlist_songs(playlist.id) == 4
        assert repo.get_music_playlist_song_counts(user_id) == {playlist.id: 4}

    def test_remove_song_renumbers(self, repo, user_id):
        playlist = repo.create_music_playlist(user_id, "A")
        repo.add_music_playlist_songs(playlist.id, _rows(3))

        removed = repo.remove_music_playlist_song(playlist.id, 1)

        assert removed.title == "song1"
        songs = repo.get_music_playlist_songs(playlist.id)
        assert [s.title for s in songs] == ["song0", "song2"]
        assert [s.position for s in songs] == [0, 1]

    def test_remove_out_of_range(self, repo, user_id):
        playlist = repo.create_music_playlist(user_id, "A")
        repo.add_music_playlist_songs(playlist.id, _rows(1))

        assert repo.remove_music_playlist_song(playlist.id, 5) is None
        assert repo.count_music_playlist_songs(playlist.id) == 1

    def test_delete_playlist_removes_songs(self, repo, user_id):
        playlist = repo.create_music_playlist(user_id, "A")
        repo.add_music_playlist_songs(playlist.id, _rows(2))

        repo.delete_music_playlist(playlist.id)

        assert repo.get_music_playlists(user_id) == []
        assert repo.get_music_playlist_songs(playlist.id) == []


class TestMusicPlaylistSource:
    @pytest.fixture
    def playlist(self, repo, user_id):
        return repo.create_music_playlist(user_id, "A")

    def _titles(self, repo, playlist):
        songs = repo.get_music_playlist_songs(playlist.id)
        assert [s.position for s in songs] == list(range(len(songs)))
        return [s.title for s in songs]

    def test_replace_keeps_manual_songs_in_place(self, repo, playlist):
        repo.add_music_playlist_songs(playlist.id, _rows(1, "manual_a"))
        source = repo.create_music_playlist_source(playlist.id, "https://example.com/list", "外部")
        repo.add_music_playlist_songs(playlist.id, _rows(3, "src"), source_id=source.id)
        repo.add_music_playlist_songs(playlist.id, _rows(1, "manual_b"))

        # 外部歌單刪掉 src0、加入 new0
        added, removed = repo.replace_music_playlist_source_songs(source, [*_rows(3, "src")[1:], *_rows(1, "new")], "外部改名")

        assert (added, removed) == (1, 1)
        assert self._titles(repo, playlist) == ["manual_a0", "src1", "src2", "new0", "manual_b0"]
        assert repo.get_music_playlist_source(playlist.id, "https://example.com/list").title == "外部改名"

    def test_replace_appends_when_source_songs_all_removed(self, repo, playlist):
        source = repo.create_music_playlist_source(playlist.id, "https://example.com/list", None)
        repo.add_music_playlist_songs(playlist.id, _rows(1, "src"), source_id=source.id)
        repo.add_music_playlist_songs(playlist.id, _rows(1, "manual"))
        repo.remove_music_playlist_song(playlist.id, 0)

        added, removed = repo.replace_music_playlist_source_songs(source, _rows(2, "src"))

        assert (added, removed) == (2, 0)
        assert self._titles(repo, playlist) == ["manual0", "src0", "src1"]

    def test_replace_only_touches_own_source(self, repo, playlist):
        a = repo.create_music_playlist_source(playlist.id, "https://example.com/a", None)
        b = repo.create_music_playlist_source(playlist.id, "https://example.com/b", None)
        repo.add_music_playlist_songs(playlist.id, _rows(2, "a"), source_id=a.id)
        repo.add_music_playlist_songs(playlist.id, _rows(2, "b"), source_id=b.id)

        repo.replace_music_playlist_source_songs(a, [])

        assert self._titles(repo, playlist) == ["b0", "b1"]
        assert [s.url for s in repo.get_music_playlist_sources(playlist.id)] == ["https://example.com/a", "https://example.com/b"]

    def test_replace_reuses_rows_for_existing_songs(self, repo, playlist):
        """沒變的歌沿用原本的資料列，同步不消耗新 id。"""
        source = repo.create_music_playlist_source(playlist.id, "https://example.com/list", None)
        repo.add_music_playlist_songs(playlist.id, _rows(3, "src"), source_id=source.id)
        before = {s.url: s.id for s in repo.get_music_playlist_songs(playlist.id)}

        # 順序反轉、標題更新，但歌都一樣
        rows = [(url, f"{title}-new", duration) for url, title, duration in reversed(_rows(3, "src"))]
        added, removed = repo.replace_music_playlist_source_songs(source, rows)

        songs = repo.get_music_playlist_songs(playlist.id)
        assert (added, removed) == (0, 0)
        assert {s.url: s.id for s in songs} == before
        assert [s.title for s in songs] == ["src2-new", "src1-new", "src0-new"]

    def test_replace_matches_duplicate_urls_one_to_one(self, repo, playlist):
        source = repo.create_music_playlist_source(playlist.id, "https://example.com/list", None)
        dup = ("https://example.com/dup", "dup", 60)
        repo.add_music_playlist_songs(playlist.id, [dup, dup], source_id=source.id)

        added, removed = repo.replace_music_playlist_source_songs(source, [dup, dup, dup])
        assert (added, removed) == (1, 0)

        added, removed = repo.replace_music_playlist_source_songs(source, [dup])
        assert (added, removed) == (0, 2)
        assert self._titles(repo, playlist) == ["dup"]

    def test_delete_playlist_removes_sources(self, repo, playlist):
        repo.create_music_playlist_source(playlist.id, "https://example.com/list", None)

        repo.delete_music_playlist(playlist.id)

        assert repo.get_music_playlist_sources(playlist.id) == []


# ─── Song.extract ────────────────────────────────────────────────────────────


class TestSongExtract:
    def _run(self, monkeypatch, info):
        async def fake_extract(url, opts):
            return info

        monkeypatch.setattr(music_player, "_extract", fake_extract)
        return asyncio.run(Song.extract("https://www.youtube.com/playlist?list=PLx"))

    def test_playlist_carries_url_and_title(self, monkeypatch):
        info = {
            "_type": "playlist",
            "title": "我的歌單",
            "webpage_url": "https://www.youtube.com/playlist?list=PLx",
            "entries": [{"_type": "url", "url": "https://www.youtube.com/watch?v=a", "title": "a"}],
        }
        result = self._run(monkeypatch, info)

        assert result.playlist_url == "https://www.youtube.com/playlist?list=PLx"
        assert result.playlist_title == "我的歌單"
        assert [s.title for s in result.songs] == ["a"]

    def test_single_video_has_no_playlist(self, monkeypatch):
        info = {"title": "a", "webpage_url": "https://www.youtube.com/watch?v=a", "url": "https://stream/a"}
        result = self._run(monkeypatch, info)

        assert result.playlist_url is None
        assert result.playlist_title is None
        assert len(result.songs) == 1

    def test_from_url_signature_unchanged(self, monkeypatch):
        async def fake_extract(url, opts):
            return {"_type": "playlist", "entries": [None, {"_type": "url", "url": "https://x/b", "title": "b"}]}

        monkeypatch.setattr(music_player, "_extract", fake_extract)
        songs, skipped = asyncio.run(Song.from_url("https://x/list"))

        assert [s.title for s in songs] == ["b"]
        assert skipped == 1


# ─── Cog 輔助函式 ────────────────────────────────────────────────────────────


class FakeVoiceClient:
    def __init__(self):
        self.channel = SimpleNamespace(members=[SimpleNamespace(bot=False)])
        self.played: list = []
        self.connected = True

    def is_connected(self):
        return self.connected

    def is_playing(self):
        return bool(self.played)

    def is_paused(self):
        return False

    def is_recording(self):
        return False

    def play(self, source, after=None):
        self.played.append(source)


def _song(title: str) -> Song:
    return Song(f"https://example.com/{title}", None, title, requester=SimpleNamespace(id=1, mention="<@1>"), duration=100)


async def _fake_get_source(self, volume=0.5):
    return SimpleNamespace(title=self.title, cleanup=lambda: None)


@pytest.fixture
def fake_playback(monkeypatch):
    monkeypatch.setattr(Song, "get_source", _fake_get_source)
    guild_playing.clear()
    yield
    guild_playing.clear()


class TestEnqueueAndPlay:
    def _run(self, songs, skipped=0):
        async def scenario():
            vc = FakeVoiceClient()
            ctx = SimpleNamespace(channel=SimpleNamespace(send=_noop_send), guild=SimpleNamespace(id=1))
            text = await music_player.enqueue_and_play(vc, ctx, asyncio.get_running_loop(), songs, skipped)
            return vc, text

        return asyncio.run(scenario())

    def test_single_song(self, fake_playback):
        vc, text = self._run([_song("a")])
        assert text == "加入歌單: a"
        assert [s.title for s in vc.played] == ["a"]

    def test_many_songs_with_skipped(self, fake_playback):
        vc, text = self._run([_song("a"), _song("b")], skipped=3)
        assert text == "**2** 首歌已加入歌單（已略過 3 首無法播放的歌曲）"
        assert [s.title for s in vc.played] == ["a"]

    def test_disconnected_voice_discards_player(self, fake_playback):
        async def scenario():
            vc = FakeVoiceClient()
            vc.connected = False
            ctx = SimpleNamespace(channel=SimpleNamespace(send=_noop_send), guild=SimpleNamespace(id=1))
            await music_player.enqueue_and_play(vc, ctx, asyncio.get_running_loop(), [_song("a")], 0)
            return vc

        vc = asyncio.run(scenario())
        assert vc.played == []
        assert "1" not in guild_playing


async def _noop_send(content=None, **kwargs):
    return None


class TestSaveSongs:
    @pytest.fixture
    def saved(self, monkeypatch):
        saved: list = []
        monkeypatch.setattr(music_cog.sqldb, "add_music_playlist_songs", lambda playlist_id, rows, source_id=None: saved.extend(rows))
        return saved

    def test_saves_url_title_duration(self, monkeypatch, saved):
        monkeypatch.setattr(music_cog.sqldb, "count_music_playlist_songs", lambda playlist_id: 0)
        playlist = SimpleNamespace(id=1, name="A")

        text = music_cog._save_songs(playlist, [_song("a")])

        assert saved == [("https://example.com/a", "a", 100)]
        assert text == "已將 a 加入歌單「A」"

    def test_truncates_at_limit(self, monkeypatch, saved):
        monkeypatch.setattr(music_cog.sqldb, "count_music_playlist_songs", lambda playlist_id: music_cog.MAX_PLAYLIST_SONGS - 1)
        playlist = SimpleNamespace(id=1, name="A")

        text = music_cog._save_songs(playlist, [_song("a"), _song("b"), _song("c")])

        assert [row[1] for row in saved] == ["a"]
        assert "略過 2 首" in text

    def test_full_playlist_raises(self, monkeypatch, saved):
        monkeypatch.setattr(music_cog.sqldb, "count_music_playlist_songs", lambda playlist_id: music_cog.MAX_PLAYLIST_SONGS)

        with pytest.raises(MusicCommandError):
            music_cog._save_songs(SimpleNamespace(id=1, name="A"), [_song("a")])
        assert saved == []


class TestReplaceSourceSongs:
    def test_counts_old_source_songs_as_free_room(self, monkeypatch):
        """同步時舊的來源歌曲會被取代，計算上限時要扣回來。"""
        source = SimpleNamespace(id=7, title="外部", url="https://x/list")
        existing = [SimpleNamespace(source_id=7)] * 3 + [SimpleNamespace(source_id=None)] * (music_cog.MAX_PLAYLIST_SONGS - 3)
        captured = {}

        def fake_replace(src, rows, title):
            captured["rows"] = rows
            return len(rows), 0

        monkeypatch.setattr(music_cog.sqldb, "get_music_playlist_songs", lambda playlist_id: existing)
        monkeypatch.setattr(music_cog.sqldb, "replace_music_playlist_source_songs", fake_replace)

        result = ExtractResult([_song(f"s{i}") for i in range(5)], 0, source.url, "外部")
        text = music_cog._replace_source_songs(SimpleNamespace(id=1, name="A"), source, result)

        assert [row[1] for row in captured["rows"]] == ["s0", "s1", "s2"]
        assert "略過 2 首" in text


class TestPlaylistName:
    def test_strips(self):
        assert music_cog._clean_playlist_name("  我的歌  ") == "我的歌"

    @pytest.mark.parametrize("name", ["", "   ", "x" * (music_cog.MAX_PLAYLIST_NAME_LENGTH + 1)])
    def test_invalid(self, name):
        with pytest.raises(MusicCommandError):
            music_cog._clean_playlist_name(name)
