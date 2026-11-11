import re
from datetime import datetime, timedelta, timezone

from dateutil import parser as _date_parser
from dateutil.relativedelta import relativedelta

_tz = timezone(timedelta(hours=8))

_RELATIVE_UNITS = {
    "d": "days", "天": "days",
    "h": "hours", "hr": "hours", "小時": "hours",
    "m": "minutes", "min": "minutes", "分": "minutes", "分鐘": "minutes",
    "s": "seconds", "秒": "seconds",
}  # fmt: skip
_RELATIVE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(分鐘|小時|min|hr|[dhms天分秒])")
_DAY_WORDS = {"今天": 0, "today": 0, "明天": 1, "tomorrow": 1, "後天": 2}
_AM_WORDS = ("凌晨", "早上", "上午")
_PM_WORDS = ("中午", "下午", "傍晚", "晚上")
# 兩組年月日都不同的預設值，用來判斷輸入省略了哪些欄位
_DEFAULT_A = datetime(2000, 1, 1)
_DEFAULT_B = datetime(2001, 2, 2)


def parse_datetime(text: str, now: datetime | None = None) -> datetime | None:
    """把使用者輸入的時間解析成 UTC+8 的 datetime，無法辨認時回傳 None

    支援相對時間（「3d」「1天12小時」「90m」「2小時後」）與各種絕對時間寫法
    （「2026-11-07 20:00」「2026/11/7 8pm」「11/7 20:00」「11月7日 晚上8點半」「明天 20:00」「20:00」）。
    省略年、月或日期時取最近的未來時間：已過的「1/2」視為明年，已過的「20:00」視為明天。
    """
    now = now or nowtz()
    text = text.strip().lower()
    if not text:
        return None

    relative = text.removesuffix("later").removesuffix("後").strip()
    if _RELATIVE_RE.search(relative) and not _RELATIVE_RE.sub("", relative).strip():
        delta = timedelta()
        for value, unit in _RELATIVE_RE.findall(relative):
            delta += timedelta(**{_RELATIVE_UNITS[unit]: float(value)})
        return now + delta

    day_offset = None
    for word, offset in _DAY_WORDS.items():
        if word in text:
            day_offset = offset
            text = text.replace(word, " ")

    meridiem = ""
    for words, suffix in ((_AM_WORDS, " am"), (_PM_WORDS, " pm")):
        for word in words:
            if word in text:
                text = text.replace(word, " ")
                meridiem = suffix

    text = re.sub(r"(\d+)\s*[點時]\s*半", r"\1:30", text)
    text = re.sub(r"(\d+)\s*[點時]\s*(\d+)\s*分?", r"\1:\2", text)
    text = re.sub(r"(\d+)\s*[點時]", r"\1:00", text)
    text = re.sub(r"[年月]", "/", text)
    text = re.sub(r"[日號秒分]", " ", text)
    text = text.strip(" /") + meridiem

    try:
        parsed_a = _date_parser.parse(text, default=_DEFAULT_A)
        parsed_b = _date_parser.parse(text, default=_DEFAULT_B)
    except ValueError, OverflowError:
        return None

    has_year = parsed_a.year == parsed_b.year
    has_month = parsed_a.month == parsed_b.month
    has_day = parsed_a.day == parsed_b.day
    if day_offset is not None and (has_year or has_month or has_day):
        return None

    base = now + timedelta(days=day_offset or 0)
    try:
        result = datetime(
            parsed_a.year if has_year else base.year,
            parsed_a.month if has_month else (1 if has_year else base.month),
            parsed_a.day if has_day else (1 if has_month else base.day),
            parsed_a.hour,
            parsed_a.minute,
            parsed_a.second,
            tzinfo=parsed_a.tzinfo or _tz,
        )
    except ValueError:
        return None

    if result <= now and day_offset is None:
        if not has_year and has_month:
            result += relativedelta(years=1)
        elif not has_month and has_day:
            result += relativedelta(months=1)
        elif not has_day and not has_month and not has_year:
            result += timedelta(days=1)
    return result


def ensure_local_tz(dt: datetime) -> datetime:
    """將 datetime 統一成 UTC+8；沒有時區的 datetime 視為 UTC+8 時間，有時區的轉換到 UTC+8"""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=_tz)
    return dt.astimezone(_tz)


def convert_tz(dt: datetime, offset: int = 8) -> datetime:
    """將 UTC 時間轉移至指定時區"""
    target_tz = timezone(timedelta(hours=offset))
    return dt.astimezone(target_tz)


def nowtz() -> datetime:
    """獲取當前 timezone-aware 時間"""
    return datetime.now(tz=_tz)


def time_to_sec(arg: str):
    """10s->1,0用str相加 s則轉換後用int相乘"""
    dict = {"s": 1, "m": 60, "h": 3600}
    n = 0
    m = ""
    for i in arg:
        try:
            int(i)
            m += i
        except ValueError:
            try:
                m = int(m)
                n = n + (m * dict[i])
                m = ""
            except KeyError:
                raise
    return n


def time_to_datetime(arg: str):
    m = ""
    days = 0
    hours = 0
    minutes = 0
    seconds = 0
    for i in arg:
        try:
            int(i)
            m += i
        except ValueError:
            m = int(m)
            if i == "d":
                days = m
            elif i == "h":
                hours = m
            elif i == "m":
                minutes = m
            elif i == "s":
                seconds = m
            m = ""
    return timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)


def format_seconds(seconds: int) -> str:
    """秒數轉成中文時長，例如 600 → 10 分鐘、5400 → 1 小時 30 分鐘。"""
    parts = []
    for unit, size in (("天", 86400), ("小時", 3600), ("分鐘", 60), ("秒", 1)):
        count, seconds = divmod(seconds, size)
        if count:
            parts.append(f"{count} {unit}")
    return " ".join(parts) or "0 秒"
