class StarException(Exception):
    "starcord original error: 1000"
    def __init__(self,
                 message: str = 'A exception occurred',
                 code: int = 1000,
                 original:Exception = None):
        
        self.code = code
        self.message = message
        self.original = original
    
    def __repr__(self):
        return f'[{self.code}] {self.message}'

    def __str__(self):
        return f'[{self.code}] {self.message}'


class CommandError(StarException):
    "Command original error: 1100"
    def __init__(self,
                 message: str = 'A command exception occurred'):
        self.code = 1100
        self.message = message

class MysqlError(StarException):
    "MySQL original error: 1200"

class MysqlError01(MysqlError):
    def __init__(self):
        self.code = 1201
        self.message = '新增的資料已存在'


class VoiceError(StarException):
    "Voice original error: 1300"

class VoiceError01(VoiceError):
    "Voice error while using command: 1301"
    def __init__(self,message='在使用音樂指令時發生錯誤'):
        self.code = 1301
        self.message = message

class VoiceError02(VoiceError):
    "Voice error while play_next: 1302"
    def __init__(self,message=None):
        self.code = 1302
        self.message = '在播放歌曲時發生錯誤：' + message