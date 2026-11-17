"""個人區的歌單（T-07）：假 auth server、假擷取，真實 PostgreSQL，交易結束後 rollback。"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_dashboard_auth import (  # noqa: F401  (fixture 與 helper)
    FRONTEND,
    USER_ID,
    dashboard_env,
    make_app,
    make_session,
)
from test_dashboard_domalyze_login import account
from test_identity import repo  # noqa: F401

from starlib import music_playlist as mp
from starlib.exceptions import MusicCommandError
from starlib.identity import BotIdentity, IdentityUnavailable
from starServer.dashboard import personal, personal_playlists

OWN = int(USER_ID)
HEADERS = {"Origin": FRONTEND}
BASE = "/dashboard/personal/playlists"


def _rows(n: int, prefix: str = "song") -> list[tuple[str, str, int | None]]:
    return [(f"https://example.com/{prefix}{i}", f"{prefix}{i}", 60 + i) for i in range(n)]


@pytest.fixture
def directory(dashboard_env):
    return dashboard_env.directory


@pytest.fixture
def identity(monkeypatch):
    state = {"result": None}

    async def fake(discord_id, *, create=True):
        if isinstance(state["result"], Exception):
            raise state["result"]
        return state["result"]

    monkeypatch.setattr(personal, "resolve_identity", fake)
    return state


@pytest.fixture
def extract(monkeypatch):
    """擷取結果依網址決定：results[url] 是 ExtractResult 風格的物件或 MusicCommandError。"""
    results: dict = {}

    async def fake(url, requester):
        assert requester is None
        result = results[url]
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(personal_playlists, "extract_songs", fake)
    return results


def _result(n: int, prefix: str = "s", playlist_url=None, playlist_title=None, skipped=0):
    songs = [SimpleNamespace(url=f"https://example.com/{prefix}{i}", title=f"{prefix}{i}", duration=60) for i in range(n)]
    return SimpleNamespace(songs=songs, skipped=skipped, playlist_url=playlist_url, playlist_title=playlist_title)


@pytest.fixture
def client(repo, identity, directory, extract, monkeypatch) -> TestClient:  # noqa: F811
    for module in (personal, personal_playlists, mp):
        monkeypatch.setattr(module, "sqldb", repo)
    app = make_app()
    c = TestClient(app, base_url="https://testserver", follow_redirects=False)
    make_session(repo)
    c.cookies.set("dashboard_session", "sid")
    return c


@pytest.fixture
def account_id(directory):
    """session 的 Discord 連結了析域帳號，工具類資料用這個 ID。"""
    acc_id = uuid4()
    directory.accounts[OWN] = account(acc_id)
    return acc_id


@pytest.fixture
def mine(repo, account_id):
    playlist = repo.create_music_playlist(account_id, "我的歌")
    repo.add_music_playlist_songs(playlist.id, _rows(3))
    repo.session.refresh(playlist)
    return playlist


def post(client, path, **body):
    return client.post(f"{BASE}{path}", json=body, headers=HEADERS)


class TestRead:
    def test_summary_and_detail(self, client, mine, repo):
        listing = client.get(BASE).json()
        assert listing["writable"] is True and listing["unavailable"] is False
        assert listing["limits"] == {"playlists": 25, "songs": 500, "name": 50}
        assert listing["playlists"] == [{"id": mine.id, "name": "我的歌", "version": 1, "song_count": 3}]

        detail = client.get(f"{BASE}/{mine.id}").json()["playlist"]
        assert [s["title"] for s in detail["songs"]] == ["song0", "song1", "song2"]
        assert detail["version"] == 1 and detail["sources"] == []

    def test_detail_matches_command_order_and_sources(self, client, mine, repo):
        source = repo.import_music_playlist_source(mine.id, "https://x/list", "外部", _rows(2, "src"))

        detail = client.get(f"{BASE}/{mine.id}").json()["playlist"]

        assert [s["title"] for s in detail["songs"]] == [s.title for s in repo.get_music_playlist_songs(mine.id)]
        assert detail["sources"][0]["id"] == source.id and detail["sources"][0]["title"] == "外部"

    def test_without_account_reads_temporary_id_readonly(self, client, identity, repo):
        temp = uuid4()
        identity["result"] = BotIdentity(temp, False, None, (), False)
        playlist = repo.create_music_playlist(temp, "舊的")
        repo.add_music_playlist_songs(playlist.id, _rows(1))

        listing = client.get(BASE).json()

        assert listing["writable"] is False
        assert [p["name"] for p in listing["playlists"]] == ["舊的"]
        assert client.get(f"{BASE}/{playlist.id}").status_code == 200

    def test_without_any_record_is_empty(self, client):
        assert client.get(BASE).json()["playlists"] == []

    def test_identity_unavailable_is_flagged(self, client, identity):
        identity["result"] = IdentityUnavailable()
        listing = client.get(BASE).json()
        assert (listing["unavailable"], listing["playlists"]) == (True, [])

    def test_others_playlist_is_404(self, client, repo, account_id):
        other = repo.create_music_playlist(uuid4(), "別人的")

        res = client.get(f"{BASE}/{other.id}")

        assert (res.status_code, res.json()) == (404, {"error": "not_found"})
        assert client.get(f"{BASE}/999999999").status_code == 404


class TestWriteAccess:
    @pytest.mark.parametrize(
        ("method", "path", "body"),
        [
            ("POST", "", {"name": "x"}),
            ("PATCH", "/1", {"name": "x", "version": 0}),
            ("DELETE", "/1?version=0", None),
            ("POST", "/1/songs", {"url": "u", "version": 0}),
            ("POST", "/1/songs/remove", {"song_ids": [], "version": 0}),
            ("PUT", "/1/songs/order", {"song_ids": [], "version": 0}),
            ("POST", "/1/sync", {"version": 0}),
        ],
    )
    def test_without_account_every_write_is_rejected(self, client, identity, repo, method, path, body):
        temp = uuid4()
        identity["result"] = BotIdentity(temp, False, None, (), False)
        playlist = repo.create_music_playlist(temp, "舊的")
        path = path.replace("/1", f"/{playlist.id}", 1)

        res = client.request(method, f"{BASE}{path}", json=body, headers=HEADERS)

        assert (res.status_code, res.json()) == (403, {"error": "domalyze_required"})
        assert repo.get_music_playlist(temp, "舊的") is not None

    @pytest.mark.parametrize(
        ("method", "path", "body"),
        [
            ("PATCH", "", {"name": "x", "version": 0}),
            ("DELETE", "?version=0", None),
            ("POST", "/songs", {"url": "https://u", "version": 0}),
            ("POST", "/songs/remove", {"song_ids": [1], "version": 0}),
            ("PUT", "/songs/order", {"song_ids": [1], "version": 0}),
            ("POST", "/sync", {"version": 0}),
        ],
    )
    def test_others_playlist_cannot_be_written(self, client, repo, account_id, extract, method, path, body):
        other = repo.create_music_playlist(uuid4(), "別人的")
        repo.add_music_playlist_songs(other.id, _rows(2))
        extract["https://u"] = _result(1)

        res = client.request(method, f"{BASE}/{other.id}{path}", json=body, headers=HEADERS)

        assert (res.status_code, res.json()) == (404, {"error": "not_found"})
        assert repo.count_music_playlist_songs(other.id) == 2
        assert repo.get_music_playlist_by_id(other.id).name == "別人的"


class TestCreateRenameDelete:
    def test_create_then_visible_to_commands(self, client, repo, account_id):
        res = post(client, "", name="  新歌單 ")

        assert res.status_code == 200
        assert res.json()["playlist"]["name"] == "新歌單"
        assert repo.get_music_playlist(account_id, "新歌單") is not None

    @pytest.mark.parametrize("name", ["", "   ", "x" * 51])
    def test_invalid_name(self, client, account_id, name):
        res = post(client, "", name=name)
        assert res.status_code == 400 and res.json()["error"] == "invalid_playlist"

    def test_duplicate_name(self, client, mine):
        res = post(client, "", name="我的歌")
        assert res.status_code == 400 and "已經有名為" in res.json()["message"]

    def test_rename_found_by_new_name(self, client, mine, repo, account_id):
        res = client.patch(f"{BASE}/{mine.id}", json={"name": "新名字", "version": 1}, headers=HEADERS)

        assert res.json()["playlist"]["name"] == "新名字" and res.json()["playlist"]["version"] == 2
        assert repo.get_music_playlist(account_id, "新名字").id == mine.id
        assert repo.get_music_playlist(account_id, "我的歌") is None

    def test_rename_to_same_name_with_stale_version_is_conflict(self, client, mine, repo):
        repo.add_music_playlist_songs(mine.id, _rows(1, "cmd"))

        res = client.patch(f"{BASE}/{mine.id}", json={"name": "我的歌", "version": 1}, headers=HEADERS)

        assert res.status_code == 409 and res.json()["current"]["version"] == 2

    def test_delete(self, client, mine, repo):
        res = client.delete(f"{BASE}/{mine.id}?version=1", headers=HEADERS)

        assert res.json() == {"ok": True}
        assert repo.get_music_playlist_by_id(mine.id) is None
        assert repo.get_music_playlist_songs(mine.id) == []

    def test_delete_with_stale_version_is_conflict_with_latest(self, client, mine, repo):
        repo.add_music_playlist_songs(mine.id, _rows(1, "cmd"))

        res = client.delete(f"{BASE}/{mine.id}?version=1", headers=HEADERS)

        assert res.status_code == 409
        body = res.json()
        assert body["error"] == "conflict" and body["deleted"] is False
        assert body["current"]["version"] == 2 and len(body["current"]["songs"]) == 4
        assert repo.get_music_playlist_by_id(mine.id) is not None


class TestSongs:
    def test_reorder_matches_command_view(self, client, mine, repo):
        ids = [s["id"] for s in client.get(f"{BASE}/{mine.id}").json()["playlist"]["songs"]]

        res = client.put(f"{BASE}/{mine.id}/songs/order", json={"song_ids": ids[::-1], "version": 1}, headers=HEADERS)

        assert [s["id"] for s in res.json()["playlist"]["songs"]] == ids[::-1]
        assert [s.id for s in repo.get_music_playlist_songs(mine.id)] == ids[::-1]

    def test_reorder_must_list_all_songs(self, client, mine, repo):
        ids = [s.id for s in repo.get_music_playlist_songs(mine.id)]

        res = client.put(f"{BASE}/{mine.id}/songs/order", json={"song_ids": ids[:2], "version": 1}, headers=HEADERS)

        assert (res.status_code, res.json()) == (400, {"error": "invalid_request"})

    def test_remove_three_at_once(self, client, mine, repo):
        repo.add_music_playlist_songs(mine.id, _rows(2, "more"))
        songs = repo.get_music_playlist_songs(mine.id)
        version = repo.get_music_playlist_by_id(mine.id).version

        res = post(client, f"/{mine.id}/songs/remove", song_ids=[s.id for s in songs[:3]], version=version)

        assert [s["title"] for s in res.json()["playlist"]["songs"]] == ["more0", "more1"]
        assert [s.position for s in repo.get_music_playlist_songs(mine.id)] == [0, 1]

    def test_add_single_url(self, client, mine, extract, repo):
        extract["https://u/a"] = _result(1, "a")

        res = post(client, f"/{mine.id}/songs", url=" https://u/a ", version=1)

        body = res.json()
        assert body["message"] == "已將 a0 加入歌單「我的歌」"
        assert len(body["playlist"]["songs"]) == 4 and body["playlist"]["version"] == 2

    def test_add_external_playlist_creates_source(self, client, mine, extract):
        extract["https://u/list"] = _result(2, "l", playlist_url="https://u/list", playlist_title="外部")

        res = post(client, f"/{mine.id}/songs", url="https://u/list", version=1)

        playlist = res.json()["playlist"]
        assert [s["title"] for s in playlist["sources"]] == ["外部"]
        assert len(playlist["songs"]) == 5 and playlist["version"] == 2

    def test_extract_failure_is_400(self, client, mine, extract):
        extract["https://u/bad"] = MusicCommandError("不受支援的連結")

        res = post(client, f"/{mine.id}/songs", url="https://u/bad", version=1)

        assert (res.status_code, res.json()) == (400, {"error": "invalid_playlist", "message": "不受支援的連結"})

    def test_add_with_stale_version_changes_nothing(self, client, mine, extract, repo):
        extract["https://u/list"] = _result(2, "l", playlist_url="https://u/list")
        repo.add_music_playlist_songs(mine.id, _rows(1, "cmd"))

        res = post(client, f"/{mine.id}/songs", url="https://u/list", version=1)

        assert res.status_code == 409
        assert repo.get_music_playlist_sources(mine.id) == []
        assert repo.count_music_playlist_songs(mine.id) == 4


class TestConflict:
    def test_command_change_blocks_next_operation_and_returns_latest(self, client, mine, repo):
        detail = client.get(f"{BASE}/{mine.id}").json()["playlist"]
        repo.add_music_playlist_songs(mine.id, _rows(1, "cmd"))  # 指令端在網頁打開後加了一首

        res = client.patch(f"{BASE}/{mine.id}", json={"name": "改名", "version": detail["version"]}, headers=HEADERS)

        assert res.status_code == 409
        body = res.json()
        assert body["error"] == "conflict" and body["deleted"] is False
        assert [s["title"] for s in body["current"]["songs"]] == ["song0", "song1", "song2", "cmd0"]
        assert body["current"]["name"] == "我的歌" and body["current"]["version"] == detail["version"] + 1

    def test_deleted_playlist(self, client, mine, repo):
        repo.delete_music_playlist(mine.id)
        res = client.patch(f"{BASE}/{mine.id}", json={"name": "x", "version": 1}, headers=HEADERS)
        assert (res.status_code, res.json()) == (404, {"error": "not_found"})

    def test_deleted_between_check_and_write(self, client, mine, repo, monkeypatch):
        real = repo.lock_music_playlist

        def delete_then_lock(playlist_id, expected_version=None):
            repo.delete_music_playlist(playlist_id)
            return real(playlist_id, expected_version)

        monkeypatch.setattr(repo, "lock_music_playlist", delete_then_lock)

        res = client.patch(f"{BASE}/{mine.id}", json={"name": "x", "version": 1}, headers=HEADERS)

        assert (res.status_code, res.json()) == (409, {"error": "conflict", "deleted": True, "current": None})


class TestSync:
    @pytest.fixture
    def with_sources(self, mine, repo):
        a = repo.import_music_playlist_source(mine.id, "https://u/a", "甲", _rows(2, "a"))
        b = repo.import_music_playlist_source(mine.id, "https://u/b", "乙", _rows(2, "b"))
        return a, b

    def test_manual_songs_survive_sync(self, client, mine, with_sources, extract, repo):
        extract["https://u/a"] = _result(3, "a")
        extract["https://u/b"] = MusicCommandError("私人歌單")
        version = repo.get_music_playlist_by_id(mine.id).version

        res = post(client, f"/{mine.id}/sync", version=version)

        body = res.json()
        assert body["messages"] == ["「甲」新增 1 首、移除 0 首", "「乙」同步失敗，保留原本的歌曲：私人歌單"]
        titles = [s["title"] for s in body["playlist"]["songs"]]
        assert titles[:3] == ["song0", "song1", "song2"] and len(titles) == 3 + 3 + 2
        assert body["playlist"]["version"] == version + 1

    def test_no_sources(self, client, mine):
        res = post(client, f"/{mine.id}/sync", version=1)
        assert res.status_code == 400 and "沒有匯入過外部歌單" in res.json()["message"]

    def test_command_change_during_fetch_is_conflict(self, client, mine, with_sources, extract, repo):
        version = repo.get_music_playlist_by_id(mine.id).version
        extract["https://u/a"] = _result(3, "a")
        extract["https://u/b"] = _result(3, "b")
        repo.add_music_playlist_songs(mine.id, _rows(1, "cmd"))

        res = post(client, f"/{mine.id}/sync", version=version)

        assert res.status_code == 409
        assert len(repo.get_music_playlist_songs(mine.id)) == 3 + 2 + 2 + 1
