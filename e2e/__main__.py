"""入口。`--help` 以外的事都交給 `e2e.runner`，它必須在 import 任何 starlib 之前先轉向暫時資料庫。"""

import argparse
import sys
from pathlib import Path

from e2e.args import Args


def parse(argv: list[str]) -> Args:
    parser = argparse.ArgumentParser(prog="python -m e2e", description="XingyuBot 的 E2E（Web API 與 dashboard）")
    parser.add_argument("--cov-out", type=Path, default=Path(".e2e-coverage"), help="伺服器端覆蓋資料檔的位置")
    parser.add_argument("--api-port", type=int, default=14100)
    parser.add_argument("--frontend-port", type=int, default=3100)
    parser.add_argument("--only", action="append", default=[], help="只跑名稱含此字串的情境，可重複")
    parser.add_argument("--headed", action="store_true", help="瀏覽器情境顯示視窗")
    ns = parser.parse_args(argv)
    return Args(ns.cov_out.resolve(), ns.api_port, ns.frontend_port, tuple(ns.only), ns.headed)


if __name__ == "__main__":
    # Windows 主控台預設不是 UTF-8，情境訊息是中文
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    from e2e.runner import run

    sys.exit(run(parse(sys.argv[1:])))
