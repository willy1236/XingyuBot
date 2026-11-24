"""Twitch bot 的 Helix client，補齊 twitchAPI 的執法錯誤判定。"""

from urllib.parse import urlsplit

from aiohttp import ClientResponse, ClientResponseError, ClientSession
from twitchAPI.twitch import Twitch
from twitchAPI.type import AuthScope, AuthType, TwitchAPIException, UnauthorizedException


class BotTwitch(Twitch):
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
        endpoint = "/".join(urlsplit(url).path.rsplit("/", 2)[-2:])
        delete = method == "DELETE" and endpoint == "moderation/chat"
        enforcing = delete or (method == "POST" and endpoint == "moderation/bans")
        if enforcing and not 200 <= response.status < 300:
            # delete_chat_message 會把 403 轉為 ForbiddenError；其餘已知狀態交由 SDK 處理。
            if delete and response.status == 403:
                return response
            if response.status not in (400, 401, 404, 500, 503):
                # SDK 4.5.0 的 429 只會等待重設，刪除方法最後仍會當成成功。
                raise TwitchAPIException(f"Twitch {method} {endpoint} failed: HTTP {response.status}")

        try:
            return await super()._check_request_return(
                session, response, method, url, auth_type, required_scope, data, retries
            )
        except (AttributeError, ClientResponseError, ValueError) as exc:
            if enforcing and response.status == 401:
                # 401 的刷新仍由 SDK 執行。若拒絕回應不是 JSON 物件，保留授權錯誤型別。
                raise UnauthorizedException("Twitch authorization failed: HTTP 401") from exc
            raise
