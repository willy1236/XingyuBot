import asyncio
import enum
import logging
import random
import subprocess
import time
import wave
from datetime import datetime
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import discord
import yt_dlp as youtube_dl

from starlib import BotEmbed
from starlib.exceptions import MusicCommandError, MusicPlayingError

log = logging.getLogger(__name__)

youtube_dl.utils.bug_reports_message = lambda before=";": ""

_BASE_YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "outtmpl": "%(extractor)s-%(id)s-%(title)s.%(ext)s",
    "restrictfilenames": True,
    "noplaylist": False,
    "nocheckcertificate": True,
    "ignoreerrors": False,
    "logtostderr": False,
    "quiet": True,
    "no_warnings": True,
    "default_search": "auto",
    "source_address": "0.0.0.0",
    "extractor_retries": 3,
    "playlistend": 200,
    "socket_timeout": 15,
    "http_headers": {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    },
}

ytdl_format_options = {**_BASE_YTDL_OPTIONS}
ytdl_bilibili_options = {
    **_BASE_YTDL_OPTIONS,
    "http_headers": {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
        "Referer": "https://www.bilibili.com",
        "Origin": "https://www.bilibili.com",
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    },
}

ffmpeg_options = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)
ytdl_bilibili = youtube_dl.YoutubeDL(ytdl_bilibili_options)


class SongSource(enum.IntEnum):
    Youtube_or_other = 1
    Spotify = 2


def _pick_extractor(url: str) -> youtube_dl.YoutubeDL:
    return ytdl_bilibili if "bilibili.com" in url or "b23.tv" in url else ytdl


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
        source_path: str,
        title: str,
        requester: discord.Member = None,
        song_from=None,
        headers: dict | None = None,
        duration: int | None = None,
    ):
        self.url = url  # webpage_url — 用來顯示及重新擷取
        self.source_path = source_path  # 最後一次取到的串流 URL（快取）
        self.title = title
        self.requester = requester
        self.song_from = song_from if song_from is not None else SongSource.Youtube_or_other
        self.headers = headers or {}
        self.duration = duration

    async def _fetch_fresh_stream(self) -> tuple[str | None, dict]:
        """
        播放前重新向 yt-dlp 取得最新串流 URL，避免 signed URL 過期導致長音樂中斷。
        若重新擷取失敗則退回快取的 source_path。
        """
        loop = asyncio.get_event_loop()
        extractor = _pick_extractor(self.url)
        try:
            info = await loop.run_in_executor(None, lambda: extractor.extract_info(self.url, download=False))
            if info:
                source_path, headers = _extract_source_from_info(info)
                if source_path:
                    return source_path, headers
        except Exception:
            log.warning("串流 URL 重新擷取失敗，退回快取網址", extra={"url": self.url})
        return self.source_path, self.headers

    async def get_source(self, volume: float = 0.5) -> discord.PCMVolumeTransformer:
        source_path, headers = await self._fetch_fresh_stream()
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
    async def from_url(
        cls,
        url: str,
        *,
        loop: asyncio.AbstractEventLoop = None,
        requester: discord.Member = None,
        song_from=None,
    ) -> list["Song"]:
        loop = loop or asyncio.get_event_loop()
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        if qs.get("list", [""])[0].startswith("RD"):
            qs.pop("list", None)
            qs.pop("start_radio", None)
            url = urlunparse(parsed._replace(query=urlencode({k: v[0] for k, v in qs.items()})))

        extractor = _pick_extractor(url)
        lst: list["Song"] = []

        results = None
        for attempt in range(3):
            results = await loop.run_in_executor(None, lambda: extractor.extract_info(url, download=False))
            if results is not None:
                break
            if attempt < 2:
                await asyncio.sleep(2**attempt)

        if not results:
            return lst

        entries = results["entries"] if "entries" in results else [results]

        for song_datas in entries:
            if not song_datas:
                continue

            title = song_datas.get("title")
            display_url = song_datas.get("webpage_url") or song_datas.get("original_url") or url
            source_path, headers = _extract_source_from_info(song_datas)
            duration = song_datas.get("duration")

            if not source_path:
                continue

            lst.append(
                cls(
                    display_url,
                    source_path,
                    title or display_url,
                    requester=requester,
                    song_from=song_from,
                    headers=headers,
                    duration=duration,
                )
            )

        return lst


class MusicPlayer:
    if TYPE_CHECKING:
        vc: discord.VoiceClient
        channel: discord.interactions.InteractionChannel
        loop: asyncio.AbstractEventLoop
        guildid: str
        playlist: list[Song]
        songloop: bool
        volume: float
        nowplaying: Song | None
        skip_voters: list[int]
        play_lock: asyncio.Lock
        play_started_at: float | None
        paused_at: float | None
        paused_total: float

    def __init__(self, vc: discord.VoiceClient, ctx: discord.ApplicationContext, loop):
        self.vc = vc
        self.channel = ctx.channel
        self.loop = loop
        self.guildid = str(ctx.guild.id)
        self.playlist: list[Song] = []
        self.songloop = False
        self.volume = 0.75
        self.nowplaying: Song | None = None
        self.skip_voters: list[int] = []
        self.play_lock = asyncio.Lock()
        self.play_started_at: float | None = None
        self.paused_at: float | None = None
        self.paused_total = 0.0

    async def play_next(self):
        async with self.play_lock:
            if self.vc.is_playing() or self.vc.is_paused():
                return

            log.debug("Music play_next", extra={"guild_id": self.guildid})
            song = self.start_first_song()
            try:
                source = await song.get_source(self.volume)
                embed = BotEmbed.simple(
                    title="現在播放",
                    description=f"[{song.title}]({song.url}) [{song.requester.mention}/{format_seconds(song.duration)}]",
                )
                await self.channel.send(embed=embed, silent=True)
                self.play_started_at = time.monotonic()
                self.paused_at = None
                self.paused_total = 0.0
                self.vc.play(source, after=self.after)
            except Exception as e:
                raise MusicPlayingError(str(e)) from e

    def after(self, error):
        log.debug("Music after", extra={"guild_id": self.guildid})
        if error:
            log.error("Music 播放後回呼錯誤", extra={"guild_id": self.guildid, "error": str(error)})
        time.sleep(1)
        if self.playlist or self.songloop:
            asyncio.run_coroutine_threadsafe(self.play_next(), self.loop)
        else:
            asyncio.run_coroutine_threadsafe(self.wait_to_leave(), self.loop)

    async def wait_to_leave(self, wait_for: int = 15):
        self.nowplaying = None
        self.play_started_at = None
        self.paused_at = None
        self.paused_total = 0.0
        await asyncio.sleep(wait_for)
        if not self.vc.is_playing() and not self.nowplaying:
            await self.stop()

    def skip_song(self, skip_voter: discord.Member) -> str:
        if self.nowplaying.requester == skip_voter:
            self.vc.stop()
            return f"已跳過歌曲：{self.nowplaying.title}"

        if skip_voter.id not in self.skip_voters:
            self.skip_voters.append(skip_voter.id)
        else:
            return "你已投票跳過歌曲"

        threshold = int(len(self.vc.channel.members) / 3) + 1
        if len(self.skip_voters) >= threshold:
            self.vc.stop()
            return f"已達投票人數，跳過歌曲：{self.nowplaying.title}"
        return f"已成功投票，目前票數：{len(self.skip_voters)}/{threshold}"

    async def stop(self):
        await self.vc.disconnect()
        self.playlist.clear()
        self.play_started_at = None
        self.paused_at = None
        self.paused_total = 0.0
        del guild_playing[self.guildid]
        log.debug("Music stop", extra={"guild_id": self.guildid})
        await self.channel.send("歌曲播放完畢 掰掰~")

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

    def start_first_song(self) -> Song:
        if not self.songloop:
            self.nowplaying = self.playlist.pop(0)
        self.skip_voters = []
        assert self.nowplaying is not None, "nowplaying 不應為 None"
        return self.nowplaying

    def get_full_playlist(self) -> list[Song]:
        return self.playlist

    def shuffle(self):
        random.shuffle(self.playlist)


guild_playing: dict[str, MusicPlayer] = {}


def get_player(guildid: str) -> MusicPlayer | None:
    return guild_playing.get(str(guildid))


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


def convert_audio(input_file: str, output_file: str):
    subprocess.run(
        ["ffmpeg", "-i", input_file, "-ar", "16000", "-ac", "1", "-y", output_file],
        check=False,
    )


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
