class Error(Exception):
    pass
        
class Error1(Error):
    def __init__(self):
        self.code = 1
        self.message = None
        self.original = None

class MysqlError():
    pass

class MysqlError1(MysqlError):
    def __init__(self):
        self.errno = 1
        self.message = '新增的資料已存在'

