from datetime import datetime, timedelta, timezone
from typing import Annotated

from pydantic import AfterValidator

from ..utils.time import ensure_utc

# 定義一個全平台通用的時區型別
# 未來所有模型只要引用這個，就能確保資料一致
UTCDateTime = Annotated[datetime, AfterValidator(ensure_utc)]
