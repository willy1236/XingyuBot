import logging
import os
from datetime import datetime

filename = datetime.now().strftime("%Y-%m-%d %H_%M_%S") + ".log"
logging.captureWarnings(True)

def create_logger(log_name, log_level=logging.DEBUG, file_log=False, dir_path="./logs", format="%(asctime)s [%(levelname)s] %(message)s"):
    # config
    formatter = logging.Formatter(format)
    logger = logging.getLogger(log_name)
    logger.setLevel(log_level)

    if file_log:
        # 若不存在目錄則新建
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)

        # file handler
        fileHandler = logging.FileHandler(filename=f"{dir_path}/{filename}", mode="w", encoding="utf-8")
        fileHandler.setFormatter(formatter)
        logger.addHandler(fileHandler)

    # console handler
    consoleHandler = logging.StreamHandler()
    consoleHandler.setLevel(log_level)
    consoleHandler.setFormatter(formatter)
    logger.addHandler(consoleHandler)

    return logger
