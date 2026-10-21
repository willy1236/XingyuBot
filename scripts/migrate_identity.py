"""
一次性轉換：把 cloud_user 底下的歌單、NetBird、外部帳號綁定、雲端資料夾轉到新的使用者 ID（任務卡 T-08）。

用法（先停 bot、切到新版 code 再跑；新版 code import 時會建好 discord_identity 等新表）：
    python scripts/migrate_identity.py --dry-run --report identity-dry-run.json
    python scripts/migrate_identity.py --report identity-migration.json

- 每個 cloud_user 的主帳號是 external_account.id 最小的 Discord 列；主帳號查得到域民就轉到 account_id，查不到發臨時 ID。
- 兩個 cloud_user 的主帳號屬於同一位域民時，cloud_user.id 小的直接轉，其餘先轉到暫用 ID 再 merge_user_data。
- 先查完所有人才寫入；auth server 沒給出明確答案就中止，不發任何臨時 ID。
- 整個轉換在單一交易內，--dry-run 跑完整流程後 rollback，資料不變；新表若還不存在，import 時會先建好空表。
- 舊表有新表收不下的資料（平台不在名單、external_id 為空、同人同平台兩筆）就中止並列出，不自行取捨。
- 舊表以 raw SQL 讀取，不依賴舊 model。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import text

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from starlib.database import PlatformType
from starlib.database.postgresql.client import SQLRepository
from starlib.database.postgresql.models import DiscordIdentity
from starlib.identity import AccountDirectory, DirectoryUnavailable
from starlib.utils import nowtz

# 搬到 linked_account 的平台；Discord 改由 discord_identity 記錄
LINKED_PLATFORMS = (PlatformType.Twitch, PlatformType.Google, PlatformType.Minecraft)

LEGACY_COUNTS = {
    "playlists": "SELECT count(*) FROM users.music_playlist",
    "songs": "SELECT count(*) FROM users.music_playlist_song",
    "sources": "SELECT count(*) FROM users.music_playlist_source",
    "netbird": "SELECT count(*) FROM users.netbird_binding",
    "linked": "SELECT count(*) FROM users.external_account WHERE platform = ANY(:platforms)",
    "drive": "SELECT count(*) FROM users.cloud_user WHERE drive_gmail IS NOT NULL AND drive_share_id IS NOT NULL",
}

NEW_COUNTS = {
    **LEGACY_COUNTS,
    "linked": "SELECT count(*) FROM users.linked_account",
    "drive": "SELECT count(*) FROM users.drive_share",
}

LEGACY_USERS = """
SELECT c.id,
       coalesce(c.privilege_level, 0) AS privilege_level,
       (SELECT e.external_id FROM users.external_account e
         WHERE e.user_id = c.id AND e.platform = :discord ORDER BY e.id LIMIT 1) AS discord_id,
       (c.drive_gmail IS NULL) <> (c.drive_share_id IS NULL) AS partial_drive,
       (SELECT count(*) FROM users.music_playlist p WHERE p.user_id = c.id) AS playlists,
       (SELECT count(*) FROM users.netbird_binding n WHERE n.user_id = c.id) AS netbird,
       (SELECT count(*) FROM users.external_account e
         WHERE e.user_id = c.id AND e.platform = ANY(:platforms)) AS linked,
       (c.drive_gmail IS NOT NULL AND c.drive_share_id IS NOT NULL)::int AS drive
FROM users.cloud_user c
ORDER BY c.id
"""

# 舊 schema 允許、新表收不下或腳本沒有規則處理的資料；有命中就中止並列出 external_account.id
LEGACY_CHECKS = {
    "平台不是 Discord／Twitch／Google／Minecraft": (
        "SELECT id FROM users.external_account WHERE platform IS NULL OR NOT (platform = :discord OR platform = ANY(:platforms)) ORDER BY id"
    ),
    "external_id 是空的": "SELECT id FROM users.external_account WHERE external_id IS NULL ORDER BY id",
    "Discord 的 external_id 不是數字": "SELECT id FROM users.external_account WHERE platform = :discord AND external_id !~ '^[0-9]+$' ORDER BY id",
    "同一個 cloud_user 有兩筆同平台綁定": (
        "SELECT id FROM users.external_account e WHERE platform = ANY(:platforms) AND EXISTS "
        "(SELECT 1 FROM users.external_account o WHERE o.user_id = e.user_id AND o.platform = e.platform AND o.id <> e.id) ORDER BY id"
    ),
}

CONVERT = [
    "CREATE TEMP TABLE identity_map (cloud_user_id integer PRIMARY KEY, user_id uuid NOT NULL) ON COMMIT DROP",
    "INSERT INTO identity_map VALUES (:cloud_user_id, :user_id)",
    # 歌單：拿掉 user_id 時舊 FK、唯一鍵、index 一起消失，改名後照 model 重建
    "ALTER TABLE users.music_playlist ADD COLUMN user_uuid uuid",
    "UPDATE users.music_playlist p SET user_uuid = m.user_id FROM identity_map m WHERE m.cloud_user_id = p.user_id",
    "ALTER TABLE users.music_playlist DROP COLUMN user_id",
    "ALTER TABLE users.music_playlist RENAME COLUMN user_uuid TO user_id",
    "ALTER TABLE users.music_playlist ALTER COLUMN user_id SET NOT NULL",
    "ALTER TABLE users.music_playlist ADD CONSTRAINT unique_user_playlist_name UNIQUE (user_id, name)",
    "CREATE INDEX ix_users_music_playlist_user_id ON users.music_playlist (user_id)",
    # NetBird：user_id 是 PK
    "ALTER TABLE users.netbird_binding ADD COLUMN user_uuid uuid",
    "UPDATE users.netbird_binding n SET user_uuid = m.user_id FROM identity_map m WHERE m.cloud_user_id = n.user_id",
    "ALTER TABLE users.netbird_binding DROP COLUMN user_id",
    "ALTER TABLE users.netbird_binding RENAME COLUMN user_uuid TO user_id",
    "ALTER TABLE users.netbird_binding ADD CONSTRAINT netbird_binding_pkey PRIMARY KEY (user_id)",
    """
    INSERT INTO users.linked_account (user_id, platform, external_id, display_name, platform_data)
    SELECT m.user_id, e.platform, e.external_id, e.display_name, coalesce(e.platform_data, '{}'::json)
    FROM users.external_account e JOIN identity_map m ON m.cloud_user_id = e.user_id
    WHERE e.platform = ANY(:platforms)
    ORDER BY e.id
    """,
    """
    INSERT INTO users.drive_share (user_id, gmail, share_id)
    SELECT m.user_id, c.drive_gmail, c.drive_share_id
    FROM users.cloud_user c JOIN identity_map m ON m.cloud_user_id = c.id
    WHERE c.drive_gmail IS NOT NULL AND c.drive_share_id IS NOT NULL
    """,
]


class MigrationAborted(Exception):
    """轉換前檢查不過或 auth server 沒給出明確答案；資料庫沒有任何變動"""


@dataclass
class UserResult:
    cloud_user_id: int
    privilege_level: int
    discord_id: int | None
    # 資料最終掛的使用者 ID；沒有 Discord 列而略過時為 None
    user_id: UUID | None = None
    is_formal: bool = False
    username: str | None = None
    roles: tuple[str, ...] = ()
    suspended: bool = False
    # 與 cloud_user.id 較小的人屬於同一位域民，資料先轉到暫用 ID 再併入 user_id
    merged: bool = False
    counts: dict[str, int] = field(default_factory=dict)


@dataclass
class Report:
    dry_run: bool
    users: list[UserResult]
    before: dict[str, int]
    after: dict[str, int]

    @property
    def admins(self) -> list[UserResult]:
        return [u for u in self.users if u.privilege_level > 0]

    @property
    def top_playlist_users(self) -> list[UserResult]:
        """歌單最多的 5 位，轉換後抽查用"""
        owners = [u for u in self.users if u.counts.get("playlists")]
        return sorted(owners, key=lambda u: -u.counts["playlists"])[:5]

    @property
    def skipped(self) -> list[UserResult]:
        return [u for u in self.users if u.user_id is None]

    def to_dict(self) -> dict:
        return json.loads(json.dumps(asdict(self), default=str))


async def migrate(repo: SQLRepository, directory: AccountDirectory, *, dry_run: bool) -> Report:
    """轉換舊身分資料；dry_run 時跑完整流程後 rollback。檢查不過或 auth server 不可用時 raise MigrationAborted。"""
    session = repo.session
    try:
        users = _load_legacy_users(session)
        await _assign_ids(users, directory)
        before = _counts(session, LEGACY_COUNTS)
        staging = _write(session, users, before)
        for staging_id, user_id in staging:
            repo.merge_user_data(staging_id, user_id)
        after = _counts(session, NEW_COUNTS)
        _verify_after_merge(session, before, after, [s for s, _ in staging])
    except BaseException:
        session.rollback()
        raise
    if dry_run:
        session.rollback()
    else:
        session.commit()
    return Report(dry_run=dry_run, users=users, before=before, after=after)


def _load_legacy_users(session) -> list[UserResult]:
    is_legacy = session.execute(
        text(
            "SELECT data_type = 'integer' FROM information_schema.columns "
            "WHERE table_schema = 'users' AND table_name = 'music_playlist' AND column_name = 'user_id'"
        )
    ).scalar()
    if not is_legacy:
        raise MigrationAborted("users.music_playlist.user_id 已不是 integer，看起來已經轉換過")
    for table in ("discord_identity", "linked_account", "drive_share"):
        if session.execute(text(f"SELECT exists(SELECT 1 FROM users.{table})")).scalar():
            raise MigrationAborted(f"users.{table} 已有資料，轉換前應為空表")

    params = {"discord": PlatformType.Discord, "platforms": list(LINKED_PLATFORMS)}
    for problem, query in LEGACY_CHECKS.items():
        ids = session.execute(text(query), params).scalars().all()
        if ids:
            raise MigrationAborted(f"external_account {problem}：id {ids}")

    rows = session.execute(text(LEGACY_USERS), params).mappings()
    users = []
    for r in rows:
        counts = {k: r[k] for k in ("playlists", "netbird", "linked", "drive")}
        if r["discord_id"] is None and any(counts.values()):
            raise MigrationAborted(f"cloud_user {r['id']} 沒有 Discord 帳號但有資料：{counts}")
        if r["partial_drive"]:
            raise MigrationAborted(f"cloud_user {r['id']} 的雲端資料夾只填了 gmail 或 share_id 其中一個")
        discord_id = int(r["discord_id"]) if r["discord_id"] is not None else None
        users.append(UserResult(cloud_user_id=r["id"], privilege_level=r["privilege_level"], discord_id=discord_id, counts=counts))
    return users


async def _assign_ids(users: list[UserResult], directory: AccountDirectory) -> None:
    owners: set[UUID] = set()
    for u in users:
        if u.discord_id is None:
            continue
        try:
            account = await directory.find_by_discord(u.discord_id)
        except DirectoryUnavailable as e:
            raise MigrationAborted(f"auth server 沒有給出明確答案（cloud_user {u.cloud_user_id}）：{e}") from e
        if account is None:
            u.user_id = uuid4()
            continue
        u.user_id = account.account_id
        u.is_formal = True
        u.username = account.username
        u.roles = account.roles
        u.suspended = account.suspended
        u.merged = account.account_id in owners
        owners.add(account.account_id)


def _write(session, users: list[UserResult], before: dict[str, int]) -> list[tuple[UUID, UUID]]:
    """寫入新表與欄位，回傳要合併的（暫用 ID, 正式 ID）"""
    params = {"platforms": list(LINKED_PLATFORMS)}
    mapped = [u for u in users if u.user_id is not None]
    staging: list[tuple[UUID, UUID]] = []
    id_map = []
    for u in mapped:
        data_id = u.user_id
        if u.merged:
            data_id = uuid4()
            staging.append((data_id, u.user_id))
        id_map.append({"cloud_user_id": u.cloud_user_id, "user_id": data_id})

    session.execute(text(CONVERT[0]))
    session.execute(text(CONVERT[1]), id_map)
    for stmt in CONVERT[2:]:
        session.execute(text(stmt), params if ":platforms" in stmt else {})

    checked_at = nowtz()
    for u in mapped:
        session.add(
            DiscordIdentity(
                discord_id=u.discord_id,
                user_id=u.user_id,
                is_formal=u.is_formal,
                username=u.username,
                roles=list(u.roles),
                suspended=u.suspended,
                checked_at=checked_at,
            )
        )
    session.flush()

    converted = _counts(session, NEW_COUNTS)
    if converted != before:
        raise MigrationAborted(f"轉換後筆數不符：轉換前 {before}，轉換後 {converted}")
    return staging


def _verify_after_merge(session, before: dict[str, int], after: dict[str, int], staging_ids: list[UUID]) -> None:
    for key in ("playlists", "songs", "sources"):
        if after[key] != before[key]:
            raise MigrationAborted(f"合併後 {key} 筆數不符：{before[key]} → {after[key]}")
    for table in ("music_playlist", "netbird_binding", "linked_account", "drive_share"):
        left = session.execute(text(f"SELECT count(*) FROM users.{table} WHERE user_id = ANY(:ids)"), {"ids": staging_ids}).scalar()
        if left:
            raise MigrationAborted(f"合併後 users.{table} 仍有 {left} 筆掛在暫用 ID")


def _counts(session, queries: dict[str, str]) -> dict[str, int]:
    params = {"platforms": list(LINKED_PLATFORMS)}
    return {k: session.execute(text(q), params if ":platforms" in q else {}).scalar() for k, q in queries.items()}


def format_report(report: Report) -> str:
    lines = [f"== 身分轉換{'（dry-run，已 rollback）' if report.dry_run else ''} =="]
    lines.append(f"{'cloud_user':>10}  {'discord_id':<20}  {'結果':<4}  {'user_id':<36}  {'域民代號':<16}  歌單 NetBird 綁定 雲端")
    for u in report.users:
        if u.user_id is None:
            result = "略過"
        else:
            result = "合併" if u.merged else ("正式" if u.is_formal else "臨時")
        c = u.counts
        lines.append(
            f"{u.cloud_user_id:>10}  {str(u.discord_id or '-'):<20}  {result:<4}  {str(u.user_id or '-'):<36}  {u.username or '-':<16}  "
            f"{c['playlists']:>4} {c['netbird']:>7} {c['linked']:>4} {c['drive']:>4}"
        )
    lines.append("")
    lines.append("== 筆數（轉換前 → 轉換後）==")
    for key in report.before:
        lines.append(f"{key:>10}: {report.before[key]} → {report.after[key]}")
    lines.append("")
    lines.append("== 管理員（privilege_level > 0）==")
    for u in report.admins:
        account = u.username or ("已註冊" if u.is_formal else "未註冊")
        lines.append(f"cloud_user {u.cloud_user_id}  Level {u.privilege_level}  discord {u.discord_id}  析域帳號 {account}  roles {list(u.roles)}")
    lines.append("")
    lines.append("== 歌單最多的使用者（抽查用）==")
    for u in report.top_playlist_users:
        lines.append(f"cloud_user {u.cloud_user_id}  discord {u.discord_id}  歌單 {u.counts['playlists']}")
    if report.skipped:
        lines.append("")
        lines.append("== 沒有 Discord 帳號而略過的 cloud_user ==")
        lines.extend(f"cloud_user {u.cloud_user_id}" for u in report.skipped)
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="把 cloud_user 的資料轉到新的使用者 ID（T-08）")
    parser.add_argument("--dry-run", action="store_true", help="跑完整流程後 rollback，資料庫不變")
    parser.add_argument("--report", type=Path, help="另存一份 JSON 報告")
    args = parser.parse_args()
    if args.report and not args.report.parent.is_dir():
        parser.error(f"報告目錄不存在：{args.report.parent}")

    from starlib import sqldb
    from starlib.identity import DomalyzeIdentityClient
    from starlib.settings import get_settings

    settings = get_settings()
    directory = DomalyzeIdentityClient(settings.AUTH_INTERNAL_URL, settings.AUTH_SERVICE_KEY, timeout=5)
    try:
        report = asyncio.run(migrate(sqldb, directory, dry_run=args.dry_run))
    except MigrationAborted as e:
        print(f"轉換中止，資料庫沒有變動：{e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"轉換失敗，已 rollback，資料庫沒有變動：{e!r}", file=sys.stderr)
        return 1
    print(format_report(report))
    if args.report:
        args.report.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n報告已存到 {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
