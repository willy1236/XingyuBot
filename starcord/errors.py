"""
### 模組：例外處理
提供錯誤代碼與錯誤訊息的類別
"""
# class StarException(Exception):
#     "starcord original error: 1000"
#     def __init__(self,
#                  message: str = None,
#                  code: int = None,
#                  original:Exception = None,
#                  original_message: str = None):
#         self.code = code or 1000
#         self.message = message or 'A Exception occurred.'
#         self.original = original
#         self.original_message = original_message

class StarException(Exception):
    """
    starcord original error: 1000
    :param message: 錯誤訊息
    :param code: 錯誤代碼
    :param original: 原始錯誤
    :param original_message: 原始錯誤提供的訊息，如果提供，將會使機器人自動回報
    """
    code = 1000
    message = 'A Exception occurred.'
    original = None
    original_message = None
    
    def __repr__(self):
        if self.original_message:
            return f'[{self.code}] {self.message} ({self.original_message})'
        else:
            return f'[{self.code}] {self.message}'

    def __str__(self):
        return f'[{self.code}] {self.message}'

class ApiError(StarException):
    "Api original error: 1100"
    code = 1100
    message = 'A Api exception occurred'

class ClientError(ApiError):
    def __init__(self,message=None,original_message=None):
        self.code = 1101
        self.message = '調用API時發生錯誤：' + message
        self.original_message = original_message

class CommandError(ApiError):
    def __init__(self,message=None,original_message=None):
        self.code = 1101
        self.message = '調用指令時發生錯誤：' + message
        self.original_message = original_message


class MysqlError(StarException):
    "MySQL original error: 1200"
    code = 1200

class DataExistError(MysqlError):
    code = 1201
    message = '新增的資料已存在'

class SQLNotFoundError(StarException):
    def __init__(self,message='找不到資料'):
        self.code = 1202
        self.message = message

class VoiceError(StarException):
    "Voice original error: 1300"
    code = 1300

class MusicCommandError(VoiceError):
    "Voice error while using command: 1301"
    def __init__(self,message='在使用音樂指令時發生錯誤'):
        self.code = 1301
        self.message = message

class MusicPlayingError(VoiceError):
    "Voice error while play_next: 1302"
    def __init__(self,message=None):
        self.code = 1302
        self.message = '在播放歌曲時發生錯誤：' + message

class RequestError(StarException):
    "Request original error: 1400"
    code = 1400

class Forbidden(RequestError):
    """Forbidden from request: 1401"""
    def __init__(self,message='在調用資料時被拒絕',original_message=None):
        self.code = 1401
        self.message = message
        self.original_message = original_message