import asyncio
import logging
import socket
import threading

from sqlalchemy.exc import NoResultFound
from twitchAPI.chat import Chat
from twitchAPI.eventsub.webhook import EventSubWebhook
from twitchAPI.helper import first
from twitchAPI.oauth import UserAuthenticator
from twitchAPI.type import (
    AuthScope,
    ChatEvent,
    InvalidTokenException,
    MissingScopeException,
    TwitchAPIException,
)

from sentry_bootstrap import capture_exception_safe, capture_message_safe
from starlib import BaseThread
from starlib.database import APIType, OAuthToken, sqldb
from starServer.twitch_bot import (
    blocked_terms,
    channels,
    commands,
    events,
    moderation,
    speech,
    state,
    stream_info,
    timers,
    viewers,
)
from starServer.twitch_bot.helix import BotTwitch as Twitch

log = logging.getLogger(__name__)

USER_SCOPE = [
    AuthScope.BITS_READ,
    AuthScope.CHANNEL_BOT,
    AuthScope.CHANNEL_MODERATE,
    AuthScope.CHANNEL_MANAGE_MODERATORS,
    AuthScope.CHANNEL_MANAGE_POLLS,
    AuthScope.CHANNEL_MANAGE_PREDICTIONS,
    AuthScope.CHANNEL_MANAGE_RAIDS,
    AuthScope.CHANNEL_MANAGE_REDEMPTIONS,
    AuthScope.CHANNEL_READ_GOALS,
    AuthScope.CHANNEL_READ_POLLS,
    AuthScope.CHANNEL_READ_PREDICTIONS,
    AuthScope.CHANNEL_READ_REDEMPTIONS,
    AuthScope.CHANNEL_READ_VIPS,
    AuthScope.CHAT_READ,
    AuthScope.CHAT_EDIT,
    AuthScope.MODERATION_READ,
    AuthScope.MODERATOR_MANAGE_BANNED_USERS,
    AuthScope.MODERATOR_MANAGE_BLOCKED_TERMS,
    AuthScope.MODERATOR_MANAGE_CHAT_MESSAGES,
    AuthScope.MODERATOR_MANAGE_CHAT_SETTINGS,
    AuthScope.MODERATOR_READ_CHATTERS,
    AuthScope.MODERATOR_READ_FOLLOWERS,
    AuthScope.USER_BOT,
    AuthScope.USER_EDIT_FOLLOWS,
    AuthScope.USER_MANAGE_BLOCKED_USERS,
    AuthScope.USER_MANAGE_WHISPERS,
    AuthScope.USER_READ_CHAT,
    AuthScope.USER_READ_EMAIL,
    AuthScope.USER_READ_MODERATED_CHANNELS,
    AuthScope.USER_READ_SUBSCRIPTIONS,
    AuthScope.USER_WRITE_CHAT,
    AuthScope.WHISPERS_READ,
    AuthScope.WHISPERS_EDIT,
]


async def _wait_for_chat_loop(timeout: float = 30) -> None:
    """等 Chat 的 READY handler 記下它的 event loop；之後的 RPC 與 join_room、leave_room 都要在那個 loop 上執行。"""
    async with asyncio.timeout(timeout):
        while not hasattr(state, "loop"):
            await asyncio.sleep(0.1)


def _serve_and_sync() -> None:
    """EventSub 就緒後開放 web 的 RPC，並在 Chat 的 loop 上把所有頻道依資料庫現況同步一次。

    啟動時的 EventSub 訂閱也走 sync，和 web 的 sync 共用同一套每頻道的鎖，不會重複訂閱同一個事件；
    註冊之後再重讀資料庫，載入設定到註冊之間才被啟用或停用的頻道不會漏掉。同步在背景進行，不擋啟動。
    """
    channels.register()
    asyncio.run_coroutine_threadsafe(channels.sync_all(), state.loop)


async def run():
    state.load_join_channels()
    app_config = sqldb.get_oauth_client(APIType.Twitch, 2)
    APP_ID = app_config.client_id
    APP_SECRET = app_config.client_secret

    # validate_data = await validate_token(token)
    # if validate_data.get("client_id") != APP_ID:
    #     token, refresh_token = await refresh_access_token(refresh_token, APP_ID, APP_SECRET)
    #     jtoken['token'] = token
    #     jtoken['refresh'] = refresh_token

    # set up twitch api instance and add user authentication with some scopes
    twitch = state.twitch = await Twitch(APP_ID, APP_SECRET)
    try:
        app_token = sqldb.get_bot_oauth_token(APIType.Twitch, 2)
        await twitch.set_user_authentication(app_token.access_token, USER_SCOPE, app_token.refresh_token)
    except InvalidTokenException, MissingScopeException, NoResultFound:
        log.exception("Twitch token invalid or missing, re-authenticating")
        auth = UserAuthenticator(twitch, USER_SCOPE)
        token, refresh_token = await auth.authenticate()  # type: ignore
        await twitch.set_user_authentication(token, USER_SCOPE, refresh_token)
        me = await first(twitch.get_users())
        sqldb.merge(
            OAuthToken(
                user_id=me.id,
                client_credential_id=app_config.credential_id,
                access_token=token,
                refresh_token=refresh_token,
                scope=twitch.get_user_auth_scope(),
            )
        )
    # 這條 thread 之後一直跑 event loop，不釋放的話讀過的表會被 idle in transaction 的連線鎖住
    sqldb.release_session()

    # 使用自帶的函式處理token
    # helper = UserAuthenticationStorageHelper(twitch, USER_SCOPE)
    # await helper.bind()

    me = await first(twitch.get_users())
    state.bot_user_id = me.id
    try:
        users = [user async for user in twitch.get_users(user_ids=state.TARGET_CHANNEL_IDS)]
    except TwitchAPIException as exc:
        log.warning("啟動時無法批次查詢 Twitch 頻道，交由頻道同步逐一查詢：%s", exc)
    else:
        channels.rooms.update({int(user.id): user.login for user in users})

    # create chat instance
    chat = state.chat = await Chat(twitch)

    # register the handlers for the events you want
    chat.register_event(ChatEvent.READY, channels.on_ready)
    chat.register_event(ChatEvent.READY, viewers.on_ready)
    chat.register_event(ChatEvent.READY, moderation.on_ready)
    chat.register_event(ChatEvent.READY, blocked_terms.on_ready)
    chat.register_event(ChatEvent.READY, speech.on_ready)
    chat.register_event(ChatEvent.MESSAGE, commands.on_message)
    chat.register_event(ChatEvent.SUB, events.on_sub)
    chat.register_event(ChatEvent.JOINED, events.on_bot_joined)
    chat.register_event(ChatEvent.LEFT, events.on_bot_leaved)
    chat.register_event(ChatEvent.NOTICE, events.on_server_notice)
    chat.register_event(ChatEvent.WHISPER, events.on_whisper)
    chat.register_event(ChatEvent.RAID, events.on_raid)

    # chat.register_command_middleware(ChannelRestriction(allowed_channel=[]))
    chat.register_command("add_cmd", commands.add_chat_command)
    chat.register_command("edit_cmd", commands.edit_chat_command)
    chat.register_command("remove_cmd", commands.remove_chat_command)
    chat.register_command("list_cmd", commands.list_chat_command)
    chat.register_command("regular", viewers.regular_command)
    chat.register_command("permit", moderation.permit)
    moderation.register(asyncio.get_running_loop())
    blocked_terms.register(asyncio.get_running_loop())
    chat.register_command("title", stream_info.title)
    chat.register_command("game", stream_info.game)
    chat.register_command("uptime", stream_info.uptime)

    await viewers.load_regulars()
    chat.start()
    await asyncio.sleep(5)
    await _wait_for_chat_loop()
    timers.start(chat)
    commands.start()
    events.start()

    eventsub = EventSubWebhook(app_config.callback_uri, 14001, twitch)
    # unsubscribe from all old events that might still be there
    # this will ensure we have a clean slate
    await eventsub.unsubscribe_all()
    # start the eventsub client
    eventsub.start()
    await asyncio.sleep(3)
    state.eventsub = eventsub
    _serve_and_sync()

    return chat, twitch, eventsub


TWITCH_CHAT_HOST = "irc-ws.chat.twitch.tv"


def _can_reach(host: str, port: int) -> bool:
    try:
        socket.create_connection((host, port), timeout=5).close()
    except OSError:
        return False
    return True


async def _stop_eventsub(eventsub: EventSubWebhook) -> None:
    """取消訂閱並讓 webhook 的 hook thread 結束。

    不用 `EventSubWebhook.stop()`：它在呼叫端的 loop 上 shutdown aiohttp runner，但 runner 屬於 hook thread 自己的 loop，
    還有連線時會拋 `attached to a different loop`。呼叫後 process 就結束，runner 的 socket 由 OS 收回。
    """
    if eventsub.unsubscribe_on_stop:
        await eventsub.unsubscribe_all_known()
    # hook thread 的 _keep_loop_alive 看到 _closing 就結束
    eventsub._closing = True


class TwitchBotThread(BaseThread):
    def __init__(self):
        super().__init__(name="TwitchBotThread")
        self.chat: Chat = None
        self.twitch: Twitch = None
        self.eventsub: EventSubWebhook = None
        # run() 初始化完成、進入 _watch_chat 之前 set；呼叫端等它之後才開始消費事件
        self.ready = threading.Event()
        # 異常結束（放棄重連、未捕捉例外）時為 True；此時 thread 不做 cleanup，由呼叫端限時清理後以非 0 結束
        self.abnormal = False
        self._cleanup_lock = threading.Lock()

    def run(self):
        try:
            self.chat, self.twitch, self.eventsub = asyncio.run(run())
            self.ready.set()
            self._watch_chat()
        except Exception as exc:
            capture_exception_safe(exc, tags={"service": "twitch", "source": "thread_run"})
            log.error("TwitchBotThread crashed", exc_info=exc)
            self.abnormal = True
            return
        if not self.abnormal:
            asyncio.run(self.cleanup())

    _CHAT_CHECK_INTERVAL = 60
    # twitchAPI 自己的重連 backoff 合計約 255 秒，斷線超過這個時間才視為它已放棄
    _CHAT_DEAD_CHECKS = 5
    _CHAT_START_TIMEOUT = 300

    def _watch_chat(self):
        """等待停止訊號；期間若聊天室斷線且 twitchAPI 已放棄重連，就重啟 chat。"""
        disconnected_checks = 0
        while not self._stop_event.wait(self._CHAT_CHECK_INTERVAL):
            if self.chat.is_connected():
                disconnected_checks = 0
                continue
            disconnected_checks += 1
            if disconnected_checks < self._CHAT_DEAD_CHECKS:
                continue
            if not _can_reach(TWITCH_CHAT_HOST, 443):
                # 網路還沒恢復，重啟只會讓 chat.start() 卡在連線重試
                continue
            log.warning("Twitch chat 已斷線 %d 秒，重啟 chat", disconnected_checks * self._CHAT_CHECK_INTERVAL)
            try:
                self.chat.stop()
            except Exception as exc:
                capture_exception_safe(exc, tags={"service": "twitch", "source": "watch_chat_stop"})
                log.error("Twitch chat 停止失敗，放棄自動重啟", exc_info=exc)
                self.abnormal = True
                return
            # twitchAPI 只在 _callback_loop 為 None 時才設成新的 socket loop；不清掉的話，重啟後所有 handler
            # （READY、訊息、指令）都排在已停止的舊 loop 上，bot 連得上卻完全不回應
            self.chat._callback_loop = None
            # chat.start() 在連線失敗時會無限等待 startup，放到另一條 thread 並設上限
            starter = threading.Thread(target=self.chat.start, name="TwitchChatRestart", daemon=True)
            starter.start()
            starter.join(self._CHAT_START_TIMEOUT)
            if starter.is_alive():
                message = "Twitch chat 重啟逾時，放棄自動重啟"
                log.warning(message)
                capture_message_safe(message, level="error", tags={"service": "twitch", "source": "watch_chat_restart"})
                self.abnormal = True
                return
            disconnected_checks = 0

    async def cleanup(self):
        """安全地清理所有資源。

        thread 自己收尾超過 twitch_main 的等待上限時，twitch_main 會再呼叫一次；只執行第一次，避免兩邊同時取消訂閱、重複停止 chat。
        """
        if not self._cleanup_lock.acquire(blocking=False):
            return
        for module in (timers, commands, events):
            try:
                module.stop()
            except Exception as e:
                capture_exception_safe(e, tags={"service": "twitch", "source": f"cleanup_{module.__name__}"})
                log.warning("Error stopping %s: %s", module.__name__, e)

        try:
            if self.eventsub:
                await _stop_eventsub(self.eventsub)
        except Exception as e:
            capture_exception_safe(e, tags={"service": "twitch", "source": "cleanup_eventsub"})
            log.warning("Error stopping eventsub: %s", e)

        try:
            if self.twitch:
                await self.twitch.close()
        except Exception as e:
            capture_exception_safe(e, tags={"service": "twitch", "source": "cleanup_twitch"})
            log.warning("Error closing twitch: %s", e)

        try:
            if self.chat:
                self.chat.stop()
        except Exception as e:
            capture_exception_safe(e, tags={"service": "twitch", "source": "cleanup_chat"})
            log.warning("Error stopping chat: %s", e)


if __name__ == "__main__":
    chat, twitch, eventsub_webhook = asyncio.run(run())
    chat: Chat
    twitch: Twitch
    eventsub_webhook: EventSubWebhook

    try:
        input("press ENTER to stop\n")
    finally:
        chat.stop()
        asyncio.run(twitch.close())
