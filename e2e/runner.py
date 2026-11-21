"""E2E 的流程：暫時資料庫 → 假依賴與 Web API → 前端 → 情境 → 清理。

`run()` 開頭先把 `DB_NAME` 轉到暫時資料庫並啟動 coverage，之後才 import starlib／starServer。
結束代碼：0 全部通過，1 有情境失敗，2 環境或服務啟動失敗。
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
from dataclasses import dataclass

from e2e.args import TIMEOUT_ACTION, TIMEOUT_PAGE, Args, StartupError
from e2e.context import SESSION_COOKIE, Ctx, Failure

#: 要收覆蓋的伺服器端目錄
COVERED_DIRS = ("starServer", "starlib", "starDiscord")


@dataclass
class Result:
    name: str
    ok: bool
    seconds: float
    step: str = ""
    message: str = ""


def _prepare_env(args: Args) -> None:
    """後台設定走環境變數：CORS 的 origin 在 `dashboard.install` 時就固定，必須在 import 之前設好。"""
    os.environ.update(
        DASHBOARD_FRONTEND_URL=args.frontend_url,
        DASHBOARD_ALLOWED_ORIGINS=json.dumps([args.frontend_url]),
        DASHBOARD_OIDC_CLIENT_ID="e2e-client",
        DASHBOARD_OIDC_CLIENT_SECRET="e2e-secret",
        DASHBOARD_OIDC_REDIRECT_URI=f"{args.api_url}/oauth/domalyze",
    )


def _start_coverage(args: Args):
    import coverage

    from e2e.services import ROOT

    args.cov_out.parent.mkdir(parents=True, exist_ok=True)
    cov = coverage.Coverage(data_file=str(args.cov_out), include=[f"{ROOT}/{d}/*" for d in COVERED_DIRS])
    cov.erase()
    cov.start()
    return cov


def _format(result: Result) -> str:
    if result.ok:
        return f"  通過  {result.name}  ({result.seconds:.1f}s)"
    return f"  失敗  {result.name}  ({result.seconds:.1f}s)\n        步驟：{result.step}\n        {result.message}"


def _run_scenario(scenario, ctx: Ctx) -> Result:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import TimeoutError as PlaywrightTimeout

    started = time.monotonic()
    try:
        scenario.run(ctx)
        return Result(scenario.name, True, time.monotonic() - started)
    except Failure as e:
        message = str(e)
    except AssertionError as e:
        # playwright 的 expect 以 AssertionError 回報，訊息含定位器與預期；只留前幾行，不印整頁 snapshot
        message = "畫面上的元素與預期不符：" + " / ".join(line.strip() for line in str(e).strip().splitlines()[:3])
    except PlaywrightTimeout as e:
        message = f"畫面上找不到或等不到預期的元素：{str(e).strip().splitlines()[0]}"
    except PlaywrightError as e:
        message = f"瀏覽器錯誤：{str(e).strip().splitlines()[0]}"
    except Exception:  # noqa: BLE001 情境裡的任何錯誤都要報成這個情境失敗，而不是中斷整個 E2E
        message = traceback.format_exc(limit=4)
    finally:
        ctx.close()
    return Result(scenario.name, False, time.monotonic() - started, ctx.current_step, message)


def run(args: Args) -> int:
    from tests.helpers import temp_db

    _prepare_env(args)
    temp_db.redirect()
    cov = _start_coverage(args)
    services = []
    patches = None
    bot = None
    sqldb = None
    exit_code = 2
    try:
        from starlib import sclient, sqldb  # noqa: F811  轉向之後才能 import

        temp_db.assert_test_database(sqldb.engine.url.database)
        from tests.helpers import seed

        seed.prepare(sqldb)

        from e2e import data, fakes
        from e2e.services import ApiServer, Frontend
        from starServer import bot_website
        from tests.helpers.dashboard_setup import Patches, install_fakes

        patches = Patches()
        from starlib.database import APIType

        credential = sqldb.get_oauth_client(APIType.Discord, 4)
        install_fakes(
            patches.setattr,
            frontend_url=args.frontend_url,
            allowed_origins=[args.frontend_url],
            credential_id=credential.credential_id,
        )
        bot = fakes.FakeBot(fakes.FakeGuild())
        patches.setattr(sclient, "bot", bot)
        session_id = data.seed(sqldb)

        print(f"E2E：暫時資料庫 {sqldb.engine.url.database}")
        api = ApiServer(bot_website.app, args.api_port)
        services.append(api)
        api.start()
        frontend = Frontend(args.api_url, args.frontend_port)
        services.append(frontend)
        print(f"E2E：Web API {args.api_url} 已啟動，啟動 domalyze_frontend（首次編譯較慢）…")
        t0 = time.monotonic()
        frontend.start()
        print(f"E2E：dashboard {args.frontend_url} 已就緒（{time.monotonic() - t0:.0f}s）")

        from e2e.scenarios import load_all

        selected = [s for s in load_all() if not args.only or any(o in s.name for o in args.only)]
        _prewarm(args)
        results = _run_scenarios(args, session_id, selected)
        passed = sum(r.ok for r in results)
        print(f"\n總結：{passed}/{len(results)} 個情境通過")
        exit_code = 0 if results and passed == len(results) else 1
    except StartupError as e:
        print(f"\nE2E 無法啟動：{e}", file=sys.stderr)
    except Exception:  # noqa: BLE001
        print("\nE2E 發生未預期的錯誤：", file=sys.stderr)
        traceback.print_exc()
    finally:
        for service in reversed(services):
            service.stop()
        if bot is not None:
            bot.stop()
        if patches is not None:
            patches.undo()
        cov.stop()
        cov.save()
        temp_db.drop(*([sqldb.engine] if sqldb is not None else []))
        print(f"E2E：覆蓋資料 {args.cov_out}")
    return exit_code


def _prewarm(args: Args) -> None:
    """next dev 第一次請求某個路由才編譯它：先逐一請求，瀏覽器情境就不必等編譯。"""
    import httpx

    from e2e.scenarios.dashboard import PREWARM

    t0 = time.monotonic()
    for path in PREWARM:
        try:
            httpx.get(args.frontend_url + path, verify=False, timeout=TIMEOUT_PAGE)
        except httpx.HTTPError as e:
            raise StartupError(
                "frontend", f"預熱 {path} 失敗：{e!r}。next dev 編譯該頁時出錯，請看 frontend 輸出。"
            ) from e
    print(f"E2E：dashboard 路由預熱完成（{time.monotonic() - t0:.0f}s）")


def _run_scenarios(args: Args, session_id: str, selected) -> list[Result]:
    import httpx
    from playwright.sync_api import sync_playwright

    results: list[Result] = []
    headers = {"Origin": args.frontend_url}
    with (
        httpx.Client(
            base_url=args.api_url,
            verify=False,
            headers=headers,
            cookies={SESSION_COOKIE: session_id},
            timeout=30,
        ) as http,
        sync_playwright() as pw,
    ):
        browser = pw.chromium.launch(headless=not args.headed)
        try:
            for scenario in selected:
                browser_context = None
                if scenario.kind == "dashboard":
                    browser_context = browser.new_context(ignore_https_errors=True)
                    browser_context.set_default_timeout(TIMEOUT_ACTION * 1000)
                    browser_context.set_default_navigation_timeout(TIMEOUT_PAGE * 1000)
                    browser_context.add_cookies(
                        [
                            {
                                "name": SESSION_COOKIE,
                                "value": session_id,
                                "domain": "localhost",
                                "path": "/",
                                "secure": True,
                                "httpOnly": True,
                                "sameSite": "Lax",
                            }
                        ]
                    )
                ctx = Ctx(args, session_id, http, browser_context)
                result = _run_scenario(scenario, ctx)
                if browser_context is not None:
                    browser_context.close()
                results.append(result)
                print(_format(result), flush=True)
        finally:
            browser.close()
    return results
