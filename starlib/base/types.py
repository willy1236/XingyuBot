from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator

from starlib.utils.time import ensure_local_tz

# 定義一個全平台通用的時區型別，驗證後一律是 UTC+8 的 aware datetime
# 未來所有模型只要引用這個，就能確保資料一致
LocalDateTime = Annotated[datetime, AfterValidator(ensure_local_tz)]
