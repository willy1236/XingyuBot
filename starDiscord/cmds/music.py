# type: ignore
import math
import re

import discord
import yt_dlp as youtube_dl
from discord import OptionChoice
from discord.commands import SlashCommandGroup
from discord.ext import commands, pages

from starlib import BotEmbed
from starlib.exceptions import MusicCommandError, MusicPlayingError

from ..extension import Cog_Extension
from ..music_player import (
    LoopMode,
    MusicPlayer,
    Song,
    format_progress_bar,
    format_seconds,
    get_or_create_player,
    get_player,
    recording_done,
)

# 機器人不在語音頻道時，只有這些指令會自動加入
_AUTO_JOIN_COMMANDS = {"play", "recording start"}

_LOOP_MODE_OPTION = [
    OptionChoice(name="關閉", value=LoopMode.OFF.value),
    OptionChoice(name="單首循環", value=LoopMode.SONG.value),
    OptionChoice(name="整張歌單循環", value=LoopMode.QUEUE.value),
]
_LOOP_MODE_REPLY = {
    LoopMode.OFF: "循環已關閉",
    LoopMode.SONG: "單首循環已開啟🔂",
    LoopMode.QUEUE: "整張歌單循環已開啟🔁",
}


def _require_player(ctx: discord.ApplicationContext, *, need_playing: bool = False) -> MusicPlayer:
    player = get_player(ctx.guild.id)
    if not player or (need_playing and not player.nowplaying):
        raise MusicCommandError("目前沒有播放中的歌曲")
    return player


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
        vc = ctx.voice_client

        if vc.is_recording():
            raise MusicCommandError("正在錄音時無法播放音樂")

        if url.startswith("https://open.spotify.com/"):
            raise MusicCommandError("spotify目前不受支援")

        try:
            results, skipped = await Song.from_url(url, requester=ctx.author)
        except youtube_dl.utils.DownloadError as e:
            clean = re.sub(r"\x1b\[[0-9;]*m", "", str(e)).removeprefix("ERROR: ").strip()
            raise MusicCommandError(clean or "不受支援的連結，請重新檢查網址是否正確") from e

        if not results:
            raise MusicCommandError("歌曲擷取失敗，請重新檢查網址是否正確")

        player = get_or_create_player(vc, ctx, self.bot.loop)

        try:
            player.add_song(results)
            if not vc.is_playing() and not vc.is_paused():
                await player.play_next()
        except MusicPlayingError:
            raise
        except Exception as e:
            raise MusicCommandError(e) from e

        text = f"加入歌單: {results[0].title}" if len(results) == 1 else f"**{len(results)}** 首歌已加入歌單"
        if skipped:
            text += f"（已略過 {skipped} 首無法播放的歌曲）"
        await ctx.respond(text)

    @commands.slash_command(description="跳過歌曲")
    @commands.guild_only()
    async def skip(self, ctx: discord.ApplicationContext):
        player = _require_player(ctx, need_playing=True)
        await ctx.respond(player.skip_song(ctx.author))

    @commands.slash_command(description="停止播放並離開頻道")
    @commands.guild_only()
    async def stop(self, ctx: discord.ApplicationContext):
        player = get_player(ctx.guild.id)
        if player:
            await player.close()
        else:
            await ctx.voice_client.disconnect(force=True)
        await ctx.respond("再見啦~👋")

    @commands.Cog.listener("on_voice_state_update")
    async def cleanup_on_voice_disconnect(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        # 機器人被移出語音或連線中斷時收掉播放器，避免殘留綁著舊連線的 player
        if member.id != self.bot.user.id or not before.channel or after.channel:
            return
        player = get_player(member.guild.id)
        if player and not player.closing:
            await player.close("我已離開語音頻道，歌單已清空")

    @commands.slash_command(description="現在播放")
    @commands.guild_only()
    async def nowplaying(self, ctx: discord.ApplicationContext):
        player = _require_player(ctx, need_playing=True)
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
        player = _require_player(ctx)
        playlist = player.get_full_playlist()
        if not playlist:
            await ctx.respond("歌單裡空無一物")
            return

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
        player = _require_player(ctx, need_playing=True)
        player.pause()
        await ctx.respond("歌曲已暫停⏸️" if player.vc.is_paused() else "歌曲已繼續▶️")

    @commands.slash_command(description="設定循環模式")
    @commands.guild_only()
    async def loop(
        self,
        ctx: discord.ApplicationContext,
        mode: discord.Option(str, name="模式", description="循環模式", required=True, choices=_LOOP_MODE_OPTION),
    ):
        player = _require_player(ctx)
        player.loop_mode = LoopMode(mode)
        await ctx.respond(_LOOP_MODE_REPLY[player.loop_mode])

    @commands.slash_command(description="洗牌歌曲")
    @commands.guild_only()
    async def shuffle(self, ctx: discord.ApplicationContext):
        player = _require_player(ctx)
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
            if ctx.command.qualified_name not in _AUTO_JOIN_COMMANDS:
                raise discord.ApplicationCommandInvokeError(MusicCommandError("機器人目前不在語音頻道"))
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
