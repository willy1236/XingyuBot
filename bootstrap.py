"""兩個入口（main、twitch_main）共用的啟動設定。

必須在匯入 py-cord、twitchAPI 與 starlib 之前呼叫 setup_runtime()：
asyncio 的 monkey-patch 與 warning 壓制要先生效，Sentry 要在其他模組的 logger 建立前初始化。
"""

import asyncio
import inspect
import logging
import sys
import warnings

import structlog

from sentry_bootstrap import init_sentry


def _setup_logging() -> None:
    shared_processors = [
        structlog.contextvars.merge_contextvars,  # 合併上下文變數
        structlog.processors.add_log_level,  # 加入日誌等級 (info, warn 等)
        structlog.stdlib.add_logger_name,  # 加入 logger 名稱
        structlog.stdlib.ExtraAdder(),  # 加入額外的上下文資訊（如函式名稱、行號等）
        structlog.processors.TimeStamper(fmt="%Y-%m-%dT%H:%M:%S.%f%z", utc=False),  # 加入 ISO 時間戳記
        structlog.processors.format_exc_info,  # 格式化異常資訊
    ]
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processor=structlog.dev.ConsoleRenderer(colors=True),
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    logging.basicConfig(handlers=[handler], level=logging.ERROR)


def setup_runtime(service: str) -> None:
    """套用 asyncio 修正與 warning 壓制、設定 logging、初始化 Sentry。"""
    asyncio.iscoroutinefunction = inspect.iscoroutinefunction  # 修正 asyncio.iscoroutinefunction 在 Python 3.11 之後的行為，避免第三方套件出現警告

    # 壓制所有第三方套件（虛擬環境 .venv 中）的棄用警告
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    warnings.filterwarnings("ignore", category=UserWarning, module=".*")
    logging.captureWarnings(False)

    init_sentry(service=service)

    from starlib.settings import get_settings

    log_level = get_settings().LOG_LEVEL

    _setup_logging()
    logging.getLogger("starDiscord").setLevel(log_level)
    logging.getLogger("starlib").setLevel(log_level)
    logging.getLogger("starServer.twitch_chatbot").setLevel(log_level)
    logging.getLogger("starServer.bot_website").setLevel(log_level)
    logging.getLogger("py.warnings").setLevel(logging.ERROR)
    logging.getLogger("discord").setLevel(logging.WARNING)
