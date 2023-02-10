import discord,asyncio,youtube_dl,time
from discord.ext import commands,pages

from core.classes import Cog_Extension
from bothelper import Jsondb,BotEmbed

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
    "quiet": True,
    "no_warnings": True,
    "default_search": "auto",
    "source_address": "0.0.0.0",  # Bind to ipv4 since ipv6 addresses cause issues at certain times
}

ffmpeg_options = {"options": "-vn"}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)


class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source: discord.AudioSource, *, data: dict, volume: float = 0.5):
        super().__init__(source, volume)

        self.data = data

        self.title = data.get("title")
        self.url = data.get("url")

    @classmethod
    async def from_url(self, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(
            None, lambda: ytdl.extract_info(url, download=not stream)
        )

        if "entries" in data:
            # Takes the first item from a playlist
            data = data["entries"][0]

        filename = data["url"] if stream else ytdl.prepare_filename(data)    
        return self(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)


class Player():
    def __init__(self,vc:discord.ApplicationContext.voice_client,ctx:discord.ApplicationContext,loop):
        self.vc = vc
        self.ctx = ctx
        self.loop = loop

    async def play_next(self,*arg):
            print('play_next')
            song = PlayList.get(str(self.ctx.guild.id))
            print(song.title)
            if song:
                try:
                    source = await YTDLSource.from_url(song.url, stream=True)
                    #, loop=self.bot.loop
                    
                    embed = BotEmbed.simple(title="現在播放", description=f"[{song.title}]({song.url}) [{song.requester.mention}]")
                    await self.ctx.send(embed=embed)
                    self.vc.play(source, after=self.after)
                except Exception as e:
                    print('eee')
                    print(e)
            else:
                await asyncio.sleep(10)
                if not self.vc.is_playing():
                    print('stop')
                    await self.ctx.send("歌曲播放完畢 掰掰~")
                    await self.vc.disconnect()
                    del guild_playing[str(self.ctx.guild.id)]


    def after(self,*arg):
        guildid = str(self.ctx.guild.id)
        PlayList.done(guildid)
        self.vc.stop()
        time.sleep(1)
        #使用既有的bot協程
        asyncio.run_coroutine_threadsafe(self.play_next(),self.loop)

    def skip_song(self):
        self.vc.stop()


class Song:
    def __init__(self,url,title,requester=None):
        self.url = url
        self.title = title
        self.requester = requester

class PlayList():
    @staticmethod
    def add(guildid,song:Song):
        if guildid in bot_playlist:
            bot_playlist[guildid].append(song)
        else:
            bot_playlist[guildid] = [ song ]
    
    @staticmethod
    def done(guildid):
        del bot_playlist[guildid][0]
        if not bot_playlist[guildid]:
            del bot_playlist[guildid]

    @staticmethod
    def get(guildid,index=0):
        try:
            return bot_playlist[guildid][index]
        except KeyError:
            return None

    @staticmethod
    def get_fulllist(guildid):
        return bot_playlist[guildid]
        


guild_playing = {}
bot_playlist = {}

class music(Cog_Extension):

    @commands.slash_command()
    async def join(self, ctx: discord.ApplicationContext, channel: discord.VoiceChannel):
        """Joins a voice channel"""

        if ctx.voice_client:
            return await ctx.voice_client.move_to(channel)

        await channel.connect()

    # @commands.slash_command()
    # async def localplay(self, ctx: discord.ApplicationContext, query: str):
    #     """Plays a file from the local filesystem"""

    #     source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(query))
    #     ctx.voice_client.play(
    #         source, after=lambda e: print(f"Player error: {e}") if e else None
    #     )

    #     await ctx.send(f"Now playing: {query}")

    # @commands.slash_command()
    # async def yt(self, ctx: discord.ApplicationContext, url: str):
    #     """Plays from a url (almost anything youtube_dl supports)"""

    #     async with ctx.typing():
    #         player = await YTDLSource.from_url(url, loop=self.bot.loop)
    #         ctx.voice_client.play(
    #             player, after=lambda e: print(f"Player error: {e}") if e else None
    #         )

    #     await ctx.send(f"Now playing: {player.title}")

    @commands.slash_command(description='播放音樂')
    async def play(self, ctx: discord.ApplicationContext, url: str):
        """Streams from a url (same as yt, but doesn't predownload)"""
        await ctx.defer()
        guildid =str(ctx.guild.id)
        vc = ctx.voice_client

        results = ytdl.extract_info(url,download=False)
        #print(results)
        if "entries" in results:
            song_data_list = results["entries"]
        else:
            song_data_list = [ results ]

        song_count = 0
        for result in song_data_list:
            try:
                title = result['title']
                if guildid in guild_playing and vc:
                    #print('in')
                    PlayList.add(guildid,Song(url,title,ctx.author))
                    
                else:
                    #print('not in')
                    PlayList.add(guildid,Song(url,title,ctx.author))
                    player = Player(vc,ctx,self.bot.loop)
                    guild_playing[guildid] = player
                    await player.play_next()
                song_count += 1
            except:
                pass

        if song_count == 1:
            await ctx.respond(f"加入歌單: {results['title']}")
        else:
            await ctx.respond(f"**{song_count}** 首歌已加入歌單")

    @commands.slash_command(description='跳過歌曲')
    async def skip(self, ctx: discord.ApplicationContext):
        guildid = str(ctx.guild.id)
        player = guild_playing[guildid]
        player.skip_song()
        await ctx.respond(f"歌曲已跳過")

    @play.before_invoke
    @skip.before_invoke
    #@yt.before_invoke
    #@localplay.before_invoke
    async def ensure_voice(self, ctx: discord.ApplicationContext):
        if not ctx.voice_client:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect()
            else:
                raise discord.ApplicationCommandError("請先連接到一個語音頻道")
        else:
            if not ctx.author.voice or ctx.voice_client.channel != ctx.author.voice.channel:
                raise discord.ApplicationCommandError("你必須要跟機器人在同一頻道才能使用指令")


    @commands.slash_command(description='調整音量')
    async def volume(self, ctx: discord.ApplicationContext, volume: int):
        """Changes the player's volume"""

        if not ctx.voice_client:
            return await ctx.send("我沒有連接到語音頻道")

        ctx.voice_client.source.volume = volume / 100
        await ctx.send(f"音量設定為 {volume}%")

    @commands.slash_command(description='停止播放')
    async def stop(self, ctx: discord.ApplicationContext):
        """Stops and disconnects the bot from voice"""

        await ctx.voice_client.disconnect(force=True)
        await ctx.respond(f"再見啦~")

    @commands.slash_command(description='現在播放')
    async def nowplaying(self,ctx):
        song = PlayList.get(str(ctx.guild.id))
        embed = BotEmbed.simple(title="現在播放", description=f"[{song.title}]({song.url}) [{song.requester.mention}]")
        await ctx.respond(embed=embed)

    @commands.slash_command(description='歌單')
    async def queue(self,ctx):
        playlist = PlayList.get_fulllist(str(ctx.guild.id))
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
                


            paginator = pages.Paginator(pages=page, use_default_buttons=True)
            await paginator.respond(ctx.interaction, ephemeral=False)
        else:
            await ctx.respond("歌單裡空無一物")

def setup(bot):
    bot.add_cog(music(bot))

    