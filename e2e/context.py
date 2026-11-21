"""情境共用的 `Ctx`：HTTP client、瀏覽器頁面，以及讓失敗輸出指到步驟的 `step()`。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from e2e.args import TIMEOUT_ACTION, TIMEOUT_PAGE, Args

SESSION_COOKIE = "dashboard_session"


class Failure(Exception):
    """情境的斷言失敗，訊息寫明預期與實際。"""


@dataclass
class Ctx:
    args: Args
    session_id: str
    http: httpx.Client
    browser_context: Any = None  # playwright BrowserContext；API 情境不需要
    current_step: str = "（尚未開始）"
    _page: Any = field(default=None, repr=False)

    def step(self, name: str) -> None:
        self.current_step = name

    # ---- API ----
    def api(self, method: str, path: str, *, expect: int = 200, **kwargs) -> Any:
        """呼叫 API 並回傳 JSON；HTTP 狀態不是預期值就失敗，訊息含狀態與回應內容。"""
        response = self.http.request(method, path, **kwargs)
        if response.status_code != expect:
            raise Failure(f"{method} {path} 回 HTTP {response.status_code}（預期 {expect}）：{response.text[:300]}")
        return response.json() if response.content else None

    def expect(self, actual: Any, expected: Any, what: str) -> None:
        if actual != expected:
            raise Failure(f"{what}：預期 {expected!r}，實際 {actual!r}")

    # ---- 瀏覽器 ----
    @property
    def page(self):
        if self._page is None:
            self._page = self.browser_context.new_page()
            self._page.set_default_timeout(TIMEOUT_ACTION * 1000)
            self._page.set_default_navigation_timeout(TIMEOUT_PAGE * 1000)
        return self._page

    def goto(self, path: str) -> None:
        self.page.goto(self.args.frontend_url + path, wait_until="domcontentloaded")

    def close(self) -> None:
        if self._page is not None:
            self._page.close()
            self._page = None
