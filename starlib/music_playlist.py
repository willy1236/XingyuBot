"""個人歌單的加歌、匯入外部歌單與同步流程，Discord 指令與網頁共用。

只處理已擷取的資料，不 import starDiscord；擷取（yt-dlp）由呼叫端做，用 `Extracted.of` 轉成這裡的型別。
全部是同步的資料庫操作，網頁端要放進 `run_db`。傳入 `expected_version` 時，版本不符拋 `MusicPlaylistConflict`，
版本檢查與寫入在同一個交易裡完成。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from starlib.database import MAX_PLAYLIST_NAME_LENGTH, MusicPlaylist, MusicPlaylistSource, sqldb
from starlib.exceptions import MusicCommandError

# 個人歌單上限：歌單數配合下拉選單最多 25 個選項
MAX_PLAYLISTS = 25
MAX_PLAYLIST_SONGS = 500

type SongRow = tuple[str, str, int | None]


@dataclass(frozen=True)
class Extracted:
    """擷取外部網址的結果；playlist_url 不為 None 表示網址是一份外部歌單。"""

    songs: list[SongRow]
    skipped: int = 0
    playlist_url: str | None = None
    playlist_title: str | None = None

    @classmethod
    def of(cls, result) -> Extracted:
        """從有 songs（含 url、title、duration）、skipped、playlist_url、playlist_title 的擷取結果轉換。"""
        rows = [(song.url, song.title, song.duration) for song in result.songs]
        return cls(rows, result.skipped, result.playlist_url, result.playlist_title)


@dataclass(frozen=True)
class SourceFetch:
    """同步時重新擷取某個來源的結果；失敗時 extracted 為 None 並帶 error。"""

    source: MusicPlaylistSource
    extracted: Extracted | None = None
    error: str | None = None


def clean_playlist_name(name: str) -> str:
    name = name.strip()
    if not name:
        raise MusicCommandError("歌單名稱不可為空")
    if len(name) > MAX_PLAYLIST_NAME_LENGTH:
        raise MusicCommandError(f"歌單名稱最多 {MAX_PLAYLIST_NAME_LENGTH} 個字")
    return name


def get_or_create_playlist(user_id: UUID, name: str) -> MusicPlaylist:
    name = clean_playlist_name(name)
    playlist = sqldb.get_music_playlist(user_id, name)
    if playlist:
        return playlist
    if len(sqldb.get_music_playlists(user_id)) >= MAX_PLAYLISTS:
        raise MusicCommandError(f"歌單數量已達上限 {MAX_PLAYLISTS} 個")
    return sqldb.create_music_playlist(user_id, name)


def create_playlist(user_id: UUID, name: str) -> MusicPlaylist:
    """建立新歌單；同名已存在時拋錯。"""
    name = clean_playlist_name(name)
    if sqldb.get_music_playlist(user_id, name):
        raise MusicCommandError(f"已經有名為「{name}」的歌單")
    return get_or_create_playlist(user_id, name)


def rename_playlist(playlist: MusicPlaylist, name: str, expected_version: int | None = None) -> None:
    name = clean_playlist_name(name)
    if name == playlist.name:
        return
    if sqldb.get_music_playlist(playlist.user_id, name):
        raise MusicCommandError(f"已經有名為「{name}」的歌單")
    sqldb.rename_music_playlist(playlist.id, name, expected_version)


def playlist_room(playlist: MusicPlaylist) -> int:
    room = MAX_PLAYLIST_SONGS - sqldb.count_music_playlist_songs(playlist.id)
    if room <= 0:
        raise MusicCommandError(f"歌單「{playlist.name}」已達上限 {MAX_PLAYLIST_SONGS} 首")
    return room


def source_name(source: MusicPlaylistSource) -> str:
    return source.title or source.url


def _overflow_text(dropped: int) -> str:
    return f"（歌單已滿 {MAX_PLAYLIST_SONGS} 首，略過 {dropped} 首）" if dropped else ""


def _saved_text(playlist: MusicPlaylist, saved: list[SongRow], dropped: int) -> str:
    text = f"已將 {saved[0][1]} 加入歌單「{playlist.name}」" if len(saved) == 1 else f"已將 **{len(saved)}** 首歌加入歌單「{playlist.name}」"
    return text + _overflow_text(dropped)


def save_songs(playlist: MusicPlaylist, songs: list[SongRow], expected_version: int | None = None) -> str:
    """把歌曲存進歌單（超過上限的部分捨棄），回傳給使用者的訊息。"""
    to_save = songs[: playlist_room(playlist)]
    sqldb.add_music_playlist_songs(playlist.id, to_save, expected_version=expected_version)
    return _saved_text(playlist, to_save, len(songs) - len(to_save))


def _sync_text(source: MusicPlaylistSource, result: tuple[int, int, int]) -> str:
    added, removed, dropped = result
    return f"「{source_name(source)}」新增 {added} 首、移除 {removed} 首" + _overflow_text(dropped)


def _sync(playlist: MusicPlaylist, updates: list[tuple[MusicPlaylistSource, Extracted]], expected_version: int | None) -> list[tuple[int, int, int]]:
    return sqldb.sync_music_playlist_sources(
        playlist.id, [(source, extracted.songs, extracted.playlist_title) for source, extracted in updates], MAX_PLAYLIST_SONGS, expected_version
    )


def add_extracted(playlist: MusicPlaylist, extracted: Extracted, expected_version: int | None = None) -> str:
    """把擷取到的單曲或外部歌單加進歌單，回傳給使用者的訊息。同一個外部歌單再加一次時改為同步，避免重複加入。"""
    if not extracted.playlist_url:
        text = save_songs(playlist, extracted.songs, expected_version)
    elif source := sqldb.get_music_playlist_source(playlist.id, extracted.playlist_url):
        result = _sync(playlist, [(source, extracted)], expected_version)[0]
        text = "此來源已存在，已同步：" + _sync_text(source, result)
    else:
        to_save = extracted.songs[: playlist_room(playlist)]  # 歌單已滿時先擋下，不留下沒有歌曲的來源
        sqldb.import_music_playlist_source(playlist.id, extracted.playlist_url, extracted.playlist_title, to_save, expected_version)
        text = _saved_text(playlist, to_save, len(extracted.songs) - len(to_save)) + "，之後可用 /playlist sync 同步外部歌單的更新"

    if extracted.skipped:
        text += f"（已略過 {extracted.skipped} 首無法播放的歌曲）"
    return text


async def fetch_sources(sources: list[MusicPlaylistSource], extract: Callable[[str], Awaitable[Extracted]]) -> list[SourceFetch]:
    """重新擷取每個來源；外部歌單被刪除或改為私人時只記錄錯誤，保留舊的歌曲。"""
    fetched = []
    for source in sources:
        try:
            fetched.append(SourceFetch(source, await extract(source.url)))
        except MusicCommandError as e:
            fetched.append(SourceFetch(source, error=e.message))
    return fetched


def apply_sync(playlist: MusicPlaylist, fetched: list[SourceFetch], expected_version: int | None = None) -> list[str]:
    """把重新擷取的結果一次寫進歌單，回傳每個來源的結果訊息（依來源順序）。"""
    ok = [(item.source, item.extracted) for item in fetched if item.extracted is not None]
    results = iter(_sync(playlist, ok, expected_version))
    lines = []
    for item in fetched:
        if item.extracted is None:
            lines.append(f"「{source_name(item.source)}」同步失敗，保留原本的歌曲：{item.error}")
        else:
            lines.append(_sync_text(item.source, next(results)))
    return lines
