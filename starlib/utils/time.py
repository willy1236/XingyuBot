from datetime import datetime, timedelta, timezone

_tz = timezone(timedelta(hours=8))


def ensure_utc(dt: datetime) -> datetime:
    """將 datetime 轉換為 UTC，若無時區則賦予 UTC 後轉換"""
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
                raise KeyError
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
