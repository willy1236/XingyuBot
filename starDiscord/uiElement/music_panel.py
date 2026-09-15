import asyncio
from collections.abc import Awaitable, Callable

import discord

from starlib import sqldb
from starlib.exceptions import MusicCommandError, MusicPlayingError

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
)
from .view import MusicPlaylistSelectView, RegisterView

PANEL_COLOR = 0xC4E9FF
QUEUE_PREVIEW = 3
QUEUE_LIST_LIMIT = 10

_LOOP_LABEL = {
    LoopMode.OFF: "循環：關閉",
    LoopMode.SONG: "循環：單首",
    LoopMode.QUEUE: "循環：整張",
}
_LOOP_STATUS = {
    LoopMode.OFF: "",
    LoopMode.SONG: "🔂 單首循環",
    LoopMode.QUEUE: "🔁 整張循環",
}
_NEXT_LOOP_MODE = {
    LoopMode.OFF: LoopMode.SONG,
    LoopMode.SONG: LoopMode.QUEUE,
    LoopMode.QUEUE: LoopMode.OFF,
}

# 播放器按鈕的動作：回傳要私下回覆按下的人的訊息（None 表示不回覆）
PanelAction = Callable[[discord.Interaction, MusicPlayer], Awaitable[str | None]]
# 點歌、歌單按鈕的動作：自行回應 interaction
PanelHandler = Callable[[discord.Interaction], Awaitable[None]]


def _truncate(text: str) -> str:
    return text if len(text) <= 2000 else text[:1997] + "…"


async def _check_voice(interaction: discord.Interaction, *, can_join: bool) -> bool:
    """確認按下的人跟機器人同語音頻道；can_join 時機器人不在頻道也可以（之後會自動加入）。"""
    voice_client = interaction.guild.voice_client
    try:
        if can_join and not voice_client:
            if not interaction.user.voice:
                raise MusicCommandError("請先連接到一個語音頻道")
        else:
            await ensure_author_voice(voice_client, interaction.user, auto_join=False)
    except MusicCommandError as e:
        await interaction.response.send_message(str(e.message), ephemeral=True)
        return False
    return True


class MusicPanelView(discord.ui.DesignerView):
    """音樂控制面板（Components V2），只有跟機器人同語音頻道的人能操作；沒在播放時只顯示點歌與個人歌單"""

    def __init__(self, guild_id: int):
        super().__init__(timeout=600, disable_on_timeout=True)
        self.guild_id = guild_id
        self.rebuild()

    def _player(self) -> MusicPlayer | None:
        player = get_player(self.guild_id)
        return player if player and not player.closing else None

    def rebuild(self):
        self.clear_items()
        player = self._player()
        add_row = discord.ui.ActionRow(
            self._handler_button("➕", "點歌", self._open_add_song, style=discord.ButtonStyle.primary),
            self._handler_button("📂", "我的歌單", self._open_playlists),
        )
        if not player:
            add_row.add_item(self._refresh_button())
            self.add_item(discord.ui.Container(discord.ui.TextDisplay("### 音樂播放器\n目前沒有播放中的歌曲，按「點歌」開始播放"), add_row, color=PANEL_COLOR))
            return

        self.add_item(
            discord.ui.Container(
                self._nowplaying_item(player),
                discord.ui.Separator(),
                discord.ui.TextDisplay(self._queue_text(player)),
                discord.ui.ActionRow(
                    self._button("▶️", "繼續", self._pause) if player.vc.is_paused() else self._button("⏸️", "暫停", self._pause),
                    self._button("⏭️", "跳過", self._skip),
                    self._button("⏹️", "停止", self._stop, style=discord.ButtonStyle.danger),
                    self._refresh_button(),
                ),
                discord.ui.ActionRow(
                    self._button("🔁", _LOOP_LABEL[player.loop_mode], self._loop),
                    self._button("🔀", "洗牌", self._shuffle),
                    self._button("📜", "待播清單", self._queue),
                ),
                add_row,
                color=PANEL_COLOR,
            )
        )

    def _nowplaying_item(self, player: MusicPlayer) -> discord.ui.ViewItem:
        song = player.nowplaying
        if not song:
            return discord.ui.TextDisplay("### 現在播放\n目前沒有播放中的歌曲")

        title = f"### 現在播放\n[{song.title}]({song.url})\n點歌：{song.requester.mention} · {format_seconds(song.duration)}"
        progress_bar, progress_text = format_progress_bar(player.get_elapsed_seconds(), song.duration)
        status = [s for s in ("⏸️ 已暫停" if player.vc.is_paused() else "", _LOOP_STATUS[player.loop_mode]) if s]
        progress = f"{progress_bar} {progress_text}" + (f"\n{' · '.join(status)}" if status else "")
        if not song.thumbnail:
            return discord.ui.TextDisplay(f"{title}\n{progress}")
        return discord.ui.Section(discord.ui.TextDisplay(title), discord.ui.TextDisplay(progress), accessory=discord.ui.Thumbnail(song.thumbnail))

    @staticmethod
    def _queue_text(player: MusicPlayer) -> str:
        queue = player.get_full_playlist()
        if not queue:
            return "**接下來**\n沒有待播歌曲"
        lines = [f"{i + 1}. {song.title} [{format_seconds(song.duration)}]" for i, song in enumerate(queue[:QUEUE_PREVIEW])]
        return "**接下來**\n" + "\n".join(lines) + f"\n-# 共 {len(queue)} 首待播"

    def _button(self, emoji: str, label: str, action: PanelAction, style=discord.ButtonStyle.secondary) -> discord.ui.Button:
        async def handler(interaction: discord.Interaction):
            if await _check_voice(interaction, can_join=False):
                await self._run(interaction, action)

        return self._make_button(emoji, label, handler, style)

    def _handler_button(self, emoji: str, label: str, handler: PanelHandler, style=discord.ButtonStyle.secondary) -> discord.ui.Button:
        async def checked(interaction: discord.Interaction):
            if await _check_voice(interaction, can_join=True):
                await handler(interaction)

        return self._make_button(emoji, label, checked, style)

    def _refresh_button(self) -> discord.ui.Button:
        # 重新整理不改變播放狀態，任何人都能按
        async def handler(interaction: discord.Interaction):
            self.rebuild()
            await interaction.response.edit_message(view=self)

        return self._make_button("🔄", "重新整理", handler, discord.ButtonStyle.secondary)

    @staticmethod
    def _make_button(emoji: str, label: str, callback: PanelHandler, style) -> discord.ui.Button:
        button = discord.ui.Button(emoji=emoji, label=label, style=style)
        button.callback = callback
        return button

    def disable_all_items(self, *, exclusions=None):
        # 預設只停用最外層元件，面板的按鈕都包在 Container 裡
        for item in self.walk_children():
            if hasattr(item, "disabled") and (exclusions is None or item not in exclusions):
                item.disabled = True
        return self

    async def refresh_message(self, message: discord.Message | None):
        """點歌等非同步操作完成後重畫面板訊息。"""
        if not message or self.is_finished():
            return
        self.rebuild()
        try:
            await message.edit(view=self)
        except discord.HTTPException:
            pass

    async def _run(self, interaction: discord.Interaction, action: PanelAction):
        # 面板過時（播放器已結束）時只重畫成閒置狀態
        player = self._player()
        text = await action(interaction, player) if player else None
        self.rebuild()
        await interaction.response.edit_message(view=self)
        if text:
            await interaction.followup.send(text, ephemeral=True)

    async def _open_add_song(self, interaction: discord.Interaction):
        await interaction.response.send_modal(AddSongModal(self, interaction.message))

    async def _open_playlists(self, interaction: discord.Interaction):
        cuser = sqldb.get_cloud_user_by_discord(interaction.user.id)
        if not cuser:
            embed = discord.Embed(title="📝 註冊帳號", description="歡迎使用本服務！在開始之前，請先建立新帳號或綁定原有帳號", color=discord.Color.blue())
            await interaction.response.send_message(embed=embed, view=RegisterView(), ephemeral=True)
            return

        playlists = sqldb.get_music_playlists(cuser.id)
        if not playlists:
            await interaction.response.send_message("你還沒有歌單，請先用 /playlist create 建立", ephemeral=True)
            return
        counts = sqldb.get_music_playlist_song_counts(cuser.id)
        panel_message = interaction.message

        async def on_select(select_interaction: discord.Interaction, playlist_id: int):
            await select_interaction.response.edit_message(content="載入歌單中…", view=view)
            try:
                text = await play_saved_playlist(select_interaction, select_interaction.user, playlist_id, shuffle=False)
            except (MusicCommandError, MusicPlayingError) as e:
                await select_interaction.edit_original_response(content=str(e.message), view=None)
                return
            await select_interaction.edit_original_response(content="已開始播放", view=None)
            await select_interaction.followup.send(text)
            await self.refresh_message(panel_message)

        view = MusicPlaylistSelectView(interaction.user.id, [(p.id, p.name, counts.get(p.id, 0)) for p in playlists], on_select)
        await interaction.response.send_message("選擇要播放的歌單", view=view, ephemeral=True)

    @staticmethod
    async def _pause(interaction: discord.Interaction, player: MusicPlayer) -> str | None:
        if not player.nowplaying:
            return "目前沒有播放中的歌曲"
        player.pause()
        return None

    @staticmethod
    async def _skip(interaction: discord.Interaction, player: MusicPlayer) -> str | None:
        if not player.nowplaying:
            return "目前沒有播放中的歌曲"
        return player.skip_song(interaction.user)

    @staticmethod
    async def _stop(interaction: discord.Interaction, player: MusicPlayer) -> str | None:
        await player.close()
        return "已停止播放並離開頻道"

    @staticmethod
    async def _loop(interaction: discord.Interaction, player: MusicPlayer) -> str | None:
        player.loop_mode = _NEXT_LOOP_MODE[player.loop_mode]
        return None

    @staticmethod
    async def _shuffle(interaction: discord.Interaction, player: MusicPlayer) -> str | None:
        player.shuffle()
        return "歌單已隨機🔀"

    @staticmethod
    async def _queue(interaction: discord.Interaction, player: MusicPlayer) -> str | None:
        queue = player.get_full_playlist()
        if not queue:
            return "歌單裡空無一物"
        lines = [
            f"**{i + 1}.** [{song.title}](<{song.url}>) [{song.requester.mention}/{format_seconds(song.duration)}]"
            for i, song in enumerate(queue[:QUEUE_LIST_LIMIT])
        ]
        if len(queue) > QUEUE_LIST_LIMIT:
            lines.append(f"-# 還有 {len(queue) - QUEUE_LIST_LIMIT} 首，完整清單請用 /queue")
        return _truncate("\n".join(lines))


class AddSongModal(discord.ui.Modal):
    """面板的點歌輸入框，行為同 /play：擷取成功後才加入語音頻道"""

    def __init__(self, panel: MusicPanelView, panel_message: discord.Message | None):
        super().__init__(title="點歌")
        self.panel = panel
        self.panel_message = panel_message
        self.add_item(discord.ui.InputText(label="歌曲或歌單網址", placeholder="YouTube、Bilibili 等網址"))

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        url = self.children[0].value.strip()
        try:
            result = await extract_songs(url, interaction.user)
            vc = await ensure_author_voice(interaction.guild.voice_client, interaction.user, auto_join=True)
            if vc.is_recording():
                raise MusicCommandError("正在錄音時無法播放音樂")
            text = await enqueue_and_play(vc, interaction, asyncio.get_running_loop(), result.songs, result.skipped)
        except (MusicCommandError, MusicPlayingError) as e:
            await interaction.followup.send(str(e.message), ephemeral=True)
            return
        await interaction.followup.send(text)
        await self.panel.refresh_message(self.panel_message)
