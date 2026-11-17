# type: ignore
import math
from uuid import UUID

import discord
from discord import OptionChoice
from discord.commands import SlashCommandGroup
from discord.ext import commands, pages
from discord.utils import format_dt

from starlib import BotEmbed, sqldb
from starlib import music_playlist as playlists
from starlib.database import MusicPlaylist
from starlib.exceptions import MusicCommandError
from starlib.identity import IdentityUnavailable, resolve_identity

from ..checks import IdentityContext, with_identity
from ..extension import Cog_Extension
from ..music_player import (
    LoopMode,
    MusicPlayer,
    enqueue_and_play,
    ensure_author_voice,
    extract_songs,
    format_progress_bar,
    format_seconds,
    get_player,
    play_saved_playlist,
    recording_done,
)
from ..uiElement.music_panel import MusicPanelView
from ..uiElement.view import ConfirmView, MusicPlaylistSelectView

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


def _song_rows(songs) -> list[playlists.SongRow]:
    return [(song.url, song.title, song.duration) for song in songs]


def _get_playlist(user_id: UUID, name: str) -> MusicPlaylist:
    playlist = sqldb.get_music_playlist(user_id, name.strip())
    if not playlist:
        raise MusicCommandError(f"找不到歌單「{name}」")
    return playlist


async def _playlist_name_autocomplete(ctx: discord.AutocompleteContext) -> list[str]:
    # 沒用過 bot 的人本來就沒有歌單，不必為了補全發臨時 ID
    try:
        identity = await resolve_identity(ctx.interaction.user.id, create=False)
    except IdentityUnavailable:
        return []
    if identity is None or identity.suspended:
        return []
    value = (ctx.value or "").lower()
    return [p.name for p in sqldb.get_music_playlists(identity.user_id) if value in p.name.lower()][:25]


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

        result = await extract_songs(url, ctx.author)
        await ctx.respond(await enqueue_and_play(vc, ctx, self.bot.loop, result.songs, result.skipped))

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

    @commands.slash_command(name="music", description="音樂控制面板")
    @commands.guild_only()
    async def music_panel(self, ctx: discord.ApplicationContext):
        # 沒在播放也能開：面板只顯示點歌與個人歌單按鈕，語音頻道檢查交給各按鈕
        await ctx.respond(view=MusicPanelView(ctx.guild.id))

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
            await ensure_author_voice(ctx.voice_client, ctx.author, auto_join=ctx.command.qualified_name in _AUTO_JOIN_COMMANDS)
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
            ) from None
        await ctx.respond("開始錄音")

    @recording.command(description="結束錄音")
    async def end(self, ctx: discord.ApplicationContext):
        vc = ctx.voice_client
        if not vc.is_recording():
            raise MusicCommandError("沒有在錄音")
        vc.stop_recording()
        await ctx.respond("結束錄音")

    @playlist.command(name="create", description="建立個人歌單")
    @with_identity()
    async def playlist_create(self, ctx: IdentityContext, name: discord.Option(str, name="歌單", description="歌單名稱")):
        name = playlists.create_playlist(ctx.identity.user_id, name).name
        await ctx.respond(f"已建立歌單「{name}」", ephemeral=True)

    @playlist.command(name="delete", description="刪除個人歌單")
    @with_identity()
    async def playlist_delete(self, ctx: IdentityContext, name: _playlist_name_option()):
        playlist = _get_playlist(ctx.identity.user_id, name)
        view = ConfirmView(ctx.author.id, confirm_label="刪除")
        await ctx.respond(f"確定要刪除歌單「{playlist.name}」嗎？", view=view, ephemeral=True)
        await view.wait()
        if view.confirmed:
            sqldb.delete_music_playlist(playlist.id)
            await ctx.interaction.edit_original_response(content=f"已刪除歌單「{playlist.name}」", view=None)
        else:
            await ctx.interaction.edit_original_response(content="已取消刪除", view=None)

    @playlist.command(name="add", description="把歌曲或整份歌單網址加入個人歌單（歌單不存在時自動建立）")
    @with_identity()
    async def playlist_add(
        self,
        ctx: IdentityContext,
        name: _playlist_name_option(),
        url: discord.Option(str, name="網址", description="單曲或歌單網址（YouTube、Bilibili 等）"),
    ):
        name = playlists.clean_playlist_name(name)
        await ctx.defer(ephemeral=True)
        result = await extract_songs(url, ctx.author)
        # 擷取成功後才建立歌單，避免連結無效時留下空歌單
        playlist = playlists.get_or_create_playlist(ctx.identity.user_id, name)
        text = playlists.add_extracted(playlist, playlists.Extracted.of(result))
        await ctx.respond(text, ephemeral=True)

    @playlist.command(name="sync", description="重新擷取歌單匯入過的外部歌單（手動加入的歌曲不受影響）")
    @with_identity()
    async def playlist_sync(self, ctx: IdentityContext, name: _playlist_name_option()):
        playlist = _get_playlist(ctx.identity.user_id, name)
        sources = sqldb.get_music_playlist_sources(playlist.id)
        if not sources:
            raise MusicCommandError(f"歌單「{playlist.name}」沒有匯入過外部歌單")

        await ctx.defer(ephemeral=True)

        async def extract(url: str) -> playlists.Extracted:
            return playlists.Extracted.of(await extract_songs(url, ctx.author))

        lines = playlists.apply_sync(playlist, await playlists.fetch_sources(sources, extract))
        text = "\n".join(lines)
        await ctx.respond(text if len(text) <= 2000 else text[:1997] + "…", ephemeral=True)

    @playlist.command(name="save_current", description="把目前播放的歌存進個人歌單（歌單不存在時自動建立）")
    @commands.guild_only()
    @with_identity()
    async def playlist_save_current(self, ctx: IdentityContext, name: _playlist_name_option()):
        player = _require_player(ctx, need_playing=True)
        playlist = playlists.get_or_create_playlist(ctx.identity.user_id, name)
        await ctx.respond(playlists.save_songs(playlist, _song_rows([player.nowplaying])), ephemeral=True)

    @playlist.command(name="save_queue", description="把目前播放與待播歌單全部存進個人歌單（歌單不存在時自動建立）")
    @commands.guild_only()
    @with_identity()
    async def playlist_save_queue(self, ctx: IdentityContext, name: _playlist_name_option()):
        player = _require_player(ctx)
        songs = ([player.nowplaying] if player.nowplaying else []) + player.get_full_playlist()
        if not songs:
            raise MusicCommandError("歌單裡空無一物")
        playlist = playlists.get_or_create_playlist(ctx.identity.user_id, name)
        await ctx.respond(playlists.save_songs(playlist, _song_rows(songs)), ephemeral=True)

    @playlist.command(name="remove", description="從個人歌單刪除一首歌")
    @with_identity()
    async def playlist_remove(
        self,
        ctx: IdentityContext,
        name: _playlist_name_option(),
        index: discord.Option(int, name="編號", description="歌曲編號（可用 /playlist show 查看）", min_value=1),
    ):
        playlist = _get_playlist(ctx.identity.user_id, name)
        removed = sqldb.remove_music_playlist_song(playlist.id, index - 1)
        if not removed:
            raise MusicCommandError(f"歌單「{playlist.name}」沒有第 {index} 首歌")
        await ctx.respond(f"已從歌單「{playlist.name}」刪除 {removed.title}", ephemeral=True)

    @playlist.command(name="show", description="查看個人歌單內容")
    @with_identity()
    async def playlist_show(self, ctx: IdentityContext, name: _playlist_name_option()):
        playlist = _get_playlist(ctx.identity.user_id, name)
        songs = sqldb.get_music_playlist_songs(playlist.id)
        if not songs:
            await ctx.respond(f"歌單「{playlist.name}」裡空無一物", ephemeral=True)
            return

        title = f"{playlist.name}（{len(songs)} 首）"
        page = [BotEmbed.simple(title=title, description="") for _ in range(math.ceil(len(songs) / 10))]
        sources = sqldb.get_music_playlist_sources(playlist.id)
        if sources:
            source_lines = [f"[{playlists.source_name(s)}]({s.url})（上次同步 {format_dt(s.synced_at, 'R')}）" for s in sources]
            page[0].description = "來源：\n" + "\n".join(source_lines) + "\n\n"
        for i, song in enumerate(songs):
            page[i // 10].description += f"**{i + 1}.** [{song.title}]({song.url}) [{format_seconds(song.duration)}]\n\n"
        paginator = pages.Paginator(pages=page, use_default_buttons=True, loop_pages=True)
        await paginator.respond(ctx.interaction, ephemeral=True)

    @playlist.command(name="play", description="選擇個人歌單並播放")
    @commands.guild_only()
    @with_identity()
    async def playlist_play(
        self,
        ctx: IdentityContext,
        shuffle: discord.Option(bool, name="隨機", description="是否打亂播放順序", default=False),
    ):
        if not ctx.author.voice:
            raise MusicCommandError("請先連接到一個語音頻道")

        playlists = sqldb.get_music_playlists(ctx.identity.user_id)
        if not playlists:
            raise MusicCommandError("你還沒有歌單，請先用 /playlist create 建立")
        counts = sqldb.get_music_playlist_song_counts(ctx.identity.user_id)

        async def on_select(interaction: discord.Interaction, playlist_id: int):
            await interaction.response.edit_message(content="載入歌單中…", view=view)
            try:
                text = await play_saved_playlist(ctx, ctx.author, playlist_id, shuffle)
            except MusicCommandError as e:
                await interaction.edit_original_response(content=str(e.message), view=None)
                return
            await interaction.edit_original_response(content="已開始播放", view=None)
            await interaction.followup.send(text)

        view = MusicPlaylistSelectView(ctx.author.id, [(p.id, p.name, counts.get(p.id, 0)) for p in playlists], on_select)
        await ctx.respond("選擇要播放的歌單", view=view, ephemeral=True)


def setup(bot):
    bot.add_cog(music(bot))
