# type: ignore
import re

import discord
import yt_dlp as youtube_dl
from discord.commands import SlashCommandGroup
from discord.ext import commands, pages

from starlib import BotEmbed
from starlib.exceptions import MusicCommandError, MusicPlayingError

from ..extension import Cog_Extension
from ..music_player import (
    MusicPlayer,
    Song,
    format_progress_bar,
    format_seconds,
    get_player,
    guild_playing,
    recording_done,
)


class music(Cog_Extension):
    recording = SlashCommandGroup("recording", "錄音指令")

    @commands.slash_command(description="讓機器人加入語音頻道")
    @commands.guild_only()
    async def join(self, ctx: discord.ApplicationContext, channel: discord.VoiceChannel):
        if ctx.voice_client:
            await ctx.voice_client.move_to(channel)
        else:
            await channel.connect()
        await ctx.respond(f"我來到了 {channel.name}")

    @commands.slash_command(description="播放音樂")
    @commands.guild_only()
    async def play(self, ctx: discord.ApplicationContext, url: str):
        guildid = str(ctx.guild.id)
        vc = ctx.voice_client

        if vc.is_recording():
            raise MusicCommandError("正在錄音時無法播放音樂")

        if url.startswith("https://open.spotify.com/"):
            raise MusicCommandError("spotify目前不受支援")

        try:
            results = await Song.from_url(url, requester=ctx.author)
        except youtube_dl.utils.DownloadError as e:
            clean = re.sub(r"\x1b\[[0-9;]*m", "", str(e)).removeprefix("ERROR: ").strip()
            raise MusicCommandError(clean or "不受支援的連結，請重新檢查網址是否正確") from e

        if not results:
            raise MusicCommandError("歌曲擷取失敗，請重新檢查網址是否正確")

        player = guild_playing.get(guildid)
        if not player:
            player = MusicPlayer(vc, ctx, self.bot.loop)
            guild_playing[guildid] = player

        try:
            player.add_song(results)
            if not vc.is_playing() and not vc.is_paused():
                await player.play_next()
        except MusicPlayingError:
            raise
        except Exception as e:
            raise MusicCommandError(e) from e

        if len(results) == 1:
            await ctx.respond(f"加入歌單: {results[0].title}")
        else:
            await ctx.respond(f"**{len(results)}** 首歌已加入歌單")

    @commands.slash_command(description="跳過歌曲")
    @commands.guild_only()
    async def skip(self, ctx: discord.ApplicationContext):
        player = get_player(ctx.guild.id)
        await ctx.respond(player.skip_song(ctx.author))

    @commands.slash_command(description="停止播放並離開頻道")
    @commands.guild_only()
    async def stop(self, ctx: discord.ApplicationContext):
        guildid = str(ctx.guild.id)
        await ctx.voice_client.disconnect(force=True)
        if guild_playing.get(guildid):
            del guild_playing[guildid]
        await ctx.respond("再見啦~👋")

    @commands.slash_command(description="現在播放")
    @commands.guild_only()
    async def nowplaying(self, ctx: discord.ApplicationContext):
        player = get_player(ctx.guild.id)
        if not player or not player.nowplaying:
            await ctx.respond("目前沒有正在播放的歌曲")
            return

        song = player.nowplaying
        progress_bar, progress_text = format_progress_bar(player.get_elapsed_seconds(), song.duration)
        embed = BotEmbed.simple(
            title="現在播放",
            description=f"[{song.title}]({song.url}) [{song.requester.mention}]\n{progress_bar} {progress_text}",
        )
        await ctx.respond(embed=embed)

    @commands.slash_command(description="待播歌單")
    @commands.guild_only()
    async def queue(self, ctx: discord.ApplicationContext):
        player = get_player(ctx.guild.id)
        playlist = player.get_full_playlist()
        if not playlist:
            await ctx.respond("歌單裡空無一物")
            return

        import math
        page = [BotEmbed.simple(title="待播歌單", description="") for _ in range(math.ceil(len(playlist) / 10))]
        for i, song in enumerate(playlist):
            page[i // 10].description += (
                f"**{i + 1}.** [{song.title}]({song.url}) "
                f"[{song.requester.mention}/{format_seconds(song.duration)}]\n\n"
            )
        paginator = pages.Paginator(pages=page, use_default_buttons=True, loop_pages=True)
        await paginator.respond(ctx.interaction, ephemeral=False)

    @commands.slash_command(description="暫停/繼續播放歌曲")
    @commands.guild_only()
    async def pause(self, ctx: discord.ApplicationContext):
        player = get_player(ctx.guild.id)
        if not player or not player.nowplaying:
            await ctx.respond("目前沒有正在播放的歌曲")
            return
        player.pause()
        await ctx.respond("歌曲已暫停⏸️" if player.vc.is_paused() else "歌曲已繼續▶️")

    @commands.slash_command(description="循環/取消循環單首歌曲")
    @commands.guild_only()
    async def loop(self, ctx: discord.ApplicationContext):
        player = get_player(ctx.guild.id)
        player.songloop = not player.songloop
        await ctx.respond("循環已開啟🔂" if player.songloop else "循環已關閉")

    @commands.slash_command(description="洗牌歌曲")
    @commands.guild_only()
    async def shuffle(self, ctx: discord.ApplicationContext):
        player = get_player(ctx.guild.id)
        player.shuffle()
        await ctx.respond("歌單已隨機🔀")

    @play.before_invoke
    @skip.before_invoke
    @stop.before_invoke
    @nowplaying.before_invoke
    @queue.before_invoke
    @pause.before_invoke
    @loop.before_invoke
    @shuffle.before_invoke
    @recording.before_invoke
    async def ensure_voice(self, ctx: discord.ApplicationContext):
        await ctx.defer()
        if not ctx.voice_client:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect(timeout=10, reconnect=False)
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
        try:
            vc.start_recording(discord.sinks.WaveSink(), recording_done)
        except AttributeError:
            raise MusicCommandError(
                "錄音功能目前因 Discord 語音端對端加密（DAVE）與 py-cord 尚未相容而無法使用，"
                "詳見 https://github.com/Pycord-Development/pycord/issues/3139"
            )
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
