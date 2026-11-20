"""pytest 每次執行專用的暫時資料庫：`<原 DB 名>_test_<隨機碼>`，session 結束刪除。

`starlib.database` 在 import 時就依設定連線並 `create_all`，所以 `redirect()` 必須在任何 starlib import 之前呼叫；
它只改 `DB_NAME` 環境變數（pydantic-settings 的環境變數優先於 .env 檔），不動產品程式碼。
"""

from __future__ import annotations

import atexit
import importlib.util
import os
import secrets
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Connection, Engine
from sqlalchemy.pool import NullPool

#: 建立與清理暫時資料庫時互斥用的 advisory lock key（任意固定值）
_LOCK_KEY = 0x5354_4442_5445_5354 & 0x7FFF_FFFF_FFFF_FFFF

_admin: Engine | None = None
_keeper: Connection | None = None
_name: str | None = None
_source: URL | None = None


def _load_settings():
    """直接載入 starlib/settings.py：經由 `starlib` package import 會觸發連線，那時 DB_NAME 還沒改。"""
    path = Path(__file__).resolve().parents[2] / "starlib" / "settings.py"
    spec = importlib.util.spec_from_file_location("_temp_db_settings", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.get_settings()


def assert_test_database(name: str | None) -> None:
    """安全防線：名稱不含 `_test` 的資料庫一律拒絕，避免清掉開發或正式資料。"""
    if not name or "_test" not in name:
        raise RuntimeError(f"測試只能連名稱含 _test 的資料庫，目前是 {name!r}")


#: 測試在本次暫時資料庫底下另建的資料庫（如 test_migrate_identity）以 `<暫時資料庫>_mig_<隨機碼>` 命名
CHILD_INFIX = "_mig_"


def _drop_stale(conn: Connection, prefix: str) -> None:
    """刪掉中途被中斷而留下的暫時資料庫。不加 FORCE：有連線中的（別的 pytest 正在用）DROP 會失敗，跳過即可。

    子資料庫從 CREATE 到第一次連線之間沒有連線，所以母資料庫還有連線時一併視為使用中。
    """
    pattern = prefix.replace("\\", "\\\\").replace("_", "\\_").replace("%", "\\%") + "%"
    rows = conn.execute(
        text(
            "SELECT datname, EXISTS (SELECT 1 FROM pg_stat_activity a WHERE a.datname = d.datname) "
            "FROM pg_database d WHERE datname LIKE :pattern"
        ),
        {"pattern": pattern},
    ).all()
    in_use = {name for name, connected in rows if connected}
    for name, connected in rows:
        if connected or name.split(CHILD_INFIX)[0] in in_use:
            continue
        try:
            conn.execute(text(f'DROP DATABASE "{name}"'))
        except Exception:  # noqa: BLE001 別的 session 剛好連上，留給它自己刪
            pass


def redirect() -> str:
    """建立暫時資料庫並把 DB_NAME 指過去，回傳名稱；同一個 process 只建一次。"""
    global _admin, _keeper, _name, _source
    if _name is not None:
        return _name

    settings = _load_settings()
    prefix = f"{settings.DB_NAME}_test_"
    name = prefix + secrets.token_hex(6)
    assert_test_database(name)

    url = URL.create(
        drivername="postgresql+psycopg",
        username=settings.DB_USER,
        password=settings.DB_PASSWORD,
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        database=settings.DB_NAME,
    )
    _source = url
    # 建立、清理與鎖都在 maintenance DB `postgres` 上做；原 DB 只在 source_readonly() 唯讀讀取
    _admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT", poolclass=NullPool)
    with _admin.connect() as conn:
        # 建立到 keeper 連上之間，別的 process 的清理看不到連線；用 advisory lock 讓清理與建立互斥
        conn.execute(text("SELECT pg_advisory_lock(:key)"), {"key": _LOCK_KEY})
        try:
            _drop_stale(conn, prefix)
            conn.execute(text(f'CREATE DATABASE "{name}"'))
            # 整個 session 都留著這條連線，讓別的 process 判斷這個資料庫還在使用中
            _keeper = create_engine(url.set(database=name), poolclass=NullPool).connect()
        finally:
            conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": _LOCK_KEY})

    os.environ["DB_NAME"] = name
    _name = name
    # conftest 載入失敗時 pytest_unconfigure 不會執行，靠 atexit 兜底
    atexit.register(drop)
    return name


def source_readonly() -> Engine:
    """原 DB（如 stardb）的唯讀 engine：連線層設 default_transaction_read_only，任何寫入或 DDL 都會被 Postgres 拒絕。"""
    if _source is None:
        raise RuntimeError("redirect() 還沒呼叫")
    return create_engine(_source, poolclass=NullPool, connect_args={"options": "-c default_transaction_read_only=on"})


def drop(*engines: Engine) -> None:
    """session 結束：關掉用到暫時資料庫的連線並刪除它。"""
    global _keeper, _name
    if _name is None:
        return
    for engine in engines:
        engine.dispose()
    if _keeper is not None:
        _keeper.close()
        _keeper.engine.dispose()
        _keeper = None
    with _admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{_name}" WITH (FORCE)'))
    _admin.dispose()
    _name = None
