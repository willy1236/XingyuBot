import asyncio
import concurrent.futures
import enum
import logging
import random
import time
import wave
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import discord
import yt_dlp as youtube_dl
from discord.voice.client import VoiceClient

from starlib import BotEmbed
from starlib.exceptions import MusicPlayingError

log = logging.getLogger(__name__)

youtube_dl.utils.bug_reports_message = lambda before=";": ""


def _patched_remove_ssrc(self: VoiceClient, *, user_id: int) -> None:
    # py-cord 2.8.1 bug：未錄音時 _reader 是 MISSING，原版直接存取 speaking_timer 會拋 AttributeError，
    # 使語音 websocket 收訊迴圈靜默中止，之後 DAVE 金鑰無法更新，bot 送出的聲音全被丟棄。
    # 觸發條件：曾說過話的成員離開語音頻道。上游修正後即可移除。
    ssrc = self._id_to_ssrc.pop(user_id, None)
    if ssrc:
        if self._reader:
            self._reader.speaking_timer.drop_ssrc(ssrc)
        self._ssrc_to_id.pop(ssrc, None)


VoiceClient._remove_ssrc = _patched_remove_ssrc

_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"

_BASE_YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "outtmpl": "%(extractor)s-%(id)s-%(title)s.%(ext)s",
    "restrictfilenames": True,
    "noplaylist": False,
    "logtostderr": False,
    "quiet": True,
    "no_warnings": True,
    "default_search": "auto",
    "source_address": "0.0.0.0",
    "extractor_retries": 3,
    "socket_timeout": 15,
    "http_headers": {
        "User-Agent": _USER_AGENT,
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    },
}

_BILIBILI_HEADERS = {
    "User-Agent": _USER_AGENT,
    "Referer": "https://www.bilibili.com",
    "Origin": "https://www.bilibili.com",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
}

ffmpeg_options = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

# flat 擷取時 YouTube 以這些標題代表無法播放的影片
_UNAVAILABLE_TITLES = {"[Private video]", "[Deleted video]"}


def _ytdl_options(url: str, *, flat: bool, ignoreerrors: bool = False) -> dict:
    """
    :param flat: True 用於 /play 加入歌曲（歌單只取清單不解析串流）；False 用於播放前取單曲串流
    :param ignoreerrors: True 時歌單中單首失敗會被略過，而非整張失敗
    """
    opts = {**_BASE_YTDL_OPTIONS, "ignoreerrors": ignoreerrors}
    if "bilibili.com" in url or "b23.tv" in url:
        opts["http_headers"] = _BILIBILI_HEADERS
    if flat:
        opts["extract_flat"] = "in_playlist"
    else:
        opts["noplaylist"] = True
    return opts


def _extract_blocking(url: str, opts: dict) -> dict | None:
    # YoutubeDL 非 thread-safe，每次擷取各自建立實例
    with youtube_dl.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)


async def _extract(url: str, opts: dict) -> dict | None:
    return await asyncio.get_running_loop().run_in_executor(None, _extract_blocking, url, opts)


def _strip_radio_params(url: str) -> str:
    """YouTube Mix（list=RD*）是無限電台，去除電台參數只播單曲。"""
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    if qs.get("list", [""])[0].startswith("RD"):
        qs.pop("list", None)
        qs.pop("start_radio", None)
        return urlunparse(parsed._replace(query=urlencode({k: v[0] for k, v in qs.items()})))
    return url


def _extract_source_from_info(info: dict) -> tuple[str | None, dict]:
    """從 yt-dlp info_dict 中取出最佳音訊 URL 與 headers。"""
    source_path = info.get("url")
    headers = info.get("http_headers") or {}
    if not source_path:
        formats = info.get("requested_formats") or info.get("formats") or []
        audio_fmt = next(
            (f for f in formats if isinstance(f, dict) and f.get("acodec") not in (None, "none") and f.get("url")),
            None,
        ) or next(
            (f for f in formats if isinstance(f, dict) and f.get("url")),
            None,
        )
        if audio_fmt:
            source_path = audio_fmt.get("url")
            headers = audio_fmt.get("http_headers") or headers
    return source_path, headers


class Song:
    def __init__(
        self,
        url: str,
        source_path: str | None,
        title: str,
        requester: discord.Member = None,
        headers: dict | None = None,
        duration: int | None = None,
    ):
        self.url = url  # webpage_url — 用來顯示及重新擷取
        self.source_path = source_path  # 最後一次取到的串流 URL（快取）；歌單 flat 擷取時為 None
        self.title = title
        self.requester = requester
        self.headers = headers or {}
        self.duration = duration

    async def _fetch_fresh_stream(self) -> tuple[str | None, dict]:
        """
        播放前重新向 yt-dlp 取得最新串流 URL，避免 signed URL 過期導致長音樂中斷。
        若重新擷取失敗則退回快取的 source_path。
        """
        try:
            info = await _extract(self.url, _ytdl_options(self.url, flat=False))
            if info and "entries" in info:
                info = next((e for e in info["entries"] if e), None)
            if info:
                source_path, headers = _extract_source_from_info(info)
                if source_path:
                    return source_path, headers
        except Exception:
            log.warning("串流 URL 重新擷取失敗，退回快取網址", extra={"url": self.url})
        return self.source_path, self.headers

    async def get_source(self, volume: float = 0.5) -> discord.PCMVolumeTransformer:
        source_path, headers = await self._fetch_fresh_stream()
        if not source_path:
            raise MusicPlayingError(f"無法取得串流：{self.title}")
        # 更新快取，下次 fallback 用
        self.source_path = source_path
        self.headers = headers or {}

        before_options = ffmpeg_options["before_options"]
        if self.headers and source_path.startswith(("http://", "https://")):
            header_lines = "".join(f"{k}: {v}\r\n" for k, v in self.headers.items())
            header_lines = header_lines.replace('"', '\\"')
            before_options = f'{before_options} -headers "{header_lines}"'

        return discord.PCMVolumeTransformer(
            discord.FFmpegPCMAudio(
                source_path,
                before_options=before_options,
                options=ffmpeg_options["options"],
            ),
            volume,
        )

    @classmethod
    async def from_url(cls, url: str, *, requester: discord.Member = None) -> tuple[list["Song"], int]:
        """
        擷取網址中的歌曲。歌單只取清單（flat），串流在播放時才由 get_source 取得。

        :return: (歌曲清單, 因無法播放而略過的數量)
        """
        result = await cls.extract(url, requester=requester)
        return result.songs, result.skipped

    @classmethod
    async def extract(cls, url: str, *, requester: discord.Member = None) -> "ExtractResult":
        """同 from_url，另外帶出網址是否為歌單及其正規化網址與名稱。"""
        url = _strip_radio_params(url)
        results = await _extract(url, _ytdl_options(url, flat=True, ignoreerrors=True))
        if results is None:
            # ignoreerrors 會吞掉單曲失敗的原因，改用嚴格模式重抓讓 DownloadError 帶出錯誤訊息
            results = await _extract(url, _ytdl_options(url, flat=True))
        if not results:
            return ExtractResult([], 0)

        playlist_url = playlist_title = None
        if results.get("_type") == "playlist":
            playlist_url = results.get("webpage_url") or url
            playlist_title = results.get("title")

        entries = results["entries"] if "entries" in results else [results]
        songs: list[Song] = []
        skipped = 0

        for entry in entries:
            if not entry:
                skipped += 1
                continue

            if entry.get("_type") in ("url", "url_transparent"):
                # flat 項目：url 是影片頁面而非串流
                display_url = entry.get("url")
                source_path, headers = None, {}
                if not display_url or entry.get("title") in _UNAVAILABLE_TITLES:
                    skipped += 1
                    continue
            else:
                display_url = entry.get("webpage_url") or entry.get("original_url") or url
                source_path, headers = _extract_source_from_info(entry)
                if not source_path:
                    skipped += 1
                    continue

            songs.append(
                cls(
                    display_url,
                    source_path,
                    entry.get("title") or display_url,
                    requester=requester,
                    headers=headers,
                    duration=entry.get("duration"),
                )
            )

        return ExtractResult(songs, skipped, playlist_url, playlist_title)


@dataclass
class ExtractResult:
    songs: list[Song]
    skipped: int
    # 網址為歌單時的正規化網址與歌單名稱；單曲為 None
    playlist_url: str | None = None
    playlist_title: str | None = None


class LoopMode(enum.Enum):
    OFF = "off"
    SONG = "song"  # 重播目前歌曲
    QUEUE = "queue"  # 播完的歌放回歌單尾端


class MusicPlayer:
    if TYPE_CHECKING:
        vc: discord.VoiceClient
        channel: discord.interactions.InteractionChannel
        loop: asyncio.AbstractEventLoop
        guildid: str
        playlist: list[Song]
        loop_mode: LoopMode
        volume: float
        nowplaying: Song | None
        skip_voters: list[int]
        play_lock: asyncio.Lock
        play_started_at: float | None
        paused_at: float | None
        paused_total: float
        closing: bool

    # 播放不到此秒數即結束視為播放失敗，循環模式下連續失敗達上限就關閉循環避免洗版
    QUICK_FAIL_SECONDS = 3
    QUICK_FAIL_LIMIT = 3

    def __init__(self, vc: discord.VoiceClient, ctx: discord.ApplicationContext, loop):
        self.vc = vc
        self.channel = ctx.channel
        self.loop = loop
        self.guildid = str(ctx.guild.id)
        self.playlist: list[Song] = []
        self.loop_mode = LoopMode.OFF
        self.volume = 0.75
        self.nowplaying: Song | None = None
        self.skip_voters: list[int] = []
        self.play_lock = asyncio.Lock()
        self.play_started_at: float | None = None
        self.paused_at: float | None = None
        self.paused_total = 0.0
        self.closing = False
        self.after_delay = 1.0
        self.leave_delay = 15.0
        self._leave_task: asyncio.Task | None = None
        self._skip_requested = False
        self._quick_fail_count = 0

    async def _send(self, content: str | None = None, **kwargs):
        try:
            await self.channel.send(content, **kwargs)
        except discord.HTTPException:
            log.warning("音樂訊息發送失敗", extra={"guild_id": self.guildid})

    def _reset_timer(self):
        self.play_started_at = None
        self.paused_at = None
        self.paused_total = 0.0

    async def play_next(self):
        async with self.play_lock:
            if self.closing or self.vc.is_playing() or self.vc.is_paused():
                return
            self._cancel_leave()

            log.debug("Music play_next", extra={"guild_id": self.guildid})
            while True:
                song = self._next_song()
                if song is None:
                    self._start_leave_timer()
                    return

                try:
                    source = await song.get_source(self.volume)
                except Exception:
                    log.warning("歌曲無法播放，略過", extra={"guild_id": self.guildid, "url": song.url}, exc_info=True)
                    if self.loop_mode is LoopMode.SONG:
                        self.loop_mode = LoopMode.OFF
                        await self._send(f"無法播放 {song.title}，已關閉循環並略過")
                    else:
                        await self._send(f"略過無法播放的歌曲：{song.title}")
                    # 清掉 nowplaying：整張循環時不會把壞歌放回歌單
                    self.nowplaying = None
                    continue

                if self.closing:
                    source.cleanup()
                    return

                self._reset_timer()
                self.play_started_at = time.monotonic()
                try:
                    self.vc.play(source, after=self.after)
                except Exception as e:
                    raise MusicPlayingError(str(e)) from e

                embed = BotEmbed.simple(
                    title="現在播放",
                    description=f"[{song.title}]({song.url}) [{song.requester.mention}/{format_seconds(song.duration)}]",
                )
                await self._send(embed=embed, silent=True)
                return

    def _next_song(self) -> Song | None:
        """決定下一首：單首循環重播目前歌曲（跳過時除外）；整張循環先把目前歌曲放回歌單尾端再取下一首。"""
        skip_requested = self._skip_requested
        self._skip_requested = False
        self.skip_voters = []
        if self.loop_mode is LoopMode.SONG and self.nowplaying and not skip_requested:
            return self.nowplaying
        if self.loop_mode is LoopMode.QUEUE and self.nowplaying:
            self.playlist.append(self.nowplaying)
        self.nowplaying = self.playlist.pop(0) if self.playlist else None
        return self.nowplaying

    def after(self, error):
        """由語音執行緒呼叫。"""
        log.debug("Music after", extra={"guild_id": self.guildid})
        if error:
            log.error("Music 播放後回呼錯誤", extra={"guild_id": self.guildid, "error": str(error)})
        if self.closing:
            return

        if not self._skip_requested and self.get_elapsed_seconds() < self.QUICK_FAIL_SECONDS:
            self._quick_fail_count += 1
        else:
            self._quick_fail_count = 0

        time.sleep(self.after_delay)
        if self.closing:
            return
        self._schedule(self._advance())

    async def _advance(self):
        if self.loop_mode is not LoopMode.OFF and self._listener_count() == 0:
            # 循環模式不會自己播完，頻道沒人時繼續播只是浪費
            await self.close("語音頻道已經沒有人，停止循環播放 掰掰~")
            return
        if self.loop_mode is not LoopMode.OFF and self._quick_fail_count >= self.QUICK_FAIL_LIMIT:
            self.loop_mode = LoopMode.OFF
            self._quick_fail_count = 0
            await self._send("歌曲連續無法正常播放，已關閉循環")
        await self.play_next()

    def _schedule(self, coro):
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        future.add_done_callback(self._log_future_error)

    def _log_future_error(self, future: concurrent.futures.Future):
        if future.cancelled():
            return
        if exc := future.exception():
            log.error("Music 背景換歌失敗", extra={"guild_id": self.guildid}, exc_info=exc)

    def _start_leave_timer(self):
        self._cancel_leave()
        self._leave_task = asyncio.create_task(self.wait_to_leave())

    def _cancel_leave(self):
        if self._leave_task and self._leave_task is not asyncio.current_task():
            self._leave_task.cancel()
        self._leave_task = None

    async def wait_to_leave(self):
        self.nowplaying = None
        self._reset_timer()
        await asyncio.sleep(self.leave_delay)
        if self.closing or self.vc.is_playing() or self.vc.is_paused() or self.nowplaying:
            return
        self._leave_task = None
        await self.close("歌曲播放完畢 掰掰~")

    async def close(self, message: str | None = None):
        """播放器唯一的收尾出口：停止播放、斷線並移出 registry。"""
        if self.closing:
            return
        self.discard()
        try:
            await self.vc.disconnect(force=True)
        except Exception:
            log.warning("Music 斷線失敗", extra={"guild_id": self.guildid}, exc_info=True)
        log.debug("Music close", extra={"guild_id": self.guildid})
        if message:
            await self._send(message)

    def discard(self):
        """停用播放器（不斷線），讓殘留的回呼不再動作。"""
        self.closing = True
        self.playlist.clear()
        self.nowplaying = None
        self._reset_timer()
        self._cancel_leave()
        if guild_playing.get(self.guildid) is self:
            del guild_playing[self.guildid]

    def skip_song(self, skip_voter: discord.Member) -> str:
        if self.nowplaying.requester == skip_voter:
            self._skip_requested = True
            self.vc.stop()
            return f"已跳過歌曲：{self.nowplaying.title}"

        if skip_voter.id not in self.skip_voters:
            self.skip_voters.append(skip_voter.id)
        else:
            return "你已投票跳過歌曲"

        threshold = self._listener_count() // 3 + 1
        if len(self.skip_voters) >= threshold:
            self._skip_requested = True
            self.vc.stop()
            return f"已達投票人數，跳過歌曲：{self.nowplaying.title}"
        return f"已成功投票，目前票數：{len(self.skip_voters)}/{threshold}"

    def _listener_count(self) -> int:
        """語音頻道內的真人數量（不含 bot）。"""
        return sum(1 for member in self.vc.channel.members if not member.bot)

    def pause(self):
        if not self.vc.is_paused():
            self.vc.pause()
            self._on_paused()
        else:
            self.vc.resume()
            self._on_resumed()

    def _on_paused(self):
        if not self.paused_at:
            self.paused_at = time.monotonic()

    def _on_resumed(self):
        if self.paused_at:
            self.paused_total += time.monotonic() - self.paused_at
            self.paused_at = None

    def get_elapsed_seconds(self) -> int:
        if not self.play_started_at:
            return 0
        paused_total = self.paused_total
        if self.paused_at:
            paused_total += time.monotonic() - self.paused_at
        return max(0, int(time.monotonic() - self.play_started_at - paused_total))

    def add_song(self, song: "Song | list[Song]"):
        if isinstance(song, list):
            self.playlist.extend(song)
        else:
            self.playlist.append(song)

    def get_full_playlist(self) -> list[Song]:
        return self.playlist

    def shuffle(self):
        random.shuffle(self.playlist)


guild_playing: dict[str, MusicPlayer] = {}


def get_player(guildid: str) -> MusicPlayer | None:
    return guild_playing.get(str(guildid))


def get_or_create_player(vc: discord.VoiceClient, ctx: discord.ApplicationContext, loop) -> MusicPlayer:
    """取得伺服器的播放器；既有播放器綁的是舊連線（例如曾被踢出語音）時重建。"""
    guildid = str(ctx.guild.id)
    player = guild_playing.get(guildid)
    if player and (player.closing or player.vc is not vc):
        player.discard()
        player = None
    if not player:
        player = MusicPlayer(vc, ctx, loop)
        guild_playing[guildid] = player
    return player


def format_seconds(total_seconds: int | None) -> str:
    if total_seconds is None:
        return "--:--"
    total_seconds = int(total_seconds)
    minutes, seconds = divmod(max(total_seconds, 0), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02}:{seconds:02}"
    return f"{minutes:02}:{seconds:02}"


def format_progress_bar(current_seconds: int, total_seconds: int | None, width: int = 16) -> tuple[str, str]:
    if total_seconds is None:
        return f"[{'-' * width}]", f"{format_seconds(current_seconds)} / {format_seconds(None)}"
    total = max(int(total_seconds), 1)
    current = max(0, min(int(current_seconds), total))
    filled = int((current / total) * width)
    return f"[{'▅' * filled}{'-' * (width - filled)}]", f"{format_seconds(current)} / {format_seconds(total)}"


async def recording_done(sink: discord.sinks.WaveSink):
    now = datetime.now().strftime("%H%M%S")
    recorded_users = [f"<@{user_id}>" for user_id in sink.audio_data]
    await sink.vc.disconnect()
    files = [discord.File(audio.file, f"{user_id}_{now}.{sink.encoding}") for user_id, audio in sink.audio_data.items()]
    await sink.vc.channel.send(f"完成以下成員的錄音： {', '.join(recorded_users)}.", files=files)

    for user_id, audio in sink.audio_data.items():
        file_path = f"{user_id}_{now}.{sink.encoding}"
        with wave.open(file_path, "wb") as wav_file:
            wav_file.setnchannels(2)
            wav_file.setsampwidth(2)
            wav_file.setframerate(48000)
            wav_file.writeframes(audio.file.getvalue())
