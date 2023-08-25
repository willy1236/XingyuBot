import discord,asyncio,time,random
from discord.ext import commands,pages
from typing import TYPE_CHECKING
from core.classes import Cog_Extension
from starcord import BotEmbed
from starcord.errors import *
import youtube_dl

# Suppress noise about console usage from errors
youtube_dl.utils.bug_reports_message = lambda: ""


ytdl_format_options = {
    "format": "bestaudio/best",
    "outtmpl": "%(extractor)s-%(id)s-%(title)s.%(ext)s",
    "restrictfilenames": True,
    "noplaylist": False,
    "nocheckcertificate": True,
    "ignoreerrors": False,
    "logtostderr": False,
    "quiet": False,
    "no_warnings": True,
    "default_search": "auto",
    "source_address": "0.0.0.0",  # Bind to ipv4 since ipv6 addresses cause issues at certain times
    'extractor_retries': 'auto',
}

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    "options": "-vn"
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)


class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source: discord.AudioSource, *, data: dict, volume: float = 0.5):
        super().__init__(source, volume)
        self.title = data.get("title")
        self.url = data.get("url")

    @classmethod
    async def from_url(self, url, *, loop=None, stream=False, volume: float = 0.5):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if "entries" in data:
            # Takes the first item from a playlist
            data = data["entries"][0]

        filename = data["url"] if stream else ytdl.prepare_filename(data)
        return self(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data,volume=volume)


class Song:
    def __init__(self,url:str,title:str,requester:discord.Member=None):
        self.url = url
        self.title = title
        self.requester = requester

class MusicPlayer():
    if TYPE_CHECKING:
        vc: discord.VoiceClient
        ctx: discord.ApplicationContext
        loop: asyncio.AbstractEventLoop
        playlist: list[Song]
        songloop: bool
        volume: float
        nowplaying: Song

    def __init__(self,vc:discord.VoiceClient,ctx:discord.ApplicationContext,loop):
        self.vc = vc
        self.channel = ctx.channel
        self.guildid = str(ctx.guild.id)
        self.loop = loop
        self.playlist = []
        self.songloop = False
        self.volume = 0.5
        self.nowplaying = None

    async def play_next(self,*arg):
            #print('play_next')
            song = self.start_first_song()
            #print(self.playlist,arg)
            try:
                #print(song.title)
                source = await YTDLSource.from_url(song.url, stream=True,volume=self.volume)
                #, loop=self.bot.loop
                
                embed = BotEmbed.simple(title="現在播放", description=f"[{song.title}]({song.url}) [{song.requester.mention}]")
                await self.channel.send(embed=embed)
                #print(f"play1")
                self.vc.play(source, after=self.after)
                #print(f"play2")
            except Exception as e:
                raise MusicPlayingError(str(e))

    def after(self,error):
        #print(f"after")
        self.play_conpleted()
        if error:
            raise MusicPlayingError(error)
        time.sleep(2)
        if self.playlist:
            #使用既有的bot協程
            asyncio.run_coroutine_threadsafe(self.play_next(),self.loop)
        else:
            asyncio.run_coroutine_threadsafe(self.wait_to_leave(),self.loop)

    async def wait_to_leave(self):
        #print('wait2')
        await asyncio.sleep(15)
        if self.vc and not self.vc.is_playing():
            #print('stop')
            await self.stop()

    def skip_song(self):
        self.vc.stop()

    async def stop(self):
        await self.vc.disconnect()
        del guild_playing[self.guildid]
        await self.channel.send("歌曲播放完畢 掰掰~")

    def add_song(self,song:Song):
        self.playlist.append(song)
    
    def start_first_song(self) -> Song:
        if not self.songloop:
            self.nowplaying = self.playlist[0]
            self.playlist.pop(0)
        return self.nowplaying

    def play_conpleted(self):
        self.vc.stop()

    def get_full_playlist(self) -> list[Song]:
        return self.playlist

    def shuffle(self):
        random.shuffle(self.playlist)

guild_playing = {}
def get_player(guildid:str) -> MusicPlayer:
    return guild_playing[guildid]

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
        guildid =str(ctx.guild.id)
        vc = ctx.voice_client

        #抓取歌曲
        try:
            results = ytdl.extract_info(url,download=False)
        except youtube_dl.utils.DownloadError as e:
            raise MusicCommandError("不受支援的連結，請重新檢查網址是否正確")

        #區分歌單與單首歌曲
        if "entries" in results:
            song_data_list = results["entries"]
        else:
            song_data_list = [ results ]

        #播放器設定
        player = guild_playing.get(guildid)
        if not player:
            player = MusicPlayer(vc,ctx,self.bot.loop)
            guild_playing[guildid] = player
        
        #把歌曲放入清單
        song_count = 0
        try:
            for result in song_data_list:
                title = result['title']

                song = Song(url,title,ctx.author)
                player.add_song(song)
                song_count += 1

            if not vc.is_playing():
                await asyncio.sleep(2)
                await player.play_next()
        except MusicPlayingError:
            raise
        except Exception as e:
            raise MusicCommandError(e)

        #回應
        if song_count == 1:
            await ctx.respond(f"加入歌單: {results['title']}")
        else:
            await ctx.respond(f"**{song_count}** 首歌已加入歌單")

    @commands.slash_command(description='跳過歌曲')
    @commands.guild_only()
    async def skip(self, ctx: discord.ApplicationContext):
        guildid = str(ctx.guild.id)
        player = get_player(guildid)
        #if player.nowplaying.requester == ctx.author:
        player.skip_song()
        await ctx.respond(f"歌曲已跳過")

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
        if guild_playing[guildid]:
            del guild_playing[guildid]
        await ctx.respond(f"再見啦~")

    @commands.slash_command(description='現在播放')
    @commands.guild_only()
    async def nowplaying(self,ctx: discord.ApplicationContext):
        player = get_player(str(ctx.guild.id))
        song = player.nowplaying
        embed = BotEmbed.simple(title="現在播放", description=f"[{song.title}]({song.url}) [{song.requester.mention}]")
        await ctx.respond(embed=embed)

    @commands.slash_command(description='歌單')
    @commands.guild_only()
    async def queue(self,ctx: discord.ApplicationContext):
        player = get_player(str(ctx.guild.id))
        playlist = player.get_full_playlist()
        if playlist:
            count = 0
            page_count = 0
            song_count = 1
            page = [BotEmbed.simple(title="播放清單",description='')]
            for song in playlist:
                page[page_count].description += f"**{song_count}.** [{song.title}]({song.url}) [{song.requester.mention}]\n\n"
                song_count += 1
                count += 1
                if count > 10:
                    page.append(BotEmbed.simple(title="播放清單",description=''))
                    count = 0
                    page_count += 1

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
        player = get_player(str(ctx.guild.id))
        player.songloop = not player.songloop
        if player.songloop:
            await ctx.respond(f"循環已開啟🔂")
        else:
            await ctx.respond(f"循環已關閉")

    @commands.slash_command(description='洗牌歌曲')
    @commands.guild_only()
    async def shuffle(self, ctx: discord.ApplicationContext):
        player = get_player(str(ctx.guild.id))
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
                    print(ctx.author.voice.channel)
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

    