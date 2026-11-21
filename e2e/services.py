"""E2E 的外部行程：Web API（同行程內的 uvicorn 執行緒）與 domalyze_frontend 的 `next dev`。

啟動前先預檢，失敗一律丟 `StartupError(服務名稱, 怎麼修)`；每個等待都有逾時，不會卡住。
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
import psutil

from e2e.args import TIMEOUT_API_START, TIMEOUT_FRONTEND_START, Args, StartupError

ROOT = Path(__file__).resolve().parent.parent
FRONTEND_ENV = "XINGYU_E2E_FRONTEND"
CERT_NAME = "localhost+2.pem"
KEY_NAME = "localhost+2-key.pem"


def _main_checkout() -> Path:
    """XingyuBot 主 checkout：worktree 與主 checkout 共用同一個 git common dir。"""
    out = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        return ROOT
    return Path(out.stdout.strip()).parent


def frontend_dir() -> Path:
    override = os.environ.get(FRONTEND_ENV)
    path = Path(override) if override else _main_checkout().parent / "domalyze_frontend"
    if not (path / "package.json").is_file():
        raise StartupError(
            "frontend",
            f"找不到 domalyze_frontend（{path}）。把它 clone 到 XingyuBot 主 checkout 旁邊，或設定環境變數 {FRONTEND_ENV}。",
        )
    if not (path / "node_modules" / "next").is_dir():
        raise StartupError("frontend", f"{path} 尚未安裝套件，請先在該目錄執行 `pnpm install`（或 npm install）。")
    return path


def cert_files() -> tuple[Path, Path]:
    """本機 https 憑證（不進版控）：先找這個 checkout，再找主 checkout。"""
    for base in (ROOT, _main_checkout()):
        cert, key = base / "database" / CERT_NAME, base / "database" / KEY_NAME
        if cert.is_file() and key.is_file():
            return cert, key
    raise StartupError(
        "api", f"找不到 database/{CERT_NAME} 與 {KEY_NAME}（本機 https 憑證），請用 mkcert 產生後放在 database/。"
    )


def port_in_use(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _check_port(service: str, port: int, flag: str) -> None:
    if port_in_use(port):
        raise StartupError(service, f"port {port} 已被佔用。關掉佔用的程式，或改用 {flag} 指定其他 port。")


def _running_dev_server(frontend: Path) -> str | None:
    """frontend 已有 `next dev` 在跑時回傳描述它的字串：Next.js 同一個專案不能同時跑兩個。

    dev server 啟動時建立並鎖住 `.next/dev/lock`；Windows 上鎖住的檔案讀不了，讀得到時內容有 pid。
    """
    lock = frontend / ".next" / "dev" / "lock"
    if not lock.is_file():
        return None
    try:
        pid = int(json.loads(lock.read_text(encoding="utf-8")).get("pid"))
    except OSError:
        return "pid 不明"
    except ValueError, TypeError:
        return None
    return f"pid {pid}" if psutil.pid_exists(pid) else None


@dataclass(frozen=True)
class Preflight:
    frontend: Path
    cert: Path
    key: Path


def _check_browser() -> None:
    """Playwright 的 chromium 沒裝時，到跑第一個瀏覽器情境才會失敗；先擋下並說明怎麼裝。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise StartupError(
            "browser", "沒有安裝 playwright。執行 `uv sync` 後再 `uv run playwright install chromium`。"
        ) from e

    with sync_playwright() as pw:
        installed = Path(pw.chromium.executable_path).is_file()
    if not installed:
        raise StartupError(
            "browser", "Playwright 的 chromium 還沒安裝。執行 `uv run playwright install chromium` 後重跑。"
        )


def preflight(args: Args) -> Preflight:
    """啟動任何東西之前的檢查：憑證、frontend 目錄、瀏覽器、port、frontend 是否已有 dev server。"""
    cert, key = cert_files()
    _check_browser()
    frontend = frontend_dir()
    _check_port("api", args.api_port, "--api-port")
    _check_port("frontend", args.frontend_port, "--frontend-port")
    if (running := _running_dev_server(frontend)) is not None:
        raise StartupError(
            "frontend",
            f"domalyze_frontend 已有 dev server 在跑（{running}）；Next.js 同一個專案不能同時跑兩個。"
            "請自行結束它（taskkill /PID <pid> /F）再重跑，E2E 不會替你關。",
        )
    return Preflight(frontend, cert, key)


def _ignore_reset(loop, context: dict) -> None:
    """瀏覽器關閉連線時 Windows 的 proactor 會丟 ConnectionResetError，不是產品問題，不印出來干擾輸出。"""
    if isinstance(context.get("exception"), ConnectionResetError):
        return
    loop.default_exception_handler(context)


class ApiServer:
    """同行程內的 uvicorn：app 與假依賴都在這個行程，覆蓋資料才收得到。"""

    def __init__(self, app, port: int, cert: Path, key: Path):
        self.app, self.port, self.cert, self.key = app, port, cert, key
        self.server = None
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        import uvicorn

        config = uvicorn.Config(
            self.app,
            host="127.0.0.1",
            port=self.port,
            ssl_certfile=str(self.cert),
            ssl_keyfile=str(self.key),
            log_level="warning",
        )
        self.server = uvicorn.Server(config)
        self.server.install_signal_handlers = lambda: None  # 不在主執行緒，不能裝 signal handler
        self.thread = threading.Thread(target=self._serve, name="e2e-api", daemon=True)
        self.thread.start()
        deadline = time.monotonic() + TIMEOUT_API_START
        while not self.server.started:
            if not self.thread.is_alive():
                raise StartupError("api", "Web API 啟動時結束了，原因見上方的錯誤訊息。")
            if time.monotonic() > deadline:
                raise StartupError("api", f"Web API 在 {TIMEOUT_API_START} 秒內沒有啟動完成。")
            time.sleep(0.1)

    def _serve(self) -> None:
        loop = asyncio.new_event_loop()
        loop.set_exception_handler(_ignore_reset)
        try:
            loop.run_until_complete(self.server.serve())
        finally:
            loop.close()

    def stop(self) -> None:
        if self.server is not None:
            self.server.should_exit = True
        if self.thread is not None:
            self.thread.join(timeout=15)


class Frontend:
    """domalyze_frontend 的 `next dev --experimental-https`，輸出寫到暫存檔，失敗時附上尾端。"""

    def __init__(self, api_url: str, port: int, directory: Path):
        self.api_url, self.port, self.directory = api_url, port, directory
        self.process: subprocess.Popen | None = None
        self.log_path = Path(tempfile.gettempdir()) / f"xingyu-e2e-frontend-{os.getpid()}.log"
        self._log = None

    def start(self) -> None:
        frontend = self.directory
        env = {**os.environ, "NEXT_PUBLIC_BASE_API_URL": self.api_url, "NEXT_TELEMETRY_DISABLED": "1"}
        next_bin = frontend / "node_modules" / "next" / "dist" / "bin" / "next"
        self._log = self.log_path.open("wb")
        self.process = subprocess.Popen(
            ["node", str(next_bin), "dev", "--experimental-https", "-p", str(self.port)],
            cwd=frontend,
            env=env,
            stdout=self._log,
            stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + TIMEOUT_FRONTEND_START
        while True:
            if self.process.poll() is not None:
                raise StartupError(
                    "frontend", f"next dev 啟動時結束了（exit {self.process.returncode}）。\n{self._tail()}"
                )
            try:
                if (
                    httpx.get(f"https://localhost:{self.port}/dashboard-login", verify=False, timeout=5).status_code
                    < 500
                ):
                    return
            except httpx.HTTPError:
                pass
            if time.monotonic() > deadline:
                raise StartupError(
                    "frontend",
                    f"next dev 在 {TIMEOUT_FRONTEND_START} 秒內沒有就緒（首次編譯很慢時可再試一次）。\n{self._tail()}",
                )
            time.sleep(1)

    def _tail(self, lines: int = 20) -> str:
        try:
            text = self.log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
        return "frontend 輸出尾端：\n" + "\n".join(text.splitlines()[-lines:])

    def stop(self) -> None:
        if self.process is not None and self.process.poll() is None:
            try:
                parent = psutil.Process(self.process.pid)
                procs = [*parent.children(recursive=True), parent]
            except psutil.NoSuchProcess:
                procs = []
            for p in procs:
                try:
                    p.kill()
                except psutil.NoSuchProcess:
                    pass
            psutil.wait_procs(procs, timeout=15)
        if self._log is not None:
            self._log.close()
        self.log_path.unlink(missing_ok=True)
