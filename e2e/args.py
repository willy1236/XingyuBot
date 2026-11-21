from dataclasses import dataclass
from pathlib import Path

#: 各階段的逾時（秒）。next dev 首次編譯慢，前端的值抓寬
TIMEOUT_API_START = 60
TIMEOUT_FRONTEND_START = 240
TIMEOUT_PAGE = 180
TIMEOUT_ACTION = 30


@dataclass(frozen=True)
class Args:
    cov_out: Path
    api_port: int
    frontend_port: int
    only: tuple[str, ...]
    headed: bool

    @property
    def api_url(self) -> str:
        return f"https://localhost:{self.api_port}"

    @property
    def frontend_url(self) -> str:
        return f"https://localhost:{self.frontend_port}"


class StartupError(Exception):
    """環境或服務啟動失敗：`service` 是哪個服務，訊息要寫怎麼修。"""

    def __init__(self, service: str, message: str):
        super().__init__(f"[{service}] {message}")
        self.service = service
