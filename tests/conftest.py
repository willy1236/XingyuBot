from tests.helpers.dashboard_auth import dashboard_env, site, spy  # noqa: F401  (fixture)
from tests.helpers.dashboard_guilds import discord as discord_env  # noqa: F401  (fixture)
from tests.helpers.identity import repo  # noqa: F401  (fixture)


def pytest_addoption(parser):
    parser.addoption(
        "--url",
        action="store",
        default=None,
        help="自訂擷取網址，供整合測試使用（支援 YouTube 單曲、歌單、Bilibili 等）",
    )
