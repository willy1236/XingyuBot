import logging,os,datetime

filename = datetime.datetime.now().strftime("%Y-%m-%d %H_%M_%S") + '.log'

def create_logger(dir_path,file_log=False,log_level=logging.DEBUG,log_name='py.warnings',format='%(asctime)s [%(levelname)s] %(message)s'):
    # config
    logging.captureWarnings(True)   # 捕捉 py waring message
    formatter = logging.Formatter(format)
    logger = logging.getLogger(log_name)    # 捕捉 py waring message
    logger.setLevel(log_level)

    if file_log:
        # 若不存在目錄則新建
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)

        # file handler
        fileHandler = logging.FileHandler(filename=f"{dir_path}/{filename}",mode='w',encoding='utf-8')
        fileHandler.setFormatter(formatter)
        logger.addHandler(fileHandler)

    # console handler
    consoleHandler = logging.StreamHandler()
    consoleHandler.setLevel(log_level)
    consoleHandler.setFormatter(formatter)
    logger.addHandler(consoleHandler)

    return logger