"""
### 模組：例外處理
提供錯誤代碼與錯誤訊息的類別
"""

class StarException(Exception):
    """
    A custom exception class for starlib.

    :param message: The error message.
    :param code: The error code.
    :param original: The original error.
    :param original_message: The message provided by the original error. If provided, the bot will automatically report it.
    """
    code = 1000

    def __init__(self, message="A Exception occurred.", original: Exception | None = None, original_message: str | None = None):
        self.message: str = message
        self.original: Exception | None = original
        self.original_message: str | None = original_message

    def __repr__(self):
        if self.original_message:
            return f"[{self.code}] {self.message} ({self.original_message})"
        else:
            return f"[{self.code}] {self.message}"

    def __str__(self):
        if self.original_message:
            return f"[{self.code}] {self.message} ({self.original_message})"
        else:
            return f"[{self.code}] {self.message}"


class ApiError(StarException):
    """Api original error: 1100"""
    code = 1100
    message = "A Api exception occurred"


class APIInvokeError(ApiError):
    """A error occurred while calling API: 1101"""

    code = 1101

    def __init__(self, message=None, original_message=None):
        self.message = "調用API時發生錯誤：" + message
        self.original_message = original_message


class CommandError(ApiError):
    code = 1102

    def __init__(self, message=None, original_message=None):
        self.message = "調用指令時發生錯誤：" + message
        self.original_message = original_message


class GenerateError(ApiError):
    code = 1103

    def __init__(self, message=None, original_message=None):
        self.message = "生成時發生錯誤：" + message
        self.original_message = original_message


class DatabaseError(StarException):
    """Database original error: 1200"""
    code = 1200


class DataExistError(DatabaseError):
    code = 1201
    message = "新增的資料已存在"


class SQLNotFoundError(StarException):
    code = 1202

    def __init__(self, message="找不到資料"):
        self.message = message


class DataExpiredError(StarException):
    code = 1203

    def __init__(self, message="資料已經過期"):
        self.message = message


class VoiceError(StarException):
    """Voice original error: 1300"""

    code = 1300


class MusicCommandError(VoiceError):
    """Voice error while using command: 1301"""

    code = 1301

    def __init__(self, message="在使用音樂指令時發生錯誤"):
        self.message = message


class MusicPlayingError(VoiceError):
    "Voice error while play_next: 1302"

    code = 1302

    def __init__(self, message=None):
        self.message = "在播放歌曲時發生錯誤：" + message


class RequestError(StarException):
    "Request original error: 1400"

    code = 1400


class Forbidden(RequestError):
    """Forbidden from request: 1401"""

    code = 1401

    def __init__(self, message="在調用資料時被拒絕", original_message=None):
        self.message = message
        self.original_message = original_message
