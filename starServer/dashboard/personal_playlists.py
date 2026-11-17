"""個人區的歌單管理（T-07）。

GET    /dashboard/personal/playlists                       歌單清單（名稱、版本、歌曲數）與上限
GET    /dashboard/personal/playlists/{id}                  整份歌單：歌曲、來源、version
POST   /dashboard/personal/playlists                       建立 {name}
PATCH  /dashboard/personal/playlists/{id}                  改名 {name, version}
DELETE /dashboard/personal/playlists/{id}?version=         刪除
POST   /dashboard/personal/playlists/{id}/songs            加入歌曲或外部歌單網址 {url, version}
POST   /dashboard/personal/playlists/{id}/songs/remove     批次刪除 {song_ids, version}
PUT    /dashboard/personal/playlists/{id}/songs/order      重排 {song_ids, version}，必須是全部歌曲
POST   /dashboard/personal/playlists/{id}/sync             同步匯入過的外部歌單 {version}

讀寫都以 `personal_scope().tool_user_id` 為準，別人的歌單一律 404。寫入要有析域帳號（403 domalyze_required）。
每個寫入帶打開歌單時的 `version`，與目前不符回 409：`{"error": "conflict", "deleted": bool, "current": 整份歌單 | null}`，
版本檢查與寫入在同一個交易裡（starlib/music_playlist.py）。成功回整份最新歌單。
"""

from types import SimpleNamespace

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from starDiscord.music_player import extract_songs
from starlib import music_playlist as playlists
from starlib import sqldb
from starlib.database import MAX_PLAYLIST_NAME_LENGTH
from starlib.exceptions import MusicCommandError, MusicPlaylistConflict

from .db import run_db
from .errors import DashboardError
from .personal import PersonalScope, require_personal

router = APIRouter(prefix="/dashboard")

_MAX_URL_LENGTH = 2000


def _playlist_json(playlist_id: int) -> dict | None:
    playlist = sqldb.get_music_playlist_by_id(playlist_id)
    if playlist is None:
        return None
    return {
        "id": playlist.id,
        "name": playlist.name,
        "version": playlist.version,
        "songs": [
            {"id": s.id, "url": s.url, "title": s.title, "duration": s.duration, "source_id": s.source_id}
            for s in sqldb.get_music_playlist_songs(playlist.id)
        ],
        "sources": [
            {"id": s.id, "url": s.url, "title": s.title, "synced_at": s.synced_at.isoformat()}
            for s in sqldb.get_music_playlist_sources(playlist.id)
        ],
    }


def _owned(scope: PersonalScope, playlist_id: int):
    """自己的歌單；不存在或不是自己的一律 404，不洩漏別人的歌單存在。"""
    playlist = sqldb.get_music_playlist_by_id(playlist_id)
    if playlist is None or scope.tool_user_id is None or playlist.user_id != scope.tool_user_id:
        raise DashboardError(404, "not_found")
    return playlist


def _invalid(e: MusicCommandError) -> DashboardError:
    return DashboardError(400, "invalid_playlist", message=e.message)


def _write(scope: PersonalScope, playlist_id: int, action):
    """在 DB thread 內執行寫入：驗證擁有者，轉換版本衝突與輸入錯誤，成功回整份最新歌單。"""

    def run():
        playlist = _owned(scope, playlist_id)
        try:
            extra = action(playlist)
        except MusicPlaylistConflict as e:
            raise DashboardError(409, "conflict", deleted=e.deleted, current=None if e.deleted else _playlist_json(playlist_id)) from e
        except MusicCommandError as e:
            raise _invalid(e) from e
        return {**(extra or {}), "playlist": _playlist_json(playlist_id)}

    return run_db(run)


# ====== 讀取 ======
@router.get("/personal/playlists")
async def list_playlists(scope: PersonalScope = Depends(require_personal())):
    def run():
        user_id = scope.tool_user_id
        if user_id is None:
            return []
        counts = sqldb.get_music_playlist_song_counts(user_id)
        return [{"id": p.id, "name": p.name, "version": p.version, "song_count": counts.get(p.id, 0)} for p in sqldb.get_music_playlists(user_id)]

    return {
        "writable": scope.tools_writable,
        "unavailable": scope.tool_unavailable,
        "limits": {"playlists": playlists.MAX_PLAYLISTS, "songs": playlists.MAX_PLAYLIST_SONGS, "name": MAX_PLAYLIST_NAME_LENGTH},
        "playlists": await run_db(run),
    }


@router.get("/personal/playlists/{playlist_id}")
async def get_playlist(playlist_id: int, scope: PersonalScope = Depends(require_personal())):
    def run():
        _owned(scope, playlist_id)
        return _playlist_json(playlist_id)

    return {"playlist": await run_db(run)}


# ====== 寫入 ======
class CreateBody(BaseModel):
    name: str = Field(max_length=200)


@router.post("/personal/playlists")
async def create_playlist(body: CreateBody, scope: PersonalScope = Depends(require_personal(write=True))):
    def run():
        try:
            playlist = playlists.create_playlist(scope.tool_user_id, body.name)
        except MusicCommandError as e:
            raise _invalid(e) from e
        return {"playlist": _playlist_json(playlist.id)}

    return await run_db(run)


class RenameBody(BaseModel):
    name: str = Field(max_length=200)
    version: int


@router.patch("/personal/playlists/{playlist_id}")
async def rename_playlist(playlist_id: int, body: RenameBody, scope: PersonalScope = Depends(require_personal(write=True))):
    return await _write(scope, playlist_id, lambda playlist: playlists.rename_playlist(playlist, body.name, body.version))


@router.delete("/personal/playlists/{playlist_id}")
async def delete_playlist(playlist_id: int, version: int, scope: PersonalScope = Depends(require_personal(write=True))):
    def run():
        playlist = _owned(scope, playlist_id)
        try:
            sqldb.delete_music_playlist(playlist.id, version)
        except MusicPlaylistConflict as e:
            raise DashboardError(409, "conflict", deleted=e.deleted, current=None if e.deleted else _playlist_json(playlist_id)) from e
        return {"ok": True}

    return await run_db(run)


class AddBody(BaseModel):
    url: str = Field(max_length=_MAX_URL_LENGTH)
    version: int


@router.post("/personal/playlists/{playlist_id}/songs")
async def add_songs(playlist_id: int, body: AddBody, scope: PersonalScope = Depends(require_personal(write=True))):
    await run_db(lambda: _owned(scope, playlist_id))  # 先確認是自己的歌單，再花時間擷取
    try:
        extracted = playlists.Extracted.of(await extract_songs(body.url.strip(), None))
    except MusicCommandError as e:
        raise _invalid(e) from e
    return await _write(scope, playlist_id, lambda playlist: {"message": playlists.add_extracted(playlist, extracted, body.version)})


class SongIdsBody(BaseModel):
    song_ids: list[int] = Field(max_length=playlists.MAX_PLAYLIST_SONGS)
    version: int


@router.post("/personal/playlists/{playlist_id}/songs/remove")
async def remove_songs(playlist_id: int, body: SongIdsBody, scope: PersonalScope = Depends(require_personal(write=True))):
    def action(playlist):
        sqldb.remove_music_playlist_songs(playlist.id, body.song_ids, body.version)

    return await _write(scope, playlist_id, action)


@router.put("/personal/playlists/{playlist_id}/songs/order")
async def reorder_songs(playlist_id: int, body: SongIdsBody, scope: PersonalScope = Depends(require_personal(write=True))):
    def action(playlist):
        try:
            sqldb.reorder_music_playlist_songs(playlist.id, body.song_ids, body.version)
        except ValueError as e:
            raise DashboardError(400, "invalid_request") from e

    return await _write(scope, playlist_id, action)


class VersionBody(BaseModel):
    version: int


@router.post("/personal/playlists/{playlist_id}/sync")
async def sync_playlist(playlist_id: int, body: VersionBody, scope: PersonalScope = Depends(require_personal(write=True))):
    def load_sources():
        playlist = _owned(scope, playlist_id)
        sources = sqldb.get_music_playlist_sources(playlist.id)
        if not sources:
            raise DashboardError(400, "invalid_playlist", message=f"歌單「{playlist.name}」沒有匯入過外部歌單")
        return [(s.id, s.url) for s in sources]

    async def extract(url: str) -> playlists.Extracted:
        return playlists.Extracted.of(await extract_songs(url, None))

    refs = await run_db(load_sources)
    # 擷取很慢，先不碰資料庫；全部擷取完才在同一個交易裡寫入並檢查版本
    fetched = await playlists.fetch_sources([SimpleNamespace(id=i, url=url) for i, url in refs], extract)

    def action(playlist):
        with sqldb.lock_music_playlist(playlist.id, body.version):
            current = {s.id: s for s in sqldb.get_music_playlist_sources(playlist.id)}
            if len(current) != len(fetched) or any(item.source.id not in current for item in fetched):
                # 擷取期間來源被增減過，等同歌單被改過
                raise MusicPlaylistConflict()
            rebuilt = [playlists.SourceFetch(current[item.source.id], item.extracted, item.error) for item in fetched]
            return {"messages": playlists.apply_sync(playlist, rebuilt)}

    return await _write(scope, playlist_id, action)

