from datetime import datetime, timedelta, timezone

_tz = timezone(timedelta(hours=8))


def ensure_utc(dt: datetime) -> datetime:
    """將 datetime 轉換為 UTC，若無時區則賦予 UTC"""
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
