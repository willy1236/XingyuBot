import logging
import os
from datetime import datetime

# 全局時間戳
timestamp = datetime.now().strftime("%Y-%m-%d %H_%M_%S")
logging.captureWarnings(True)

# 日誌格式常量
DEFAULT_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DETAILED_FORMAT = "%(asctime)s [%(levelname)s] %(name)s [%(filename)s:%(lineno)d]: %(message)s"


def create_logger(
    log_name: str,
    log_level=logging.DEBUG,
    file_log=False,
    dir_path="./logs",
    format_str=DEFAULT_FORMAT,
    file_name: str | None = None,
):
    """
    創建日誌記錄器。

    Args:
        log_name: 日誌記錄器名稱。
        log_level: 日誌等級。
        file_log: 是否記錄到文件。
        dir_path: 日誌目錄路徑。
        format_str: 日誌格式字串。
        file_name: 自定義檔名（不含副檔名）。若未提供則使用時間戳。

    Returns:
        logging.Logger: 配置完成的日誌記錄器。
    """
    formatter = logging.Formatter(format_str)
    logger = logging.getLogger(log_name)
    logger.setLevel(log_level)

    # 防止重複添加 handler
    if logger.hasHandlers():
        logger.handlers.clear()

    if file_log:
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)

        # 使用自定義文件名或預設文件名
        log_filename = f"{file_name or timestamp}.log"
        file_path = os.path.join(dir_path, log_filename)

        fileHandler = logging.FileHandler(filename=file_path, mode="a", encoding="utf-8")
        fileHandler.setLevel(log_level)
        fileHandler.setFormatter(formatter)
        logger.addHandler(fileHandler)

    # console handler
    consoleHandler = logging.StreamHandler()
    consoleHandler.setLevel(log_level)
    consoleHandler.setFormatter(formatter)
    logger.addHandler(consoleHandler)

    return logger


# ============ 統一日誌實例 ============
# 使用單一 logger，通過日誌等級區分不同類型的訊息

log = create_logger("starlib", log_level=logging.DEBUG, file_log=True, dir_path="./logs", format_str=DEFAULT_FORMAT, file_name="app")
