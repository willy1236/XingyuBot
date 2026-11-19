"""bot 發言的模板變數與頻道 AutoMod 檢查。web 端（儲存模板時）與 Twitch bot（發言前）共用。

AutoMod 用 Twitch 的 Check AutoMod Status（實況主 token，scope `moderation:read`）。
它的速率限制以頻道計，一般帳號每分鐘 5 次，所以 web 端在儲存模板時檢查，bot 只在內容帶觀眾輸入時才檢查。
"""

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable, Mapping
from typing import Literal

import httpx

from starlib.database import APIType, sqldb
from starlib.twitch_tokens import BROADCASTER_CLIENT_SEQ, TokenInvalid, broadcaster_token

log = logging.getLogger(__name__)

HELIX_AUTOMOD_STATUS = "https://api.twitch.tv/helix/moderation/enforcements/status"
REQUEST_TIMEOUT = 5.0

type TemplateCheck = Literal["ok", "blocked", "unavailable"]
#: 取得實況主的 (access token, client id)；拿不到可用 token 時回 TokenInvalid
type CredentialsGetter = Callable[[int], Awaitable[tuple[str, str] | TokenInvalid]]

_VARIABLE = re.compile(r"\{(\w+)\}")

#: 內容會帶入觀眾輸入的變數：含這些的訊息發言前要檢查 AutoMod
VIEWER_INPUT_VARIABLES = frozenset({"touser", "args"})

#: 檢查模板時代入的中性文字，只檢查實況主自己寫的部分
PLACEHOLDERS: Mapping[str, str] = {
    "user": "觀眾",
    "touser": "觀眾",
    "args": "內容",
    "count": "1",
    "channel": "頻道",
    "uptime": "1 小時",
    "game": "遊戲",
    "title": "標題",
    "months": "3",
    "amount": "5",
    "viewers": "10",
}


def substitute(template: str, values: Mapping[str, str]) -> str:
    """把 `{名稱}` 換成 values 裡的文字；不認得的變數原樣保留。代入的文字不會再展開一次。"""
    return _VARIABLE.sub(lambda m: values.get(m.group(1), m.group(0)), template)


def variables_used(template: str) -> set[str]:
    """模板裡用到的變數名稱（含不認得的）。"""
    return set(_VARIABLE.findall(template))


def uses_viewer_input(template: str) -> bool:
    """模板含 `{touser}` 或 `{args}`，內容會帶入觀眾輸入。"""
    return not VIEWER_INPUT_VARIABLES.isdisjoint(variables_used(template))


_client_id: str | None = None


def broadcaster_client_id_blocking() -> str:
    """實況主授權用的 Twitch 應用程式 client id（OAuth client #3）。要在 worker thread 上呼叫，查到後快取。"""
    global _client_id
    if _client_id is None:
        try:
            _client_id = sqldb.get_oauth_client(APIType.Twitch, BROADCASTER_CLIENT_SEQ).client_id
        finally:
            sqldb.release_session()
    return _client_id


async def default_credentials(twitch_id: int) -> tuple[str, str] | TokenInvalid:
    """Twitch bot 用：經 asyncio 預設 executor 取 token 與 client id。web 端用 `twitch_control` 的版本。"""
    token = await broadcaster_token(twitch_id)
    if isinstance(token, TokenInvalid):
        return token
    return token, await asyncio.to_thread(broadcaster_client_id_blocking)


async def check_text(
    twitch_id: int, text: str, *, get_credentials: CredentialsGetter = default_credentials
) -> TemplateCheck:
    """用頻道的 AutoMod 設定檢查一段文字。ok 可以發、blocked 會被擋；拿不到 token、超出速率限制或 Twitch 出錯回 unavailable。不 raise。"""
    try:
        credentials = await get_credentials(twitch_id)
        if isinstance(credentials, TokenInvalid):
            return "unavailable"
        access_token, client_id = credentials
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.post(
                HELIX_AUTOMOD_STATUS,
                params={"broadcaster_id": str(twitch_id)},
                headers={"Authorization": f"Bearer {access_token}", "Client-Id": client_id},
                json={"data": [{"msg_id": "1", "msg_text": text}]},
            )
        if response.status_code != 200:
            log.warning("Check AutoMod Status 失敗：%s %s", response.status_code, response.text)
            return "unavailable"
        entries = response.json().get("data", [])
        if not entries:
            return "unavailable"
        return "ok" if entries[0].get("is_permitted") else "blocked"
    except Exception:
        log.warning("Check AutoMod Status 出錯", exc_info=True)
        return "unavailable"


async def check_template(
    twitch_id: int, template: str, *, get_credentials: CredentialsGetter = default_credentials
) -> TemplateCheck:
    """檢查實況主寫的模板會不會被頻道 AutoMod 擋下：變數先換成中性文字，只檢查實況主寫的部分。

    web 端的儲存端點要用 `twitch_control.check_template`，它帶入後台專屬的 DB executor。
    """
    return await check_text(twitch_id, substitute(template, PLACEHOLDERS), get_credentials=get_credentials)
