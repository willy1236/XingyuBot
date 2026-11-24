"""Twitch bot 的 Helix client，補齊 twitchAPI 的執法錯誤判定。"""

from collections.abc import AsyncGenerator
from urllib.parse import urlsplit

from aiohttp import ClientResponse, ClientResponseError, ClientSession
from twitchAPI.object.api import BlockedTerm
from twitchAPI.twitch import Twitch
from twitchAPI.type import AuthScope, AuthType, ForbiddenError, TwitchAPIException, UnauthorizedException


class TwitchStatusError(TwitchAPIException):
    """Helix 回傳非 2xx，保留狀態碼讓呼叫端判斷。"""

    def __init__(self, method: str, endpoint: str, status: int):
        super().__init__(f"Twitch {method} {endpoint} failed: HTTP {status}")
        self.status = status


class BotTwitch(Twitch):
    async def get_blocked_terms(
        self, broadcaster_id: str, moderator_id: str, after: str | None = None, first: int | None = None
    ) -> AsyncGenerator[BlockedTerm]:
        """同 SDK，但 scope 只要 read 或 manage 其一：Helix 兩者都接受，SDK 4.5.0 硬寫要 read。"""
        if first is not None and not 1 <= first <= 100:
            raise ValueError("first must be between 1 and 100")
        param = {"broadcaster_id": broadcaster_id, "moderator_id": moderator_id, "first": first, "after": after}
        scopes = [[AuthScope.MODERATOR_READ_BLOCKED_TERMS, AuthScope.MODERATOR_MANAGE_BLOCKED_TERMS]]
        async for term in self._build_generator(
            "GET", "moderation/blocked_terms", param, AuthType.USER, scopes, BlockedTerm
        ):
            yield term

    async def _check_request_return(
        self,
        session: ClientSession,
        response: ClientResponse,
        method: str,
        url: str,
        auth_type: AuthType,
        required_scope: list[AuthScope | list[AuthScope]],
        data: dict | None = None,
        retries: int = 1,
    ) -> ClientResponse:
        endpoint = urlsplit(url).path.removeprefix("/helix/")
        delete = method == "DELETE" and endpoint == "moderation/chat"
        strict = (
            endpoint == "moderation/blocked_terms"
            or (method == "DELETE" and endpoint == "moderation/bans")
            or (
                method == "GET"
                and endpoint in {"users", "streams", "search/categories", "channels", "moderation/banned"}
            )
            or (method == "PATCH" and endpoint == "channels")
        )
        if strict and not 200 <= response.status < 300 and response.status not in (401, 503):
            raise TwitchStatusError(method, endpoint, response.status)
        enforcing = delete or (method == "POST" and endpoint == "moderation/bans")
        if enforcing and not 200 <= response.status < 300:
            if response.status == 403:
                raise ForbiddenError(f"Twitch {method} {endpoint} failed: HTTP 403")
            if response.status not in (400, 401, 404, 500, 503):
                # SDK 4.5.0 的 429 只會等待重設，刪除方法最後仍會當成成功。
                raise TwitchAPIException(f"Twitch {method} {endpoint} failed: HTTP {response.status}")

        try:
            checked = await super()._check_request_return(
                session, response, method, url, auth_type, required_scope, data, retries
            )
        except (AttributeError, ClientResponseError, ValueError) as exc:
            if enforcing and response.status == 401:
                # 401 的刷新仍由 SDK 執行。若拒絕回應不是 JSON 物件，保留授權錯誤型別。
                raise UnauthorizedException("Twitch authorization failed: HTTP 401") from exc
            raise
        if strict and not 200 <= checked.status < 300:
            raise TwitchStatusError(method, endpoint, checked.status)
        return checked
