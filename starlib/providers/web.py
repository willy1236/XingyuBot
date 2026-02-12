"""not used yet."""
from enum import IntEnum
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class APIResultCode(IntEnum):
    SUCCESS = 0
    ERROR = 1
    NOT_FOUND = 2
    UNAUTHORIZED = 3


class APIResult(BaseModel, Generic[T]):
    "Result Pattern for API responses"

    status: APIResultCode = Field(..., description="The status of the API response")
    data: T = Field(..., description="The data returned by the API")
    message: str | None = None

    @property
    def is_success(self) -> bool:
        return self.status == APIResultCode.SUCCESS
