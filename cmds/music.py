import asyncio
import enum
import math
import random
import time
from typing import TYPE_CHECKING

import discord
import yt_dlp as youtube_dl
from discord.ext import commands,pages

from starcord import Cog_Extension,BotEmbed,log
from starcord.errors import *


# Suppress noise about console usage from errors
youtube_dl.utils.bug_reports_message = lambda: ""

class SongSource(enum.IntEnum):
    YOUTUBE_OR_OTHER = 1
    SPOTIFY = 2

ytdl_format_options = {
    # "format": "bestaudio/best",
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
    'extractor_retries': 3,
}

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    "options": "-vn"
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)
class Song():
    def __init__(self, url:str, source_path:str, title:str, requester:discord.Member=None, song_from=SongSource.YOUTUBE_OR_OTHER):
        self.url = url
        self.source_path = source_path
        self.title = title
        self.requester = requester
        self.song_from = song_from
        self.source = None

    async def get_source(self, volume=0.5):
        if not self.source:
            source:discord.AudioSource = discord.FFmpegPCMAudio(self.source_path, **ffmpeg_options)
            self.volume = volume
            self.source = discord.PCMVolumeTransformer(source, volume)
        return self.source

    @classmethod
    async def from_url(cls, url:str, *, loop:asyncio.AbstractEventLoop=None, requester:discord.Member=None, song_from=SongSource.YOUTUBE_OR_OTHER):
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
        results = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))
        lst:list[cls] = []

        if "entries" in results:
            # 處理歌單
            results = results["entries"]
        else:
            # 處理單首歌曲
            results = [results]

        for song_datas in results:
            title = song_datas.get("title")
            
            data = None
            if song_datas["webpage_url_domain"] == "youtube.com":
                #針對youtube的處理
                for data in song_datas["formats"]:
                    if data.get("format_note") == "medium":
                        break

            else:
                data = song_datas["formats"][0]

            #filename = data["url"] if stream else ytdl.prepare_filename(data)
            source_path = data.get("url")
            lst.append(cls(url, source_path, title, requester=requester, song_from=song_from))
        
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

    def __init__(self,vc:discord.VoiceClient,ctx:discord.ApplicationContext,loop):
        self.vc = vc
        self.channel = ctx.channel
        self.loop = loop
        self.guildid = str(ctx.guild.id)
        self.playlist = []
        self.songloop = False
        self.volume = 0.5
        self.nowplaying = None
        self.skip_voters = []

    async def play_next(self):
            """
            Plays the next song in the queue.

            This method retrieves the next song from the queue and plays it using the voice client.
            It also sends an embed message to the channel indicating the currently playing song.

            Raises:
                MusicPlayingError: If there is an error playing the next song.
            """
            log.debug("play_next")
            song = self.start_first_song()
            try:
                source = await song.get_source(self.volume)
                
                embed = BotEmbed.simple(title="現在播放", description=f"[{song.title}]({song.url}) [{song.requester.mention}]")
                await self.channel.send(embed=embed,silent=True)
                self.vc.play(source, after=self.after, wait_finish=True)
            except Exception as e:
                raise MusicPlayingError(str(e))

    def after(self, error):
        """
        Callback function called after a song has finished playing.

        Args:
            error (Exception): The error that occurred during playback, if any.
        """
        log.debug("after")
        # self.play_completed()
        if error:
            raise MusicPlayingError(error)
        time.sleep(2)
        if self.playlist:
            # 使用既有的bot協程
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
            await asyncio.sleep(wait_for)
            if not self.vc.is_playing():
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
        del guild_playing[self.guildid]
        await self.channel.send("歌曲播放完畢 掰掰~")

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
            self.skip_voter = []
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


class music(Cog_Extension):

    @commands.slash_command(description='讓機器人加入語音頻道')
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

    @commands.slash_command(description='播放音樂')
    @commands.guild_only()
    async def play(self, ctx: discord.ApplicationContext, url: str):
        await ctx.defer()
        guildid = str(ctx.guild.id)
        vc = ctx.voice_client

        if url.startswith("https://open.spotify.com/"):
            songfrom = SongSource.SPOTIFY
            raise MusicCommandError("不受支援的連結，請重新檢查網址是否正確")
        else:
            songfrom = SongSource.YOUTUBE_OR_OTHER
            #抓取歌曲
            try:
                results = await Song.from_url(url, requester=ctx.author)
            except youtube_dl.utils.DownloadError as e:
                raise MusicCommandError("不受支援的連結，請重新檢查網址是否正確")

        #播放器設定
        player = guild_playing.get(guildid)
        if not player:
            player = MusicPlayer(vc,ctx,self.bot.loop)
            guild_playing[guildid] = player
        
        #把歌曲放入清單
        try:
            player.add_song(results)

            if not vc.is_playing():
                await asyncio.sleep(2)
                await player.play_next()
        except MusicPlayingError:
            raise
        except Exception as e:
            raise MusicCommandError(e)

        #回應
        song_count = len(results)
        if song_count == 1:
            await ctx.respond(f"加入歌單: {results[0].title}")
        else:
            await ctx.respond(f"**{song_count}** 首歌已加入歌單")

    @commands.slash_command(description='跳過歌曲')
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

    @commands.slash_command(description='停止播放並離開頻道')
    @commands.guild_only()
    async def stop(self, ctx: discord.ApplicationContext):
        """Stops and disconnects the bot from voice"""
        guildid = str(ctx.guild.id)
        await ctx.voice_client.disconnect(force=True)
        if guild_playing.get(guildid):
            del guild_playing[guildid]
        await ctx.respond(f"再見啦~")

    @commands.slash_command(description='現在播放')
    @commands.guild_only()
    async def nowplaying(self,ctx: discord.ApplicationContext):
        player = get_player(ctx.guild.id)
        song = player.nowplaying
        embed = BotEmbed.simple(title="現在播放", description=f"[{song.title}]({song.url}) [{song.requester.mention}]")
        await ctx.respond(embed=embed)

    @commands.slash_command(description='歌單')
    @commands.guild_only()
    async def queue(self,ctx: discord.ApplicationContext):
        player = get_player(ctx.guild.id)
        playlist = player.get_full_playlist()
        if playlist:
            page = [BotEmbed.simple(title="播放清單",description='') for _ in range(math.ceil(len(playlist) / 10))]
            for i, song in enumerate(playlist):
                page[int(i / 10)].description += f"**{i+1}.** [{song.title}]({song.url}) [{song.requester.mention}]\n\n"

            paginator = pages.Paginator(pages=page, use_default_buttons=True,loop_pages=True)
            await paginator.respond(ctx.interaction, ephemeral=False)
        else:
            await ctx.respond("歌單裡空無一物")

    @commands.slash_command(description='暫停/繼續播放歌曲')
    @commands.guild_only()
    async def pause(self, ctx: discord.ApplicationContext):
        if not ctx.voice_client.is_paused():
            await ctx.voice_client.pause()
            await ctx.respond(f"歌曲已暫停⏸️")
        else:
            await ctx.voice_client.resume()
            await ctx.respond(f"歌曲已繼續▶️")

    @commands.slash_command(description='循環/取消循環歌曲')
    @commands.guild_only()
    async def loop(self, ctx: discord.ApplicationContext):
        player = get_player(ctx.guild.id)
        player.songloop = not player.songloop
        if player.songloop:
            await ctx.respond(f"循環已開啟🔂")
        else:
            await ctx.respond(f"循環已關閉")

    @commands.slash_command(description='洗牌歌曲')
    @commands.guild_only()
    async def shuffle(self, ctx: discord.ApplicationContext):
        player = get_player(ctx.guild.id)
        player.shuffle()
        await ctx.respond(f"歌單已隨機🔀")

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
    async def ensure_voice(self, ctx: discord.ApplicationContext):
        if not ctx.voice_client:
            if ctx.author.voice:
                try:
                    await ctx.author.voice.channel.connect(timeout=10,reconnect=False)
                except Exception as e:
                    print(e)
            else:
                raise discord.ApplicationCommandInvokeError(MusicCommandError("請先連接到一個語音頻道"))
        else:
            if not ctx.author.voice or ctx.voice_client.channel != ctx.author.voice.channel:
                raise discord.ApplicationCommandInvokeError(MusicCommandError("你必須要跟機器人在同一頻道才能使用指令"))

def setup(bot):
    bot.add_cog(music(bot))

if __name__ == '__main__':
    asyncio.run(Song.from_url("https://youtu.be/TcT_BTzp83M?si=gT2xYd2d9WSiT7Lu"))