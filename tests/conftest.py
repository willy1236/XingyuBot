# 必須在任何 starlib import 之前：把 DB_NAME 轉到這次 pytest 專用的暫時資料庫
from tests.helpers import temp_db

temp_db.redirect()

from starlib import sqldb  # noqa: E402  轉向後才能 import

temp_db.assert_test_database(sqldb.engine.url.database if sqldb else None)

from tests.helpers import seed  # noqa: E402

seed.prepare(sqldb)

from tests.helpers.dashboard_auth import dashboard_env, site, spy, twitch_mods  # noqa: E402, F401  (fixture)
from tests.helpers.dashboard_guilds import discord as discord_env  # noqa: E402, F401  (fixture)
from tests.helpers.identity import repo  # noqa: E402, F401  (fixture)


def pytest_collection_finish(session):
    # session.items 已套用 -m／-k 篩選；選到 integration 測試時才改用原 DB 的真實憑證
    if any(item.get_closest_marker("integration") for item in session.items):
        seed.use_real_credentials(sqldb, temp_db.source_readonly())


def pytest_unconfigure(config):
    temp_db.drop(sqldb.engine)


def pytest_addoption(parser):
    parser.addoption(
        "--url",
        action="store",
        default=None,
        help="自訂擷取網址，供整合測試使用（支援 YouTube 單曲、歌單、Bilibili 等）",
    )
