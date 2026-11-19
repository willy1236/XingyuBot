import logging
import sys

import structlog

# 1. 定義 structlog 的共享處理管線（保留字典格式）
shared_processors = [
    structlog.contextvars.merge_contextvars,  # 合併上下文變數
    structlog.processors.add_log_level,  # 加入日誌等級 (info, warn 等)
    structlog.processors.TimeStamper(fmt="iso", utc=False),  # 加入 ISO 時間戳記
]

# 2. 設定 Python 內建 logging 的 Formatter
# 終端機專用：美化彩色文字
console_formatter = structlog.stdlib.ProcessorFormatter(
    foreign_pre_chain=shared_processors,
    processor=structlog.dev.ConsoleRenderer(colors=True),
)

# 檔案專用：輸出 JSON 字串
json_formatter = structlog.stdlib.ProcessorFormatter(
    foreign_pre_chain=shared_processors,  # 修正點
    processor=structlog.processors.JSONRenderer(),
)

# 3. 建立並設定內建 logging 的 Handlers
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(console_formatter)

# file_handler = logging.FileHandler("app.log", encoding="utf-8")
# file_handler.setFormatter(json_formatter)

# 4. 註冊到 Python 內建的 Root Logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(console_handler)
# root_logger.addHandler(file_handler)

# 5. 配置 structlog 基礎設定
structlog.configure(
    processors=shared_processors
    + [
        # 將 structlog 的日誌字典包裝成內建 logging 看得懂的格式
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

# ==================== 測試使用 ====================
log = structlog.get_logger()

# 綁定上下文
ctx_log = log.bind(request_id="req-999", user_id="user_test")

ctx_log.info("user_login_success", status="active")
ctx_log.warning("rate_limit_warning", remaining_attempts=2)
