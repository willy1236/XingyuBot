"""情境註冊：`@scenario("api")` 或 `@scenario("dashboard")` 標在一個 `def name(ctx)` 上，import 本套件即註冊。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from e2e.context import Ctx


@dataclass(frozen=True)
class Scenario:
    name: str
    kind: str  # "api" 或 "dashboard"
    run: Callable[[Ctx], None]


REGISTRY: list[Scenario] = []


def scenario(kind: str):
    def register(fn: Callable[[Ctx], None]) -> Callable[[Ctx], None]:
        REGISTRY.append(Scenario(f"{kind}/{fn.__name__}", kind, fn))
        return fn

    return register


def load_all() -> list[Scenario]:
    from e2e.scenarios import api, dashboard  # noqa: F401  import 時註冊

    return REGISTRY
