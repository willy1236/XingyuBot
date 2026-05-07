from enum import IntEnum
from typing import Generic, TypeVar

import requests
from pydantic import BaseModel, Field

from starlib.exceptions import APINetworkError

T = TypeVar("T")


class APICaller:
    """HTTP API caller wrapper built on top of requests.

    This class provides common HTTP methods and centralizes network exception
    handling by wrapping ``requests`` exceptions into ``APINetworkError``.

    Attributes:
        base_url: Default base URL used when endpoint is not an absolute URL.
    """

    base_url: str = ""

    def __init__(self, headers: dict | None = None, base_url: str | None = None):
        """Initialize an API caller instance.

        Args:
            headers: Default request headers attached to every request.
            base_url: Optional instance-level base URL override.
        """
        self.headers = headers or {}
        if base_url is not None:
            self.base_url = base_url

    def _request(
        self,
        method: str,
        endpoint: str,
        base_url: str | None = None,
        **kwargs,
    ) -> requests.Response | None:
        """Send an HTTP request and normalize network exceptions.

        Args:
            method: HTTP method name, such as ``GET`` or ``POST``.
            endpoint: Relative endpoint path or absolute URL.
            base_url: Optional per-call base URL override for relative endpoints.
            **kwargs: Extra keyword arguments passed to ``requests.request``.

        Returns:
            requests.Response | None: Response object returned by requests,
                or ``None`` when status code is 404.

        Raises:
            APINetworkError: If request fails or response status is neither 2xx nor 404.
        """
        if endpoint.startswith(("http://", "https://")):
            url = endpoint
        else:
            target_base = base_url or self.base_url
            url = f"{target_base.rstrip('/')}/{endpoint.lstrip('/')}"
        request_headers = {**self.headers, **kwargs.pop("headers", {})}

        try:
            response = requests.request(method, url, headers=request_headers, **kwargs)
            if response.status_code == requests.codes.not_found:
                return None
            if not (200 <= response.status_code < 300):
                raise APINetworkError(
                    message=f"{method.upper()} {url} 回傳狀態碼 {response.status_code}",
                    original=requests.HTTPError(f"HTTP {response.status_code}: {response.reason}", response=response),
                    original_message=response.text,
                )
            return response
        except requests.RequestException as exc:
            raise APINetworkError(
                message=f"{method.upper()} {url}",
                original=exc,
                original_message=str(exc),
            ) from exc

    def get(
        self,
        endpoint: str,
        params: dict | None = None,
        base_url: str | None = None,
        **kwargs,
    ) -> requests.Response | None:
        """Send a GET request.

        Args:
            endpoint: Relative endpoint path or absolute URL.
            params: Query string parameters.
            base_url: Optional per-call base URL override.
            **kwargs: Extra keyword arguments passed to ``requests.request``.

        Returns:
            requests.Response | None: Response object returned by requests,
                or ``None`` when status code is 404.

        Raises:
            APINetworkError: If any ``requests.RequestException`` occurs.
        """
        return self._request("GET", endpoint, params=params, base_url=base_url, **kwargs)

    def post(
        self,
        endpoint: str,
        data: dict | None = None,
        base_url: str | None = None,
        **kwargs,
    ) -> requests.Response | None:
        """Send a POST request.

        Args:
            endpoint: Relative endpoint path or absolute URL.
            data: JSON payload body.
            base_url: Optional per-call base URL override.
            **kwargs: Extra keyword arguments passed to ``requests.request``.

        Returns:
            requests.Response | None: Response object returned by requests,
                or ``None`` when status code is 404.

        Raises:
            APINetworkError: If any ``requests.RequestException`` occurs.
        """
        return self._request("POST", endpoint, json=data, base_url=base_url, **kwargs)

    def put(
        self,
        endpoint: str,
        data: dict | None = None,
        base_url: str | None = None,
        **kwargs,
    ) -> requests.Response | None:
        """Send a PUT request.

        Args:
            endpoint: Relative endpoint path or absolute URL.
            data: JSON payload body.
            base_url: Optional per-call base URL override.
            **kwargs: Extra keyword arguments passed to ``requests.request``.

        Returns:
            requests.Response | None: Response object returned by requests,
                or ``None`` when status code is 404.

        Raises:
            APINetworkError: If any ``requests.RequestException`` occurs.
        """
        return self._request("PUT", endpoint, json=data, base_url=base_url, **kwargs)

    def patch(
        self,
        endpoint: str,
        data: dict | None = None,
        base_url: str | None = None,
        **kwargs,
    ) -> requests.Response | None:
        """Send a PATCH request.

        Args:
            endpoint: Relative endpoint path or absolute URL.
            data: JSON payload body.
            base_url: Optional per-call base URL override.
            **kwargs: Extra keyword arguments passed to ``requests.request``.

        Returns:
            requests.Response | None: Response object returned by requests,
                or ``None`` when status code is 404.

        Raises:
            APINetworkError: If any ``requests.RequestException`` occurs.
        """
        return self._request("PATCH", endpoint, json=data, base_url=base_url, **kwargs)

    def delete(
        self,
        endpoint: str,
        base_url: str | None = None,
        **kwargs,
    ) -> requests.Response | None:
        """Send a DELETE request.

        Args:
            endpoint: Relative endpoint path or absolute URL.
            base_url: Optional per-call base URL override.
            **kwargs: Extra keyword arguments passed to ``requests.request``.

        Returns:
            requests.Response | None: Response object returned by requests,
                or ``None`` when status code is 404.

        Raises:
            APINetworkError: If any ``requests.RequestException`` occurs.
        """
        return self._request("DELETE", endpoint, base_url=base_url, **kwargs)


class APIResultCode(IntEnum):
    """not used yet."""

    SUCCESS = 0
    ERROR = 1
    NOT_FOUND = 2
    UNAUTHORIZED = 3


class APIResult(BaseModel, Generic[T]):
    """not used yet."""

    "Result Pattern for API responses"

    status: APIResultCode = Field(..., description="The status of the API response")
    data: T = Field(..., description="The data returned by the API")
    message: str | None = None

    @property
    def is_success(self) -> bool:
        return self.status == APIResultCode.SUCCESS
