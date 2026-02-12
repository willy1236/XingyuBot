"""
### 模組：例外處理
提供錯誤代碼與錯誤訊息的類別

錯誤代碼範圍:
- 1000: 通用錯誤
- 1100: API 相關錯誤
- 1200: 資料庫相關錯誤
- 1300: 語音相關錯誤
- 1400: 請求相關錯誤
"""


class StarException(Exception):
    """
    starlib 的自定義例外基類。

    :param message: 錯誤訊息
    :param original: 原始例外物件
    :param original_message: 原始例外提供的訊息，若提供此參數，bot 將自動回報
    """

    code = 1000

    def __init__(self, message: str = "發生例外錯誤", original: Exception | None = None, original_message: str | None = None):
        super().__init__(message)
        self.message: str = message
        self.original: Exception | None = original
        self.original_message: str | None = original_message

    def __repr__(self) -> str:
        if self.original_message:
            return f"[{self.code}] {self.message} ({self.original_message})"
        return f"[{self.code}] {self.message}"

    def __str__(self) -> str:
        if self.original_message:
            return f"[{self.code}] {self.message} ({self.original_message})"
        return f"[{self.code}] {self.message}"


class ApiError(StarException):
    """API 相關錯誤基類 (錯誤代碼: 1100)"""

    code = 1100

    def __init__(self, message: str = "發生 API 例外錯誤", original: Exception | None = None, original_message: str | None = None):
        super().__init__(message, original, original_message)


class APIInvokeError(ApiError):
    """調用 API 時發生錯誤 (錯誤代碼: 1101)"""

    code = 1101

    def __init__(self, message: str | None = None, original: Exception | None = None, original_message: str | None = None):
        full_message = f"調用 API 時發生錯誤{f'：{message}' if message else ''}"
        super().__init__(full_message, original, original_message)


class CommandError(StarException):
    """調用指令時發生錯誤 (錯誤代碼: 1102)"""

    code = 1102

    def __init__(self, message: str | None = None, original: Exception | None = None, original_message: str | None = None):
        full_message = f"調用指令時發生錯誤{f'：{message}' if message else ''}"
        super().__init__(full_message, original, original_message)


class GenerateError(StarException):
    """生成資料時發生錯誤 (錯誤代碼: 1103)"""

    code = 1103

    def __init__(self, message: str | None = None, original: Exception | None = None, original_message: str | None = None):
        full_message = f"生成時發生錯誤{f'：{message}' if message else ''}"
        super().__init__(full_message, original, original_message)


class DatabaseError(StarException):
    """資料庫相關錯誤基類 (錯誤代碼: 1200)"""

    code = 1200

    def __init__(self, message: str = "發生資料庫錯誤", original: Exception | None = None, original_message: str | None = None):
        super().__init__(message, original, original_message)


class DataExistError(DatabaseError):
    """新增的資料已存在 (錯誤代碼: 1201)"""

    code = 1201

    def __init__(self, message: str = "新增的資料已存在", original: Exception | None = None, original_message: str | None = None):
        super().__init__(message, original, original_message)


class SQLNotFoundError(DatabaseError):
    """資料庫查詢結果為空 (錯誤代碼: 1202)"""

    code = 1202

    def __init__(self, message: str = "找不到資料", original: Exception | None = None, original_message: str | None = None):
        super().__init__(message, original, original_message)


class DataExpiredError(DatabaseError):
    """資料已經過期 (錯誤代碼: 1203)"""

    code = 1203

    def __init__(self, message: str = "資料已經過期", original: Exception | None = None, original_message: str | None = None):
        super().__init__(message, original, original_message)


class VoiceError(StarException):
    """語音相關錯誤基類 (錯誤代碼: 1300)"""

    code = 1300

    def __init__(self, message: str = "發生語音錯誤", original: Exception | None = None, original_message: str | None = None):
        super().__init__(message, original, original_message)


class MusicCommandError(VoiceError):
    """使用音樂指令時發生錯誤 (錯誤代碼: 1301)"""
    code = 1301

    def __init__(self, message: str = "在使用音樂指令時發生錯誤", original: Exception | None = None, original_message: str | None = None):
        super().__init__(message, original, original_message)


class MusicPlayingError(VoiceError):
    """播放歌曲時發生錯誤 (錯誤代碼: 1302)"""
    code = 1302

    def __init__(self, message: str | None = None, original: Exception | None = None, original_message: str | None = None):
        full_message = f"在播放歌曲時發生錯誤{f'：{message}' if message else ''}"
        super().__init__(full_message, original, original_message)


class RequestError(StarException):
    """請求相關錯誤基類 (錯誤代碼: 1400)"""
    code = 1400

    def __init__(self, message: str = "發生請求錯誤", original: Exception | None = None, original_message: str | None = None):
        super().__init__(message, original, original_message)


class Forbidden(RequestError):
    """請求被拒絕 (錯誤代碼: 1401)"""
    code = 1401

    def __init__(self, message: str = "在調用資料時被拒絕", original: Exception | None = None, original_message: str | None = None):
        super().__init__(message, original, original_message)
