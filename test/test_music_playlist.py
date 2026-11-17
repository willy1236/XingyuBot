"""個人歌單：repository（真實 PostgreSQL，交易結束後 rollback）與 music cog 輔助函式。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlmodel import Session, select

from starDiscord import checks, music_player
from starDiscord.cmds import music as music_cog
from starDiscord.music_player import Song, guild_playing
from starDiscord.uiElement import music_panel
from starlib import music_playlist as mp
from starlib import sqldb
from starlib.database import MusicPlaylist
from starlib.database.postgresql.client import SQLRepository
from starlib.exceptions import MusicCommandError, MusicPlaylistConflict
from starlib.identity import BotIdentity, IdentityUnavailable

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
def user_id() -> UUID:
    return uuid4()


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


def _version(repo, playlist_id: int) -> int:
    repo.session.expire_all()
    return repo.session.exec(select(MusicPlaylist.version).where(MusicPlaylist.id == playlist_id)).one()


class TestMusicPlaylistVersion:
    @pytest.fixture
    def playlist(self, repo, user_id):
        return repo.create_music_playlist(user_id, "A")

    def test_starts_at_zero(self, repo, playlist):
        assert _version(repo, playlist.id) == 0

    def test_every_write_bumps_once(self, repo, playlist):
        pid = playlist.id
        repo.add_music_playlist_songs(pid, _rows(3))
        assert _version(repo, pid) == 1
        source = repo.create_music_playlist_source(pid, "https://example.com/list", None)
        assert _version(repo, pid) == 2
        repo.add_music_playlist_songs(pid, _rows(1, "src"), source_id=source.id)
        assert _version(repo, pid) == 3
        repo.replace_music_playlist_source_songs(source, _rows(2, "src"))
        assert _version(repo, pid) == 4
        repo.remove_music_playlist_song(pid, 0)
        assert _version(repo, pid) == 5
        repo.rename_music_playlist(pid, "B")
        assert _version(repo, pid) == 6
        ids = [s.id for s in repo.get_music_playlist_songs(pid)]
        repo.reorder_music_playlist_songs(pid, ids[::-1])
        assert _version(repo, pid) == 7
        repo.remove_music_playlist_songs(pid, ids[:1])
        assert _version(repo, pid) == 8

    def test_noop_does_not_bump(self, repo, playlist):
        repo.add_music_playlist_songs(playlist.id, [])
        repo.remove_music_playlist_song(playlist.id, 3)
        repo.remove_music_playlist_songs(playlist.id, [999])
        assert _version(repo, playlist.id) == 0

    def test_import_source_is_one_bump(self, repo, playlist):
        source = repo.import_music_playlist_source(playlist.id, "https://example.com/list", "外部", _rows(3, "src"))

        assert _version(repo, playlist.id) == 1
        assert [s.source_id for s in repo.get_music_playlist_songs(playlist.id)] == [source.id] * 3

    def test_matching_version_writes_and_stale_version_is_rejected(self, repo, playlist):
        repo.add_music_playlist_songs(playlist.id, _rows(1), expected_version=0)
        assert _version(repo, playlist.id) == 1

        with pytest.raises(MusicPlaylistConflict) as exc:
            repo.add_music_playlist_songs(playlist.id, _rows(1, "late"), expected_version=0)
        assert exc.value.deleted is False
        assert repo.count_music_playlist_songs(playlist.id) == 1
        assert _version(repo, playlist.id) == 1

    @pytest.mark.parametrize(
        "write",
        [
            lambda repo, pid: repo.rename_music_playlist(pid, "B", expected_version=9),
            lambda repo, pid: repo.remove_music_playlist_song(pid, 0, expected_version=9),
            lambda repo, pid: repo.remove_music_playlist_songs(pid, [1], expected_version=9),
            lambda repo, pid: repo.reorder_music_playlist_songs(pid, [], expected_version=9),
            lambda repo, pid: repo.import_music_playlist_source(pid, "https://x/l", None, _rows(1), expected_version=9),
            lambda repo, pid: repo.delete_music_playlist(pid, expected_version=9),
        ],
    )
    def test_every_checked_write_rejects_stale_version(self, repo, playlist, write):
        repo.add_music_playlist_songs(playlist.id, _rows(2))

        with pytest.raises(MusicPlaylistConflict):
            write(repo, playlist.id)
        assert repo.count_music_playlist_songs(playlist.id) == 2
        assert repo.get_music_playlist_sources(playlist.id) == []

    def test_replace_source_rejects_stale_version(self, repo, playlist):
        source = repo.import_music_playlist_source(playlist.id, "https://example.com/list", None, _rows(2, "src"))

        with pytest.raises(MusicPlaylistConflict):
            repo.replace_music_playlist_source_songs(source, [], expected_version=0)
        assert repo.count_music_playlist_songs(playlist.id) == 2

    def test_deleted_playlist_reports_deleted(self, repo, playlist):
        repo.delete_music_playlist(playlist.id)

        with pytest.raises(MusicPlaylistConflict) as exc:
            repo.rename_music_playlist(playlist.id, "B", expected_version=0)
        assert exc.value.deleted is True


class TestMusicPlaylistEditing:
    @pytest.fixture
    def playlist(self, repo, user_id):
        playlist = repo.create_music_playlist(user_id, "A")
        repo.add_music_playlist_songs(playlist.id, _rows(4))
        return playlist

    def test_rename(self, repo, playlist, user_id):
        repo.rename_music_playlist(playlist.id, "B")

        assert repo.get_music_playlist(user_id, "B").id == playlist.id
        assert repo.get_music_playlist(user_id, "A") is None

    def test_remove_songs_compacts_positions(self, repo, playlist):
        ids = [s.id for s in repo.get_music_playlist_songs(playlist.id)]

        assert repo.remove_music_playlist_songs(playlist.id, [ids[0], ids[2], 99999]) == 2

        songs = repo.get_music_playlist_songs(playlist.id)
        assert [s.id for s in songs] == [ids[1], ids[3]]
        assert [s.position for s in songs] == [0, 1]

    def test_reorder(self, repo, playlist):
        ids = [s.id for s in repo.get_music_playlist_songs(playlist.id)]
        order = [ids[2], ids[0], ids[3], ids[1]]

        repo.reorder_music_playlist_songs(playlist.id, order)

        assert [s.id for s in repo.get_music_playlist_songs(playlist.id)] == order

    @pytest.mark.parametrize("pick", [lambda ids: ids[:-1], lambda ids: [*ids, 99999], lambda ids: [ids[0]] * len(ids)])
    def test_reorder_requires_exact_song_set(self, repo, playlist, pick):
        ids = [s.id for s in repo.get_music_playlist_songs(playlist.id)]

        with pytest.raises(ValueError):
            repo.reorder_music_playlist_songs(playlist.id, pick(ids))


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


@pytest.fixture
def mp_repo(repo, monkeypatch):
    """starlib.music_playlist 改用綁在測試交易上的 repository。"""
    monkeypatch.setattr(mp, "sqldb", repo)
    return repo


def _extracted(n: int, prefix: str = "s", **kwargs) -> mp.Extracted:
    return mp.Extracted(_rows(n, prefix), **kwargs)


class TestSaveSongs:
    def test_saves_url_title_duration(self, mp_repo, user_id):
        playlist = mp_repo.create_music_playlist(user_id, "A")

        text = mp.save_songs(playlist, [("https://example.com/a", "a", 100)])

        assert [(s.url, s.title, s.duration) for s in mp_repo.get_music_playlist_songs(playlist.id)] == [("https://example.com/a", "a", 100)]
        assert text == "已將 a 加入歌單「A」"

    def test_truncates_at_limit(self, mp_repo, user_id):
        playlist = mp_repo.create_music_playlist(user_id, "A")
        mp_repo.add_music_playlist_songs(playlist.id, _rows(mp.MAX_PLAYLIST_SONGS - 1))

        text = mp.save_songs(playlist, _rows(3, "new"))

        assert mp_repo.count_music_playlist_songs(playlist.id) == mp.MAX_PLAYLIST_SONGS
        assert "略過 2 首" in text

    def test_full_playlist_raises(self, mp_repo, user_id):
        playlist = mp_repo.create_music_playlist(user_id, "A")
        mp_repo.add_music_playlist_songs(playlist.id, _rows(mp.MAX_PLAYLIST_SONGS))

        with pytest.raises(MusicCommandError):
            mp.save_songs(playlist, _rows(1, "new"))
        assert mp_repo.count_music_playlist_songs(playlist.id) == mp.MAX_PLAYLIST_SONGS

    def test_stale_version_is_rejected(self, mp_repo, user_id):
        playlist = mp_repo.create_music_playlist(user_id, "A")
        mp_repo.add_music_playlist_songs(playlist.id, _rows(1))

        with pytest.raises(MusicPlaylistConflict):
            mp.save_songs(playlist, _rows(1, "late"), expected_version=0)
        assert mp_repo.count_music_playlist_songs(playlist.id) == 1


class TestAddExtracted:
    def test_single_songs_are_plain_songs(self, mp_repo, user_id):
        playlist = mp_repo.create_music_playlist(user_id, "A")

        text = mp.add_extracted(playlist, _extracted(2, skipped=1))

        assert text == "已將 **2** 首歌加入歌單「A」（已略過 1 首無法播放的歌曲）"
        assert mp_repo.get_music_playlist_sources(playlist.id) == []

    def test_external_playlist_creates_source_once_then_syncs(self, mp_repo, user_id):
        playlist = mp_repo.create_music_playlist(user_id, "A")
        extracted = _extracted(3, playlist_url="https://x/list", playlist_title="外部")

        first = mp.add_extracted(playlist, extracted)
        second = mp.add_extracted(playlist, _extracted(2, playlist_url="https://x/list", playlist_title="外部"))

        assert first.endswith("，之後可用 /playlist sync 同步外部歌單的更新")
        assert second == "此來源已存在，已同步：「外部」新增 0 首、移除 1 首"
        assert len(mp_repo.get_music_playlist_sources(playlist.id)) == 1
        assert mp_repo.count_music_playlist_songs(playlist.id) == 2

    def test_full_playlist_does_not_leave_empty_source(self, mp_repo, user_id):
        playlist = mp_repo.create_music_playlist(user_id, "A")
        mp_repo.add_music_playlist_songs(playlist.id, _rows(mp.MAX_PLAYLIST_SONGS))

        with pytest.raises(MusicCommandError):
            mp.add_extracted(playlist, _extracted(1, playlist_url="https://x/list"))
        assert mp_repo.get_music_playlist_sources(playlist.id) == []

    def test_stale_version_leaves_nothing_behind(self, mp_repo, user_id):
        playlist = mp_repo.create_music_playlist(user_id, "A")
        mp_repo.add_music_playlist_songs(playlist.id, _rows(1))

        with pytest.raises(MusicPlaylistConflict):
            mp.add_extracted(playlist, _extracted(3, playlist_url="https://x/list"), expected_version=0)
        assert mp_repo.get_music_playlist_sources(playlist.id) == []
        assert mp_repo.count_music_playlist_songs(playlist.id) == 1


class TestSync:
    def test_counts_old_source_songs_as_free_room(self, mp_repo, user_id):
        """同步時舊的來源歌曲會被取代，計算上限時要扣回來。"""
        playlist = mp_repo.create_music_playlist(user_id, "A")
        source = mp_repo.import_music_playlist_source(playlist.id, "https://x/list", "外部", _rows(3, "old"))
        mp_repo.add_music_playlist_songs(playlist.id, _rows(mp.MAX_PLAYLIST_SONGS - 3, "manual"))

        [text] = mp.apply_sync(playlist, [mp.SourceFetch(source, _extracted(5))])

        assert "新增 3 首" in text and "略過 2 首" in text
        assert mp_repo.count_music_playlist_songs(playlist.id) == mp.MAX_PLAYLIST_SONGS

    def test_all_sources_in_one_write_and_failures_keep_songs(self, mp_repo, user_id):
        playlist = mp_repo.create_music_playlist(user_id, "A")
        a = mp_repo.import_music_playlist_source(playlist.id, "https://x/a", "甲", _rows(2, "a"))
        b = mp_repo.import_music_playlist_source(playlist.id, "https://x/b", "乙", _rows(2, "b"))
        before = _version(mp_repo, playlist.id)

        lines = mp.apply_sync(playlist, [mp.SourceFetch(a, _extracted(3, "a")), mp.SourceFetch(b, error="私人歌單")])

        assert lines == ["「甲」新增 1 首、移除 0 首", "「乙」同步失敗，保留原本的歌曲：私人歌單"]
        assert _version(mp_repo, playlist.id) == before + 1
        assert mp_repo.count_music_playlist_songs(playlist.id) == 5

    def test_stale_version_changes_nothing(self, mp_repo, user_id):
        playlist = mp_repo.create_music_playlist(user_id, "A")
        a = mp_repo.import_music_playlist_source(playlist.id, "https://x/a", "甲", _rows(2, "a"))
        b = mp_repo.import_music_playlist_source(playlist.id, "https://x/b", "乙", _rows(2, "b"))

        with pytest.raises(MusicPlaylistConflict):
            mp.apply_sync(playlist, [mp.SourceFetch(a, _extracted(5, "a")), mp.SourceFetch(b, _extracted(5, "b"))], expected_version=0)
        assert mp_repo.count_music_playlist_songs(playlist.id) == 4

    def test_fetch_sources_records_command_errors(self):
        async def extract(url):
            if url == "https://x/bad":
                raise MusicCommandError("不受支援的連結")
            return _extracted(1)

        good, bad = SimpleNamespace(url="https://x/ok"), SimpleNamespace(url="https://x/bad")

        fetched = asyncio.run(mp.fetch_sources([good, bad], extract))

        assert [(f.source, f.error) for f in fetched] == [(good, None), (bad, "不受支援的連結")]
        assert fetched[0].extracted is not None and fetched[1].extracted is None


class TestPlaylistName:
    def test_strips(self):
        assert mp.clean_playlist_name("  我的歌  ") == "我的歌"

    @pytest.mark.parametrize("name", ["", "   ", "x" * (mp.MAX_PLAYLIST_NAME_LENGTH + 1)])
    def test_invalid(self, name):
        with pytest.raises(MusicCommandError):
            mp.clean_playlist_name(name)

    def test_create_rejects_duplicate_and_over_limit(self, mp_repo, user_id):
        mp.create_playlist(user_id, "A")

        with pytest.raises(MusicCommandError):
            mp.create_playlist(user_id, " A ")
        for i in range(mp.MAX_PLAYLISTS - 1):
            mp.create_playlist(user_id, f"p{i}")
        with pytest.raises(MusicCommandError):
            mp.create_playlist(user_id, "one more")

    def test_rename_rejects_duplicate(self, mp_repo, user_id):
        a = mp.create_playlist(user_id, "A")
        mp.create_playlist(user_id, "B")

        with pytest.raises(MusicCommandError):
            mp.rename_playlist(a, "B")
        mp.rename_playlist(a, "C")
        assert mp_repo.get_music_playlist(user_id, "C").id == a.id


# ─── 身分入口 ───────────────────────────────────────────────────────────────


def _identity(user_id: UUID | None = None) -> BotIdentity:
    return BotIdentity(user_id=user_id or uuid4(), is_formal=False, username=None, roles=(), suspended=False)


class _Responder:
    def __init__(self):
        self.messages: list[str] = []

    async def __call__(self, content=None, **kwargs):
        self.messages.append(content)


class TestIdentityEntry:
    def _autocomplete(self, value=""):
        ctx = SimpleNamespace(interaction=SimpleNamespace(user=SimpleNamespace(id=1)), value=value)
        return asyncio.run(music_cog._playlist_name_autocomplete(ctx))

    def test_autocomplete_lists_own_playlists(self, monkeypatch):
        identity = _identity()
        seen = {}

        async def fake_resolve(discord_id, *, create=True):
            seen["create"] = create
            return identity

        monkeypatch.setattr(music_cog, "resolve_identity", fake_resolve)
        monkeypatch.setattr(music_cog.sqldb, "get_music_playlists", lambda user_id: [SimpleNamespace(name="晨跑"), SimpleNamespace(name="睡前")] if user_id == identity.user_id else [])

        assert self._autocomplete("晨") == ["晨跑"]
        assert seen["create"] is False

    def test_autocomplete_new_user_is_empty(self, monkeypatch):
        async def fake_resolve(discord_id, *, create=True):
            return None

        monkeypatch.setattr(music_cog, "resolve_identity", fake_resolve)
        assert self._autocomplete() == []

    def test_autocomplete_unavailable_is_empty(self, monkeypatch):
        async def fake_resolve(discord_id, *, create=True):
            raise IdentityUnavailable

        monkeypatch.setattr(music_cog, "resolve_identity", fake_resolve)
        assert self._autocomplete() == []

    def test_with_identity_attaches_identity(self, monkeypatch):
        identity = _identity()

        async def fake_resolve(discord_id, *, create=True):
            return identity

        monkeypatch.setattr(checks, "resolve_identity", fake_resolve)

        @checks.with_identity()
        async def command(cog, ctx):
            return ctx.identity

        ctx = SimpleNamespace(author=SimpleNamespace(id=1), respond=_Responder())
        assert asyncio.run(command(None, ctx)) is identity
        assert ctx.respond.messages == []

    def test_with_identity_unavailable_stops_command(self, monkeypatch):
        async def fake_resolve(discord_id, *, create=True):
            raise IdentityUnavailable

        monkeypatch.setattr(checks, "resolve_identity", fake_resolve)
        called = []

        @checks.with_identity()
        async def command(cog, ctx):
            called.append(True)

        ctx = SimpleNamespace(author=SimpleNamespace(id=1), respond=_Responder())
        asyncio.run(command(None, ctx))
        assert called == []
        assert ctx.respond.messages == ["身分服務暫時無法連線，請稍後再試"]

    def test_panel_playlists_unavailable(self, monkeypatch):
        async def fake_resolve(discord_id, *, create=True):
            raise IdentityUnavailable

        monkeypatch.setattr(music_panel, "resolve_identity", fake_resolve)
        responder = _Responder()
        interaction = SimpleNamespace(user=SimpleNamespace(id=1), response=SimpleNamespace(send_message=responder))

        asyncio.run(music_panel.MusicPanelView._open_playlists(SimpleNamespace(), interaction))
        assert responder.messages == ["身分服務暫時無法連線，請稍後再試"]

    def test_panel_playlists_new_user_has_none(self, monkeypatch):
        async def fake_resolve(discord_id, *, create=True):
            return _identity()

        monkeypatch.setattr(music_panel, "resolve_identity", fake_resolve)
        monkeypatch.setattr(music_panel.sqldb, "get_music_playlists", lambda user_id: [])
        responder = _Responder()
        interaction = SimpleNamespace(user=SimpleNamespace(id=1), response=SimpleNamespace(send_message=responder))

        asyncio.run(music_panel.MusicPanelView._open_playlists(SimpleNamespace(), interaction))
        assert responder.messages == ["你還沒有歌單，請先用 /playlist create 建立"]
