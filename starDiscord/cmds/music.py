# type: ignore
import asyncio
import enum
import math
import random
import subprocess
import time
import wave
from datetime import datetime
from typing import TYPE_CHECKING

import discord
import yt_dlp as youtube_dl
from discord.commands import SlashCommandGroup
from discord.ext import commands, pages

from starlib import BotEmbed, Jsondb, log
from starlib.exceptions import *

from ..extension import Cog_Extension

# Suppress noise about console usage from errors
youtube_dl.utils.bug_reports_message = lambda before=";": ""

ytdl_format_options = {
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
}

ffmpeg_options = {"before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5", "options": "-vn"}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)
# model: Model = Model(vosk_model_path)

class SongSource(enum.IntEnum):
    Youtube_or_other = 1
    Spotify = 2

class Song():
    def __init__(self, url: str, source_path: str, title: str, requester: discord.Member = None, song_from=SongSource.Youtube_or_other, headers: dict | None = None, duration: int | None = None):
        self.url = url
        self.source_path = source_path
        self.title = title
        self.requester = requester
        self.song_from = song_from
        self.headers = headers or {}
        self.duration = duration

    async def get_source(self, volume=0.5):
        before_options = ffmpeg_options["before_options"]
        if self.headers and self.source_path.startswith(("http://", "https://")):
            header_lines = "".join(f"{k}: {v}\r\n" for k, v in self.headers.items())
            header_lines = header_lines.replace('"', '\\"')
            before_options = f'{before_options} -headers "{header_lines}"'

        source = discord.PCMVolumeTransformer(
            discord.FFmpegPCMAudio(
                self.source_path,
                before_options=before_options,
                options=ffmpeg_options["options"],
            ),
            volume,
        )
        return source

    @classmethod
    async def from_url(cls, url:str, *, loop:asyncio.AbstractEventLoop=None, requester:discord.Member=None, song_from=SongSource.Youtube_or_other):
        """
        Creates a list of Song objects from the given URL.

        Parameters:
        - url (str): The URL of the song or playlist.
        - loop (asyncio.AbstractEventLoop, optional): The event loop to use for asynchronous operations. Defaults to None.
        - stream (bool, optional): Whether to stream the song or download it. Defaults to False.
        - requester (discord.Member, optional): The member who requested the song. Defaults to None.
        - song_from (SongSource, optional): The source of the song. Defaults to SongSource.YOUTUBE_OR_OTHER.

        Returns:
        - list[Song]: A list of Song objects created from the URL.
        """
        loop = loop or asyncio.get_event_loop()
        results:dict | list[dict] = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))  # type: ignore
        lst:list["Song"] = []

        if  "entries" in results:
            # 處理歌單
            results = results["entries"]
        else:
            # 處理單首歌曲
            results = [results] # type: ignore

        for song_datas in results:
            if not song_datas:
                continue

            title = song_datas.get("title")
            display_url = song_datas.get("webpage_url") or song_datas.get("original_url") or url

            # 通用來源選流：先用已解出的 url，再退回 requested_formats/formats
            source_path = song_datas.get("url")
            headers = song_datas.get("http_headers")
            duration = song_datas.get("duration")
            if not source_path:
                formats = song_datas.get("requested_formats") or song_datas.get("formats") or []
                audio_format = next(
                    (fmt for fmt in formats if isinstance(fmt, dict) and fmt.get("acodec") and fmt.get("acodec") != "none" and fmt.get("url")),
                    None,
                )
                if not audio_format:
                    audio_format = next(
                        (fmt for fmt in formats if isinstance(fmt, dict) and fmt.get("url")),
                        None,
                    )

                source_path = audio_format.get("url") if audio_format else None
                if audio_format and not headers:
                    headers = audio_format.get("http_headers")
                if audio_format and not duration:
                    duration = audio_format.get("duration")

            if not source_path:
                continue

            lst.append(cls(display_url, source_path, title or display_url, requester=requester, song_from=song_from, headers=headers, duration=duration))

        if not lst:
            raise MusicCommandError("找不到可播放的音訊來源，請嘗試其他連結")

        return lst

class MusicPlayer():
    if TYPE_CHECKING:
        vc: discord.VoiceClient
        channel: discord.interactions.InteractionChannel
        loop: asyncio.AbstractEventLoop
        guildid: str
        playlist: list[Song]
        songloop: bool
        volume: float
        nowplaying: Song
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
        self.playlist = []
        self.songloop = False
        self.volume = 0.5
        self.nowplaying = None
        self.skip_voters = []
        self.play_lock = asyncio.Lock()
        self.play_started_at = None
        self.paused_at = None
        self.paused_total = 0.0

    async def play_next(self):
        """
        Plays the next song in the queue.

        This method retrieves the next song from the queue and plays it using the voice client.
        It also sends an embed message to the channel indicating the currently playing song.

        Raises:
            MusicPlayingError: If there is an error playing the next song.
        """
        async with self.play_lock:
            # 避免多個流程同時啟動下一首，造成 after 與 play_next 互相搶跑
            if self.vc.is_playing() or self.vc.is_paused():
                return

            log.debug(f"{self.guildid}: play_next")
            song = self.start_first_song()
            try:
                source = await song.get_source(self.volume)

                embed = BotEmbed.simple(title="現在播放", description=f"[{song.title}]({song.url}) [{song.requester.mention}/{format_seconds(song.duration)}]")
                await self.channel.send(embed=embed, silent=True)
                self.play_started_at = time.monotonic()
                self.paused_at = None
                self.paused_total = 0.0
                self.vc.play(source, after=self.after)
            except Exception as e:
                raise MusicPlayingError(str(e)) from e

    def after(self, error):
        """
        Callback function called after a song has finished playing.

        Args:
            error (Exception): The error that occurred during playback, if any.
        """
        log.debug(f"{self.guildid}: after")
        # self.play_completed()
        if error:
            log.error(f"{self.guildid}: 播放後回呼錯誤: {error}")
        time.sleep(1)
        if self.playlist or self.songloop:
            # 使用既有的bot loop
            asyncio.run_coroutine_threadsafe(self.play_next(), self.loop)
        else:
            asyncio.run_coroutine_threadsafe(self.wait_to_leave(), self.loop)

    async def wait_to_leave(self, wait_for=15):
        """
        Waits for a specified amount of time and stops the music if it is not playing.

        This method is used to wait for a certain amount of time before stopping the music playback
        if there is no audio being played in the voice channel.

        Parameters:
        - wait_for (int): The number of seconds to wait before stopping the music. Default is 15.

        Returns:
        - None
        """
        self.nowplaying = None
        self.play_started_at = None
        self.paused_at = None
        self.paused_total = 0.0
        await asyncio.sleep(wait_for)
        if not self.vc.is_playing() and not self.nowplaying:
            await self.stop()

    def skip_song(self, skip_voter: discord.Member):
        """
        Skips the currently playing song.

        Parameters:
            skip_voter (discord.Member): The member who initiated the skip.

        Returns:
            str: A message indicating the result of the skip operation.
        """
        if self.nowplaying.requester == skip_voter:
            self.vc.stop()
            return f"已跳過歌曲：{self.nowplaying.title}"
        else:
            if skip_voter.id not in self.skip_voters:
                self.skip_voters.append(skip_voter.id)
            else:
                return "你已投票跳過歌曲"

            if len(self.skip_voters) >= len(self.vc.channel.members) / 3:
                self.vc.stop()
                return f"已達投票人數，跳過歌曲：{self.nowplaying.title}"
            else:
                return f"已成功投票，目前票數：{len(self.skip_voters)}/{int(len(self.vc.channel.members) / 3) + 1}"

    async def stop(self):
        """
        Stops playing the current song and disconnects from the voice channel.

        This method stops the playback of the current song and removes the guild from the `guild_playing` dictionary.
        It also sends a message to the channel indicating that the song has finished playing.

        Parameters:
        - None

        Returns:
        - None
        """
        await self.vc.disconnect()
        self.playlist.clear()
        self.play_started_at = None
        self.paused_at = None
        self.paused_total = 0.0
        del guild_playing[self.guildid]
        await self.channel.send("歌曲播放完畢 掰掰~")

    def pause(self):
        """
        Pauses the currently playing song.

        This method pauses the playback of the current song and updates the paused_at timestamp.

        Parameters:
        - None

        Returns:
        - None
        """
        if not self.vc.is_paused():
            self.vc.pause()
            self.on_paused()
        else:
            self.vc.resume()
            self.on_resumed()

    def on_paused(self):
        if not self.paused_at:
            self.paused_at = time.monotonic()

    def on_resumed(self):
        if self.paused_at:
            self.paused_total += time.monotonic() - self.paused_at
            self.paused_at = None

    def get_elapsed_seconds(self) -> int:
        if not self.play_started_at:
            return 0

        paused_total = self.paused_total
        if self.paused_at:
            paused_total += time.monotonic() - self.paused_at

        elapsed = time.monotonic() - self.play_started_at - paused_total
        return max(0, int(elapsed))

    def add_song(self, song: Song | list[Song]):
        """
        Adds a song or a list of songs to the playlist.

        Parameters:
        - song (Song | list[Song]): The song or list of songs to be added to the playlist.

        Returns:
        - None
        """
        if isinstance(song, list):
            self.playlist.extend(song)
        else:
            self.playlist.append(song)

    def start_first_song(self) -> Song:
        """
        Starts playing the first song in the playlist.

        If the song loop is disabled, the first song is removed from the playlist and set as the currently playing song.
        The skip voter list is reset.

        Returns:
            The currently playing song.
        """
        if not self.songloop:
            self.nowplaying = self.playlist.pop(0)
        self.skip_voters = []
        return self.nowplaying

    def play_completed(self):
        """
        Stops the audio playback in the voice channel.
        """
        self.vc.stop()

    def get_full_playlist(self) -> list[Song]:
        """
        Returns the full playlist of songs.

        Returns:
            list[Song]: The full playlist of songs.
        """
        return self.playlist

    def shuffle(self):
        """
        Shuffles the playlist randomly.
        """
        random.shuffle(self.playlist)

guild_playing = {}
def get_player(guildid:str) -> MusicPlayer | None:
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
        return f"[{'-' * width}]", f"{format_seconds(current_seconds)} / {format_seconds(total)}"

    total = max(int(total_seconds), 1)
    current = max(0, min(current_seconds, total))
    filled = int((current / total) * width)
    progress_bar = f"[{'▅' * filled}{'-' * (width - filled)}]"
    progress_text = f"{format_seconds(current)} / {format_seconds(total)}"
    return progress_bar, progress_text


def convert_audio(input_file, output_file):
    command = ["ffmpeg", "-i", input_file, "-ar", "16000", "-ac", "1", "-y", output_file]
    subprocess.run(command, check=False)

async def recording_done(sink: discord.sinks.WaveSink):
    now = datetime.now().strftime("%H%M%S")
    recorded_users = [
        f"<@{user_id}>"
        for user_id, audio in sink.audio_data.items()
    ]
    await sink.vc.disconnect()
    files = [discord.File(audio.file, f"{user_id}_{now}.{sink.encoding}") for user_id, audio in sink.audio_data.items()]
    await sink.vc.channel.send(f"完成以下成員的錄音： {', '.join(recorded_users)}.", files=files)

    # pylint: disable=E1101
    for user_id, audio in sink.audio_data.items():
        audio: discord.sinks.AudioData
        file_path = f"{user_id}_{now}.{sink.encoding}"
        with wave.open(file_path, "wb") as wav_file:
            wav_file.setnchannels(2)
            wav_file.setsampwidth(2)
            wav_file.setframerate(48000)
            wav_file.writeframes(audio.file.getvalue())

        # convert_audio(file_path, f"output.wav")
        # with wave.open("output.wav", 'rb') as wav_file:
        #     wav_data = wav_file.readframes(wav_file.getnframes())
        #     recognizer = KaldiRecognizer(model, wav_file.getframerate())
        #     recognizer.AcceptWaveform(wav_data)
        #     print(json.loads(recognizer.Result()).get("text"))

        # wf = wave.open(file_path, 'rb')
        # rec = KaldiRecognizer(model, wf.getframerate())
        # while True:
        #     data = wf.readframes(4000)
        #     if len(data) == 0:
        #         break
        #     if rec.AcceptWaveform(data):
        #         result = json.loads(rec.Result()).get("text")
        #         print(result)
        # print(f'{file_path}: {json.loads(rec.FinalResult()).get("text")}')

        # with sr.AudioFile(file_path) as source:
        #     audio = recognizer.record(source)

        # try:
        #     text = recognizer.recognize_google(audio, language='zh-TW')
        #     recognizer.
        #     print(text)
        # except sr.UnknownValueError:
        #     print("無法識別音頻")
        # except sr.RequestError as e:
        #     print(f"無法請求結果; {e}")

class music(Cog_Extension):
    recording = SlashCommandGroup("recording", "錄音指令")

    @commands.slash_command(description="讓機器人加入語音頻道")
    @commands.guild_only()
    async def join(self, ctx: discord.ApplicationContext, channel: discord.VoiceChannel):
        """Joins a voice channel"""
        if ctx.voice_client:
            await ctx.voice_client.move_to(channel)
        else:
            await channel.connect()
        await ctx.respond(f"我來到了 {channel.name}")

    # @commands.slash_command()
    # async def localplay(self, ctx: discord.ApplicationContext, query: str):
    #     """Plays a file from the local filesystem"""

    #     source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(query))
    #     ctx.voice_client.play(
    #         source, after=lambda e: print(f"Player error: {e}") if e else None
    #     )

    #     await ctx.send(f"Now playing: {query}")

    # @commands.slash_command(description='youtube查詢（非播歌）')
    # @commands.guild_only()
    # async def ytquery(self, ctx: discord.ApplicationContext, query: str):
    #     await ctx.defer()
    #     info = ytdl.extract_info(f'ytsearch:{query}', download=False)
    #     videos = info['entries']
    #     print(len(videos))
    #     text = '\n'.join([f"{i+1}. {v['title']}" for i,v in enumerate(videos)])
    #     await ctx.respond(f"搜尋結果: {text}")

    @commands.slash_command(description="播放音樂")
    @commands.guild_only()
    async def play(self, ctx: discord.ApplicationContext, url: str):
        await ctx.defer()
        guildid = str(ctx.guild.id)
        vc = ctx.voice_client

        if vc.is_recording():
            raise MusicCommandError("正在錄音時無法播放音樂")

        if url.startswith("https://open.spotify.com/"):
            # songfrom = SongSource.Spotify
            raise MusicCommandError("spotify目前不受支援")
        else:
            # songfrom = SongSource.Youtube_or_other
            #抓取歌曲
            try:
                results = await Song.from_url(url, requester=ctx.author)
            except youtube_dl.utils.DownloadError as e:
                raise MusicCommandError("不受支援的連結，請重新檢查網址是否正確") from e

        #播放器設定
        player = guild_playing.get(guildid)
        if not player:
            player = MusicPlayer(vc,ctx,self.bot.loop)
            guild_playing[guildid] = player

        #把歌曲放入清單
        try:
            player.add_song(results)

            if not vc.is_playing() and not vc.is_paused():
                await player.play_next()
        except MusicPlayingError:
            raise
        except Exception as e:
            raise MusicCommandError(e) from e

        #回應
        song_count = len(results)
        if song_count == 1:
            await ctx.respond(f"加入歌單: {results[0].title}")
        else:
            await ctx.respond(f"**{song_count}** 首歌已加入歌單")

    @commands.slash_command(description="跳過歌曲")
    @commands.guild_only()
    async def skip(self, ctx: discord.ApplicationContext):
        guildid = str(ctx.guild.id)
        player = get_player(guildid)
        text = player.skip_song(ctx.author)
        await ctx.respond(text)

    # @commands.slash_command(description='調整音量')
    # async def volume(self, ctx: discord.ApplicationContext, volume: int):
    #     """Changes the player's volume"""

    #     if not ctx.voice_client:
    #         return await ctx.send("我沒有連接到語音頻道")

    #     ctx.voice_client.source.volume = volume / 100
    #     await ctx.send(f"音量設定為 {volume}%")

    @commands.slash_command(description="停止播放並離開頻道")
    @commands.guild_only()
    async def stop(self, ctx: discord.ApplicationContext):
        """Stops and disconnects the bot from voice"""
        guildid = str(ctx.guild.id)
        await ctx.voice_client.disconnect(force=True)
        if guild_playing.get(guildid):
            del guild_playing[guildid]
        await ctx.respond("再見啦~👋")

    @commands.slash_command(description="現在播放")
    @commands.guild_only()
    async def nowplaying(self,ctx: discord.ApplicationContext):
        player = get_player(ctx.guild.id)
        if not player or not player.nowplaying:
            await ctx.respond("目前沒有正在播放的歌曲")
            return

        song = player.nowplaying
        elapsed_seconds = player.get_elapsed_seconds()
        progress_bar, progress_text = format_progress_bar(elapsed_seconds, song.duration)

        embed = BotEmbed.simple(
            title="現在播放",
            description=f"[{song.title}]({song.url}) [{song.requester.mention}]\n{progress_bar} {progress_text}",
        )
        await ctx.respond(embed=embed)

    @commands.slash_command(description="待播歌單")
    @commands.guild_only()
    async def queue(self,ctx: discord.ApplicationContext):
        player = get_player(ctx.guild.id)
        playlist = player.get_full_playlist()
        if playlist:
            page = [BotEmbed.simple(title="待播歌單", description="") for _ in range(math.ceil(len(playlist) / 10))]
            for i, song in enumerate(playlist):
                page[int(i / 10)].description += f"**{i + 1}.** [{song.title}]({song.url}) [{song.requester.mention}/{format_seconds(song.duration)}]\n\n"

            paginator = pages.Paginator(pages=page, use_default_buttons=True,loop_pages=True)
            await paginator.respond(ctx.interaction, ephemeral=False)
        else:
            await ctx.respond("歌單裡空無一物")

    @commands.slash_command(description="暫停/繼續播放歌曲")
    @commands.guild_only()
    async def pause(self, ctx: discord.ApplicationContext):
        player = get_player(ctx.guild.id)
        if not player or not player.nowplaying:
            await ctx.respond("目前沒有正在播放的歌曲")
            return

        player.pause()
        if player.vc.is_paused():
            await ctx.respond("歌曲已暫停⏸️")
        else:
            await ctx.respond("歌曲已繼續▶️")

    @commands.slash_command(description="循環/取消循環單首歌曲")
    @commands.guild_only()
    async def loop(self, ctx: discord.ApplicationContext):
        player = get_player(ctx.guild.id)
        player.songloop = not player.songloop
        if player.songloop:
            await ctx.respond("循環已開啟🔂")
        else:
            await ctx.respond("循環已關閉")

    @commands.slash_command(description="洗牌歌曲")
    @commands.guild_only()
    async def shuffle(self, ctx: discord.ApplicationContext):
        player = get_player(ctx.guild.id)
        player.shuffle()
        await ctx.respond("歌單已隨機🔀")

    @play.before_invoke
    @skip.before_invoke
    #@volume.before_invoke
    @stop.before_invoke
    @nowplaying.before_invoke
    @queue.before_invoke
    #@localplay.before_invoke
    @pause.before_invoke
    @loop.before_invoke
    @shuffle.before_invoke
    @recording.before_invoke
    async def ensure_voice(self, ctx: discord.ApplicationContext):
        if not ctx.voice_client:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect(timeout=10,reconnect=False)
            else:
                raise discord.ApplicationCommandInvokeError(MusicCommandError("請先連接到一個語音頻道"))
        else:
            if not ctx.author.voice or ctx.voice_client.channel != ctx.author.voice.channel:
                raise discord.ApplicationCommandInvokeError(MusicCommandError("你必須要跟機器人在同一頻道才能使用指令"))

    @recording.command(description="開始錄音（實驗版）")
    async def start(self, ctx: discord.ApplicationContext):
        vc = ctx.voice_client
        if vc.is_recording():
            raise MusicCommandError("已經在錄音了")
        if vc.is_playing():
            raise MusicCommandError("正在播放音樂時無法錄音")
        vc.start_recording(discord.sinks.WaveSink(), recording_done)
        await ctx.respond("開始錄音")

    @recording.command(description="結束錄音")
    async def end(self, ctx: discord.ApplicationContext):
        vc = ctx.voice_client
        if not vc.is_recording():
            raise MusicCommandError("沒有在錄音")
        vc.stop_recording()
        await ctx.respond("結束錄音")


def setup(bot):
    bot.add_cog(music(bot))
