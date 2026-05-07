# starlib/utils/logger.py
import logging
import sys


def setup_logging(level="INFO", file_log=False):
    """全平台統一日誌配置"""
    fmt = "%(asctime)s [%(levelname)s/%(name)s] %(message)s"

    # 配置 Root Logger
    logging.basicConfig(
        level=level,
        format=fmt,
        handlers=[
            logging.StreamHandler(sys.stdout)
            # 如果需要檔案日誌，可以在這裡加入 FileHandler
        ],
    )
