"""merge_user_data：規格〈臨時轉正式與資料合併〉的規則表（真實 PostgreSQL，交易結束後 rollback），與兩條獨立連線的鎖測試。"""

from __future__ import annotations

import threading
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, delete, select

from starlib import sqldb
from starlib.database import DriveShare, LinkedAccount, NetBirdBinding, PlatformType
from starlib.database.postgresql.client import SQLRepository
from starlib.database.postgresql.models import MAX_PLAYLIST_NAME_LENGTH, DiscordIdentity, MusicPlaylist, MusicPlaylistSong, MusicPlaylistSource
from starlib.utils import nowtz

from test_identity import repo  # noqa: F401  (fixture)


def playlist(repo: SQLRepository, user_id: UUID, name: str, songs: int = 0) -> MusicPlaylist:
    pl = repo.create_music_playlist(user_id, name)
    if songs:
        repo.add_music_playlist_songs(pl.id, [(f"https://example.com/{i}", f"song {i}", None) for i in range(songs)])
    return pl


def names(repo: SQLRepository, user_id: UUID) -> list[str]:
    return sorted(p.name for p in repo.get_music_playlists(user_id))


def link(repo: SQLRepository, user_id: UUID, platform: PlatformType, external_id: str):
    repo.session.add(LinkedAccount(user_id=user_id, platform=platform, external_id=external_id))
    repo.commit()


def platforms(repo: SQLRepository, user_id: UUID) -> dict[PlatformType, str]:
    rows = repo.session.exec(select(LinkedAccount).where(LinkedAccount.user_id == user_id)).all()
    return {r.platform: r.external_id for r in rows}


@pytest.fixture
def ids() -> tuple[UUID, UUID]:
    return uuid4(), uuid4()


class TestPlaylists:
    def test_all_moved_with_songs_and_sources(self, repo, ids):
        old, new = ids
        pl = playlist(repo, old, "road trip", songs=3)
        repo.create_music_playlist_source(pl.id, "https://example.com/list", "list")
        playlist(repo, new, "mine")

        repo.merge_user_data(old, new)
        repo.commit()

        assert names(repo, old) == []
        assert names(repo, new) == ["mine", "road trip"]
        assert repo.count_music_playlist_songs(pl.id) == 3
        assert len(repo.get_music_playlist_sources(pl.id)) == 1

    def test_same_name_is_renamed_and_both_kept(self, repo, ids):
        old, new = ids
        playlist(repo, old, "fav", songs=2)
        playlist(repo, new, "fav", songs=1)

        repo.merge_user_data(old, new)
        repo.commit()

        assert names(repo, new) == ["fav", "fav (2)"]
        assert repo.count_music_playlist_songs(repo.get_music_playlist(new, "fav").id) == 1
        assert repo.count_music_playlist_songs(repo.get_music_playlist(new, "fav (2)").id) == 2

    def test_rename_increments_past_existing_suffix(self, repo, ids):
        old, new = ids
        playlist(repo, old, "fav")
        playlist(repo, new, "fav")
        playlist(repo, new, "fav (2)")

        repo.merge_user_data(old, new)
        repo.commit()

        assert names(repo, new) == ["fav", "fav (2)", "fav (3)"]

    def test_rename_does_not_collide_with_other_moved_playlist(self, repo, ids):
        old, new = ids
        playlist(repo, old, "fav")
        playlist(repo, old, "fav (2)")
        playlist(repo, new, "fav")

        repo.merge_user_data(old, new)
        repo.commit()

        assert names(repo, new) == ["fav", "fav (2)", "fav (3)"]

    def test_renamed_name_stays_within_length_limit(self, repo, ids):
        old, new = ids
        long_name = "x" * MAX_PLAYLIST_NAME_LENGTH
        playlist(repo, old, long_name)
        playlist(repo, new, long_name)
        playlist(repo, new, long_name[:-4] + " (2)")  # 截斷後的候選名稱已被佔用，要繼續遞增

        repo.merge_user_data(old, new)
        repo.commit()

        merged = names(repo, new)
        assert len(merged) == 3
        assert all(len(n) <= MAX_PLAYLIST_NAME_LENGTH for n in merged)
        assert long_name[:-4] + " (3)" in merged

    def test_noop_when_old_has_nothing(self, repo, ids):
        old, new = ids
        playlist(repo, new, "mine")

        repo.merge_user_data(old, new)

        assert names(repo, new) == ["mine"]


class TestOnePerUserData:
    def test_netbird_moves_when_new_has_none(self, repo, ids):
        old, new = ids
        repo.session.add(NetBirdBinding(user_id=old, group_id="g-old", group_name="old"))
        repo.commit()

        repo.merge_user_data(old, new)
        repo.commit()

        assert repo.get_netbird_binding(old) is None
        assert repo.get_netbird_binding(new).group_id == "g-old"

    def test_netbird_keeps_new_and_logs_discarded_group(self, repo, ids, caplog):
        old, new = ids
        repo.session.add(NetBirdBinding(user_id=old, group_id="g-old", group_name="old"))
        repo.session.add(NetBirdBinding(user_id=new, group_id="g-new", group_name="new"))
        repo.commit()

        with caplog.at_level("WARNING", logger="starlib.database.postgresql.client"):
            repo.merge_user_data(old, new)
        repo.commit()

        assert repo.get_netbird_binding(old) is None
        assert repo.get_netbird_binding(new).group_id == "g-new"
        assert any(getattr(r, "group_id", None) == "g-old" for r in caplog.records)

    def test_drive_share_moves_or_keeps_new(self, repo, ids):
        old, new = ids
        repo.session.add(DriveShare(user_id=old, gmail="old@example.com", share_id="s-old"))
        repo.commit()
        repo.merge_user_data(old, new)
        repo.commit()
        assert repo.session.get(DriveShare, new, populate_existing=True).share_id == "s-old"

        other_old = uuid4()
        repo.session.add(DriveShare(user_id=other_old, gmail="x@example.com", share_id="s-x"))
        repo.commit()
        repo.merge_user_data(other_old, new)
        repo.commit()
        assert repo.session.get(DriveShare, new, populate_existing=True).share_id == "s-old"
        assert repo.session.get(DriveShare, other_old, populate_existing=True) is None

    def test_linked_accounts_per_platform(self, repo, ids):
        old, new = ids
        link(repo, old, PlatformType.Minecraft, "mc-old")
        link(repo, old, PlatformType.Twitch, "tw-old")
        link(repo, old, PlatformType.Google, "g-old")
        link(repo, new, PlatformType.Twitch, "tw-new")

        repo.merge_user_data(old, new)
        repo.commit()

        assert platforms(repo, old) == {}
        assert platforms(repo, new) == {PlatformType.Minecraft: "mc-old", PlatformType.Twitch: "tw-new", PlatformType.Google: "g-old"}


class TestDiscordIdentities:
    def test_other_records_pointing_at_old_follow_to_new(self, repo, ids):
        old, new = ids
        other = uuid4()
        for discord_id, uid in ((900000000000000101, old), (900000000000000102, old), (900000000000000103, other)):
            repo.session.add(DiscordIdentity(discord_id=discord_id, user_id=uid, is_formal=False, checked_at=nowtz()))
        repo.commit()

        repo.merge_user_data(old, new)
        repo.commit()

        assert repo.get_discord_identity(900000000000000101).user_id == new
        assert repo.get_discord_identity(900000000000000102).user_id == new
        assert repo.get_discord_identity(900000000000000103).user_id == other

    def test_repointed_records_are_marked_for_recheck(self, repo, ids):
        """兄弟紀錄的 roles、suspended、username 還是舊域民的值，要強迫下次使用時重查"""
        old, new = ids
        repo.session.add(DiscordIdentity(discord_id=900000000000000104, user_id=old, is_formal=True, roles=["admin"], checked_at=nowtz()))
        repo.commit()

        repo.merge_user_data(old, new)
        repo.commit()

        record = repo.session.get(DiscordIdentity, 900000000000000104, populate_existing=True)
        assert nowtz() - record.checked_at > timedelta(days=365)


class TestRollback:
    @pytest.mark.parametrize("error", [SQLAlchemyError("boom"), RuntimeError("bug")])
    def test_failure_midway_rolls_back_moved_data(self, repo, ids, error):
        """歌單已搬完、綁定還沒處理時失敗：不論例外種類，已搬的資料都不能留在 session 等下一次 commit 提交"""
        old, new = ids
        playlist(repo, old, "fav")
        link(repo, old, PlatformType.Twitch, "tw")
        original = repo.session.exec

        def flaky(stmt, *args, **kwargs):
            result = original(stmt, *args, **kwargs)
            if "UPDATE users.music_playlist" in str(stmt):
                raise error
            return result

        repo.session.exec = flaky  # type: ignore[method-assign]
        try:
            with pytest.raises(type(error)):
                repo.merge_user_data(old, new)
        finally:
            repo.session.exec = original  # type: ignore[method-assign]

        repo.commit()
        assert names(repo, old) == ["fav"]
        assert names(repo, new) == []
        assert platforms(repo, old) == {PlatformType.Twitch: "tw"}


def _independent_repo() -> tuple[Session, SQLRepository]:
    session = Session(sqldb.engine)
    return session, SQLRepository(sqldb.engine, session)


class TestConcurrency:
    """兩條獨立連線：真實的 advisory lock 行為。測試資料用隨機 UUID，結束後清掉。"""

    def test_second_merge_waits_for_first_commit(self):
        a, b = uuid4(), uuid4()
        s1, r1 = _independent_repo()
        s2, r2 = _independent_repo()
        finished = threading.Event()
        errors: list[BaseException] = []

        def second():
            try:
                # 方向相反：依 UUID 排序取鎖，所以仍然撞到同一把，也不會死鎖
                r2.merge_user_data(b, a)
                r2.commit()
            except BaseException as e:  # noqa: BLE001
                errors.append(e)
            finally:
                finished.set()

        try:
            r1.merge_user_data(a, b)  # 持有鎖、尚未提交
            t = threading.Thread(target=second)
            t.start()

            assert not finished.wait(0.7), "第二個交易應該被鎖擋住"
            r1.commit()
            assert finished.wait(5), "第一個提交後第二個應該繼續"
            t.join()
            assert errors == []
        finally:
            s1.close()
            s2.close()

    def test_concurrent_merges_of_same_old_id_do_not_duplicate_or_lose_data(self):
        """驗的是結果正確（不重複、不遺失），不是鎖：拿掉鎖，行鎖與唯一鍵也會讓它過。驗鎖的是 test_second_merge_waits_for_first_commit。"""
        old, new = uuid4(), uuid4()
        setup_session, setup = _independent_repo()
        s1, r1 = _independent_repo()
        s2, r2 = _independent_repo()
        try:
            playlist(setup, old, "fav", songs=2)
            playlist(setup, old, "other")
            playlist(setup, new, "fav")
            setup.session.add(NetBirdBinding(user_id=old, group_id="g-old", group_name="o"))
            setup.session.add(NetBirdBinding(user_id=new, group_id="g-new", group_name="n"))
            setup.commit()

            errors: list[BaseException] = []
            barrier = threading.Barrier(2)

            def run(r: SQLRepository):
                try:
                    barrier.wait(5)
                    r.merge_user_data(old, new)
                    r.commit()
                except BaseException as e:  # noqa: BLE001
                    errors.append(e)

            threads = [threading.Thread(target=run, args=(r,)) for r in (r1, r2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(10)

            assert errors == []
            with Session(sqldb.engine) as check:
                check_repo = SQLRepository(sqldb.engine, check)
                assert names(check_repo, old) == []
                assert names(check_repo, new) == ["fav", "fav (2)", "other"]
                assert check_repo.get_netbird_binding(new).group_id == "g-new"
        finally:
            s1.close()
            s2.close()
            setup_session.close()
            with Session(sqldb.engine) as cleanup:
                playlist_ids = cleanup.exec(select(MusicPlaylist.id).where(MusicPlaylist.user_id.in_([old, new]))).all()
                cleanup.exec(delete(MusicPlaylistSong).where(MusicPlaylistSong.playlist_id.in_(playlist_ids)))
                cleanup.exec(delete(MusicPlaylistSource).where(MusicPlaylistSource.playlist_id.in_(playlist_ids)))
                cleanup.exec(delete(MusicPlaylist).where(MusicPlaylist.id.in_(playlist_ids)))
                cleanup.exec(delete(NetBirdBinding).where(NetBirdBinding.user_id.in_([old, new])))
                cleanup.commit()
