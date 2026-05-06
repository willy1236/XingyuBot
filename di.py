"""
Dependency Injection container base for XingyuBot.

提供一個輕量的 `dependency_injector` 容器，集中建立與提供
全域物件（設定、資料庫、事件匯流排等）。

使用範例：
    from starlib.di import init_container

    container = init_container()
    settings = container.config()
    sqldb = container.sqldb()

若需要自動注入，可呼叫 `container.wire(...)` 並在目標模組使用
`dependency_injector.wiring.inject` 與 `Provide[...]`。

此檔案僅提供基底容器，既有專案不會自動取代目前透過
模組級別單例（如 `starlib.core.sclient`、`starlib.database.sqldb`）的行為。
後續改造可在應用啟動（如 `main.py`）呼叫 container 並選擇性覆寫。
"""

from dependency_injector import containers, providers

from starlib.core import StarEventBus
from starlib.database import create_mongedb, create_sqldb
from starlib.settings import get_settings


class Container(containers.DeclarativeContainer):
    """應用層級的 DI 容器（基底）。

    - `config`: 由 `get_settings()` 建立的 `AppSettings` 實例
    - `sqldb`: 由既有 `create_sqldb()` 建立的 SQL repository
    - `mongedb`: 由既有 `create_mongedb()` 建立（根據設定決定是否連線）
    - `sclient`: 事件匯流排（`StarEventBus`）單例
    """

    wiring_config = containers.WiringConfiguration(packages=["starDiscord", "starServer", "starlib"])

    config = providers.Singleton(get_settings)

    # reuse existing factory helpers from starlib.database
    sqldb = providers.Singleton(create_sqldb)

    # create_mongedb(should_connect: bool) -> MongoDB | None
    mongedb = providers.Factory(create_mongedb, should_connect=config.provided.MONGODB_CONNECTION)

    sclient = providers.Singleton(StarEventBus)


def init_container() -> Container:
    """建立並回傳 Container 實例（輕量封裝）。

    之後可以呼叫 `container.wire(...)` 或透過 `container.<provider>()` 取得物件。
    """
    container = Container()
    return container


__all__ = ["Container", "init_container"]
