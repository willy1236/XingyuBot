# type: ignore
import math
import random
import re

import discord
import yt_dlp as youtube_dl
from discord import OptionChoice
from discord.commands import SlashCommandGroup
from discord.ext import commands, pages
from discord.utils import format_dt

from starlib import BotEmbed, sqldb
from starlib.database import MusicPlaylist, MusicPlaylistSource
from starlib.exceptions import MusicCommandError, MusicPlayingError

from ..checks import RegisteredContext, ensure_registered
from ..extension import Cog_Extension
from ..music_player import (
    ExtractResult,
    LoopMode,
    MusicPlayer,
    Song,
    format_progress_bar,
    format_seconds,
    get_or_create_player,
    get_player,
    recording_done,
)
from ..uiElement.view import ConfirmView, MusicPlaylistSelectView

# 機器人不在語音頻道時，只有這些指令會自動加入
_AUTO_JOIN_COMMANDS = {"play", "recording start"}

# 個人歌單上限：歌單數配合下拉選單最多 25 個選項
MAX_PLAYLISTS = 25
MAX_PLAYLIST_SONGS = 500
MAX_PLAYLIST_NAME_LENGTH = 50

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


async def _ensure_author_voice(voice_client: discord.VoiceClient | None, author: discord.Member, *, auto_join: bool) -> discord.VoiceClient:
    """確認使用者跟機器人在同一語音頻道，機器人不在頻道且 auto_join 時自動加入。"""
    if not voice_client:
        if not auto_join:
            raise MusicCommandError("機器人目前不在語音頻道")
        if not author.voice:
            raise MusicCommandError("請先連接到一個語音頻道")
        return await author.voice.channel.connect(timeout=10, reconnect=False)
    if not author.voice or voice_client.channel != author.voice.channel:
        raise MusicCommandError("你必須要跟機器人在同一頻道才能使用指令")
    return voice_client


async def _extract_songs(url: str, requester: discord.Member) -> ExtractResult:
    if url.startswith("https://open.spotify.com/"):
        raise MusicCommandError("spotify目前不受支援")

    try:
        result = await Song.extract(url, requester=requester)
    except youtube_dl.utils.DownloadError as e:
        clean = re.sub(r"\x1b\[[0-9;]*m", "", str(e)).removeprefix("ERROR: ").strip()
        raise MusicCommandError(clean or "不受支援的連結，請重新檢查網址是否正確") from e

    if not result.songs:
        raise MusicCommandError("歌曲擷取失敗，請重新檢查網址是否正確")
    return result


async def _enqueue_and_play(vc: discord.VoiceClient, ctx: discord.ApplicationContext, loop, songs: list[Song], skipped: int = 0) -> str:
    """把歌曲加入伺服器佇列，沒在播放就開始播放，回傳給使用者的訊息。"""
    player = get_or_create_player(vc, ctx, loop)

    try:
        player.add_song(songs)
        if not vc.is_playing() and not vc.is_paused():
            await player.play_next()
    except MusicPlayingError:
        raise
    except Exception as e:
        raise MusicCommandError(e) from e

    text = f"加入歌單: {songs[0].title}" if len(songs) == 1 else f"**{len(songs)}** 首歌已加入歌單"
    if skipped:
        text += f"（已略過 {skipped} 首無法播放的歌曲）"
    return text


def _clean_playlist_name(name: str) -> str:
    name = name.strip()
    if not name:
        raise MusicCommandError("歌單名稱不可為空")
    if len(name) > MAX_PLAYLIST_NAME_LENGTH:
        raise MusicCommandError(f"歌單名稱最多 {MAX_PLAYLIST_NAME_LENGTH} 個字")
    return name


def _get_playlist(user_id: int, name: str) -> MusicPlaylist:
    playlist = sqldb.get_music_playlist(user_id, name.strip())
    if not playlist:
        raise MusicCommandError(f"找不到歌單「{name}」")
    return playlist


def _get_or_create_playlist(user_id: int, name: str) -> MusicPlaylist:
    name = _clean_playlist_name(name)
    playlist = sqldb.get_music_playlist(user_id, name)
    if playlist:
        return playlist
    if len(sqldb.get_music_playlists(user_id)) >= MAX_PLAYLISTS:
        raise MusicCommandError(f"歌單數量已達上限 {MAX_PLAYLISTS} 個")
    return sqldb.create_music_playlist(user_id, name)


def _playlist_room(playlist: MusicPlaylist) -> int:
    room = MAX_PLAYLIST_SONGS - sqldb.count_music_playlist_songs(playlist.id)
    if room <= 0:
        raise MusicCommandError(f"歌單「{playlist.name}」已達上限 {MAX_PLAYLIST_SONGS} 首")
    return room


def _song_rows(songs: list[Song]) -> list[tuple[str, str, int | None]]:
    return [(song.url, song.title, song.duration) for song in songs]


def _overflow_text(dropped: int) -> str:
    return f"（歌單已滿 {MAX_PLAYLIST_SONGS} 首，略過 {dropped} 首）" if dropped else ""


def _save_songs(playlist: MusicPlaylist, songs: list[Song], source_id: int | None = None) -> str:
    """把歌曲存進歌單（超過上限的部分捨棄），回傳給使用者的訊息。"""
    to_save = songs[: _playlist_room(playlist)]
    sqldb.add_music_playlist_songs(playlist.id, _song_rows(to_save), source_id=source_id)
    text = f"已將 {to_save[0].title} 加入歌單「{playlist.name}」" if len(to_save) == 1 else f"已將 **{len(to_save)}** 首歌加入歌單「{playlist.name}」"
    return text + _overflow_text(len(songs) - len(to_save))


def _source_name(source: MusicPlaylistSource) -> str:
    return source.title or source.url


def _replace_source_songs(playlist: MusicPlaylist, source: MusicPlaylistSource, result: ExtractResult) -> str:
    """以重新擷取的結果取代歌單中來自此來源的歌曲，回傳給使用者的訊息。"""
    songs = sqldb.get_music_playlist_songs(playlist.id)
    old_count = sum(1 for song in songs if song.source_id == source.id)
    room = MAX_PLAYLIST_SONGS - len(songs) + old_count
    to_save = result.songs[: max(room, 0)]

    added, removed = sqldb.replace_music_playlist_source_songs(source, _song_rows(to_save), result.playlist_title)
    return f"「{_source_name(source)}」新增 {added} 首、移除 {removed} 首" + _overflow_text(len(result.songs) - len(to_save))


async def _playlist_name_autocomplete(ctx: discord.AutocompleteContext) -> list[str]:
    cuser = sqldb.get_cloud_user_by_discord(ctx.interaction.user.id)
    if not cuser:
        return []
    value = (ctx.value or "").lower()
    return [p.name for p in sqldb.get_music_playlists(cuser.id) if value in p.name.lower()][:25]


def _playlist_name_option(**kwargs):
    return discord.Option(str, name="歌單", description="歌單名稱", autocomplete=_playlist_name_autocomplete, **kwargs)


class music(Cog_Extension):
    recording = SlashCommandGroup("recording", "錄音指令")
    playlist = SlashCommandGroup("playlist", "個人歌單")

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

        result = await _extract_songs(url, ctx.author)
        await ctx.respond(await _enqueue_and_play(vc, ctx, self.bot.loop, result.songs, result.skipped))

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
        try:
            await _ensure_author_voice(ctx.voice_client, ctx.author, auto_join=ctx.command.qualified_name in _AUTO_JOIN_COMMANDS)
        except MusicCommandError as e:
            raise discord.ApplicationCommandInvokeError(e) from e

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

    @playlist.command(name="create", description="建立個人歌單")
    @ensure_registered()
    async def playlist_create(self, ctx: RegisteredContext, name: discord.Option(str, name="歌單", description="歌單名稱")):
        name = _clean_playlist_name(name)
        if sqldb.get_music_playlist(ctx.cuser.id, name):
            raise MusicCommandError(f"已經有名為「{name}」的歌單")
        _get_or_create_playlist(ctx.cuser.id, name)
        await ctx.respond(f"已建立歌單「{name}」", ephemeral=True)

    @playlist.command(name="delete", description="刪除個人歌單")
    @ensure_registered()
    async def playlist_delete(self, ctx: RegisteredContext, name: _playlist_name_option()):
        playlist = _get_playlist(ctx.cuser.id, name)
        view = ConfirmView(ctx.author.id, confirm_label="刪除")
        await ctx.respond(f"確定要刪除歌單「{playlist.name}」嗎？", view=view, ephemeral=True)
        await view.wait()
        if view.confirmed:
            sqldb.delete_music_playlist(playlist.id)
            await ctx.interaction.edit_original_response(content=f"已刪除歌單「{playlist.name}」", view=None)
        else:
            await ctx.interaction.edit_original_response(content="已取消刪除", view=None)

    @playlist.command(name="add", description="把歌曲或整份歌單網址加入個人歌單（歌單不存在時自動建立）")
    @ensure_registered()
    async def playlist_add(
        self,
        ctx: RegisteredContext,
        name: _playlist_name_option(),
        url: discord.Option(str, name="網址", description="單曲或歌單網址（YouTube、Bilibili 等）"),
    ):
        name = _clean_playlist_name(name)
        await ctx.defer(ephemeral=True)
        result = await _extract_songs(url, ctx.author)
        # 擷取成功後才建立歌單，避免連結無效時留下空歌單
        playlist = _get_or_create_playlist(ctx.cuser.id, name)

        if not result.playlist_url:
            text = _save_songs(playlist, result.songs)
        elif source := sqldb.get_music_playlist_source(playlist.id, result.playlist_url):
            # 同一個外部歌單再貼一次時改為同步，避免重複加入
            text = "此來源已存在，已同步：" + _replace_source_songs(playlist, source, result)
        else:
            _playlist_room(playlist)  # 歌單已滿時先擋下，不留下沒有歌曲的來源
            source = sqldb.create_music_playlist_source(playlist.id, result.playlist_url, result.playlist_title)
            text = _save_songs(playlist, result.songs, source_id=source.id) + "，之後可用 /playlist sync 同步外部歌單的更新"

        if result.skipped:
            text += f"（已略過 {result.skipped} 首無法播放的歌曲）"
        await ctx.respond(text, ephemeral=True)

    @playlist.command(name="sync", description="重新擷取歌單匯入過的外部歌單（手動加入的歌曲不受影響）")
    @ensure_registered()
    async def playlist_sync(self, ctx: RegisteredContext, name: _playlist_name_option()):
        playlist = _get_playlist(ctx.cuser.id, name)
        sources = sqldb.get_music_playlist_sources(playlist.id)
        if not sources:
            raise MusicCommandError(f"歌單「{playlist.name}」沒有匯入過外部歌單")

        await ctx.defer(ephemeral=True)
        lines = []
        for source in sources:
            try:
                result = await _extract_songs(source.url, ctx.author)
            except MusicCommandError as e:
                # 外部歌單被刪除或改為私人時保留舊的歌曲
                lines.append(f"「{_source_name(source)}」同步失敗，保留原本的歌曲：{e.message}")
                continue
            lines.append(_replace_source_songs(playlist, source, result))

        text = "\n".join(lines)
        await ctx.respond(text if len(text) <= 2000 else text[:1997] + "…", ephemeral=True)

    @playlist.command(name="save_current", description="把目前播放的歌存進個人歌單（歌單不存在時自動建立）")
    @commands.guild_only()
    @ensure_registered()
    async def playlist_save_current(self, ctx: RegisteredContext, name: _playlist_name_option()):
        player = _require_player(ctx, need_playing=True)
        playlist = _get_or_create_playlist(ctx.cuser.id, name)
        await ctx.respond(_save_songs(playlist, [player.nowplaying]), ephemeral=True)

    @playlist.command(name="save_queue", description="把目前播放與待播歌單全部存進個人歌單（歌單不存在時自動建立）")
    @commands.guild_only()
    @ensure_registered()
    async def playlist_save_queue(self, ctx: RegisteredContext, name: _playlist_name_option()):
        player = _require_player(ctx)
        songs = ([player.nowplaying] if player.nowplaying else []) + player.get_full_playlist()
        if not songs:
            raise MusicCommandError("歌單裡空無一物")
        playlist = _get_or_create_playlist(ctx.cuser.id, name)
        await ctx.respond(_save_songs(playlist, songs), ephemeral=True)

    @playlist.command(name="remove", description="從個人歌單刪除一首歌")
    @ensure_registered()
    async def playlist_remove(
        self,
        ctx: RegisteredContext,
        name: _playlist_name_option(),
        index: discord.Option(int, name="編號", description="歌曲編號（可用 /playlist show 查看）", min_value=1),
    ):
        playlist = _get_playlist(ctx.cuser.id, name)
        removed = sqldb.remove_music_playlist_song(playlist.id, index - 1)
        if not removed:
            raise MusicCommandError(f"歌單「{playlist.name}」沒有第 {index} 首歌")
        await ctx.respond(f"已從歌單「{playlist.name}」刪除 {removed.title}", ephemeral=True)

    @playlist.command(name="show", description="查看個人歌單內容")
    @ensure_registered()
    async def playlist_show(self, ctx: RegisteredContext, name: _playlist_name_option()):
        playlist = _get_playlist(ctx.cuser.id, name)
        songs = sqldb.get_music_playlist_songs(playlist.id)
        if not songs:
            await ctx.respond(f"歌單「{playlist.name}」裡空無一物", ephemeral=True)
            return

        title = f"{playlist.name}（{len(songs)} 首）"
        page = [BotEmbed.simple(title=title, description="") for _ in range(math.ceil(len(songs) / 10))]
        sources = sqldb.get_music_playlist_sources(playlist.id)
        if sources:
            source_lines = [f"[{_source_name(s)}]({s.url})（上次同步 {format_dt(s.synced_at, 'R')}）" for s in sources]
            page[0].description = "來源：\n" + "\n".join(source_lines) + "\n\n"
        for i, song in enumerate(songs):
            page[i // 10].description += f"**{i + 1}.** [{song.title}]({song.url}) [{format_seconds(song.duration)}]\n\n"
        paginator = pages.Paginator(pages=page, use_default_buttons=True, loop_pages=True)
        await paginator.respond(ctx.interaction, ephemeral=True)

    @playlist.command(name="play", description="選擇個人歌單並播放")
    @commands.guild_only()
    @ensure_registered()
    async def playlist_play(
        self,
        ctx: RegisteredContext,
        shuffle: discord.Option(bool, name="隨機", description="是否打亂播放順序", default=False),
    ):
        if not ctx.author.voice:
            raise MusicCommandError("請先連接到一個語音頻道")

        playlists = sqldb.get_music_playlists(ctx.cuser.id)
        if not playlists:
            raise MusicCommandError("你還沒有歌單，請先用 /playlist create 建立")
        counts = sqldb.get_music_playlist_song_counts(ctx.cuser.id)

        async def on_select(interaction: discord.Interaction, playlist_id: int):
            await interaction.response.edit_message(content="載入歌單中…", view=view)
            try:
                text = await self._play_saved_playlist(ctx, playlist_id, shuffle)
            except MusicCommandError as e:
                await interaction.edit_original_response(content=str(e.message), view=None)
                return
            await interaction.edit_original_response(content="已開始播放", view=None)
            await interaction.followup.send(text)

        view = MusicPlaylistSelectView(ctx.author.id, [(p.id, p.name, counts.get(p.id, 0)) for p in playlists], on_select)
        await ctx.respond("選擇要播放的歌單", view=view, ephemeral=True)

    async def _play_saved_playlist(self, ctx: discord.ApplicationContext, playlist_id: int, shuffle: bool) -> str:
        rows = sqldb.get_music_playlist_songs(playlist_id)
        if not rows:
            raise MusicCommandError("這個歌單還沒有歌曲")

        vc = await _ensure_author_voice(ctx.guild.voice_client, ctx.author, auto_join=True)
        if vc.is_recording():
            raise MusicCommandError("正在錄音時無法播放音樂")

        songs = [Song(row.url, None, row.title, requester=ctx.author, duration=row.duration) for row in rows]
        if shuffle:
            random.shuffle(songs)
        return await _enqueue_and_play(vc, ctx, self.bot.loop, songs)


def setup(bot):
    bot.add_cog(music(bot))
