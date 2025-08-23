from datetime import date, datetime, timedelta, timezone

import discord
from discord import Bot
from sqlalchemy import BigInteger, Boolean, ForeignKey, ForeignKeyConstraint, Identity, Integer, Interval, SmallInteger, String, Text, Date
from sqlalchemy.dialects.postgresql import TIMESTAMP, CIDR, MACADDR
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlmodel import Field, Relationship

from ..base import ListObject
from ..fileDatabase import Jsondb
from ..settings import tz
from ..types import *
from ..utils import BotEmbed
from .sqlSchema import *


class CloudUser(UserSchema):
    __tablename__ = "cloud_user"

    id: str | None = mapped_column(String, primary_key=True, default=None)
    discord_id: int = mapped_column(BigInteger, primary_key=True, autoincrement=False, default=None)
    email: str | None = mapped_column(String, default=None)
    drive_share_id: str | None = mapped_column(String, default=None)
    twitch_id: int | None = mapped_column(Integer, unique=True, default=None)
    name: str | None = mapped_column(String, default=None)
    privilege_level: PrivilegeLevel = mapped_column(SmallInteger, default=PrivilegeLevel.User, nullable=True)


class DiscordUser(UserSchema):
    __tablename__ = "user_discord"

    discord_id: int = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    max_sign_consecutive_days: int | None = mapped_column(Integer, default=None)
    meatball_times: int | None = mapped_column(Integer, default=None)
    guaranteed: int | None = mapped_column(Integer, default=None)
    registrations_id: int | None = mapped_column(Integer, ForeignKey("stardb_idbase.discord_registrations.registrations_id"), default=None)

    registration: "DiscordRegistration" = relationship(back_populates="members", init=False)


class UserPoint(UserSchema):
    __tablename__ = "user_point"

    discord_id: int = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    stardust: int = mapped_column(Integer, default=0)
    point: int = mapped_column(Integer, default=0)
    rcoin: int = mapped_column(Integer, default=0)

class UserBet(UserSchema):
    __tablename__ = "user_bet"

    bet_id: int = mapped_column(BigInteger, primary_key=True)
    discord_id: int = mapped_column(BigInteger, primary_key=True)
    bet_option: int = mapped_column(SmallInteger)
    bet_amount: int = mapped_column(Integer)
    bet_at: datetime = mapped_column(TIMESTAMP(True, 0))

class UserGame(UserSchema):
    __tablename__ = "game_data"

    discord_id: int = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    game: GameType = mapped_column(SmallInteger, primary_key=True, autoincrement=False)
    player_name: str = mapped_column(String)
    player_id: str | None = mapped_column(String)
    account_id: str | None = mapped_column(String)
    other_id: str | None = mapped_column(String)


class UserPoll(UserSchema):
    __tablename__ = "user_poll"

    poll_id: int = mapped_column(Integer, primary_key=True)
    discord_id: int = mapped_column(BigInteger, primary_key=True)
    vote_option: int = mapped_column(Integer, primary_key=True)
    vote_at: datetime = mapped_column(TIMESTAMP(True, 0))
    vote_magnification: int = mapped_column(Integer, default=1)

class UserAccount(UserSchema):
    __tablename__ = "user_account"

    main_account: int = mapped_column(BigInteger, primary_key=True)
    alternate_account: int = mapped_column(BigInteger, primary_key=True)

class UserParty(UserSchema):
    __tablename__ = "user_party"

    discord_id: int = mapped_column(BigInteger, primary_key=True)
    party_id: int = mapped_column(Integer, ForeignKey("stardb_idbase.party_datas.party_id"), primary_key=True)

    party: "Party" = relationship(back_populates="members", init=False)

class UserModerate(UserSchema):
    __tablename__ = "user_moderate"

    warning_id: int = Base.auto_id_column()
    discord_id: int = mapped_column(BigInteger)
    moderate_type: WarningType = mapped_column(Integer)
    moderate_user: int = mapped_column(BigInteger)
    create_guild: int = mapped_column(BigInteger)
    create_time: datetime = mapped_column(TIMESTAMP(True, 0))
    reason: str | None = mapped_column(String)
    last_time: timedelta | None = mapped_column(Interval)
    guild_only: bool | None = mapped_column(Boolean)
    officially_given: bool | None = mapped_column(Boolean)

    def embed(self, bot: Bot) -> discord.Embed:
        user = bot.get_user(self.discord_id)
        moderate_user = bot.get_user(self.moderate_user)
        guild = bot.get_guild(self.create_guild)

        name = f"{user.name if user else f'<@{self.discord_id}>'} 的警告單"
        description = f"**編號：{self.warning_id}（{Jsondb.get_tw(self.moderate_type, 'warning_type')}）**\n- 被警告用戶：{user.mention if user else f'<@{self.discord_id}>'}\n- 管理員：{guild.name if guild else self.create_guild}/{moderate_user.mention if moderate_user else f'<@{self.moderate_user}>'}\n- 原因：{self.reason}\n- 時間：{self.create_time}"
        if self.last_time:
            description += f"\n- 禁言時長：{self.last_time}"
        if self.officially_given:
            description += "\n- 官方認證警告"
        if self.guild_only:
            description += "\n- 伺服器內警告"
        embed = BotEmbed.general(
            name=name,
            icon_url=user.display_avatar.url if user else None,
            description=description,
        )
        return embed

    def display_embed_field(self, bot: Bot) -> tuple[str, str]:
        moderate_user = bot.get_user(self.moderate_user)
        guild = bot.get_guild(self.create_guild)
        name = f"編號：{self.warning_id}（{Jsondb.get_tw(self.moderate_type, 'warning_type')}）"
        value = f"{guild.name if guild else self.create_guild}/{moderate_user.mention if moderate_user else f'<@{self.moderate_user}>'}\n{self.reason}\n{self.create_time}"
        if self.officially_given:
            value += "官方認證警告"
        if self.guild_only:
            value += "伺服器內警告"
        return name, value


class RoleSave(UserSchema):
    __tablename__ = "role_save"

    discord_id: int = mapped_column(BigInteger, primary_key=True)
    role_id: int = mapped_column(BigInteger, primary_key=True)
    role_name: str = mapped_column(String)
    time: date = mapped_column(Date)


class Pet(UserSchema):
    __tablename__ = "user_pet"

    discord_id: int = mapped_column(BigInteger, primary_key=True)
    pet_species: str = mapped_column(String)
    pet_name: str = mapped_column(String)
    food: int | None = mapped_column(Integer)

class LOLGameRecord(UserSchema):
    __tablename__ = "lol_game_record"

    puuid: str = mapped_column(String, primary_key=True)
    game_id: int = mapped_column(Integer, primary_key=True)
    game_type: str = mapped_column(String)
    game_mode: str = mapped_column(String)
    champion_id: int = mapped_column(Integer)
    teamId: int = mapped_column(SmallInteger)
    timePlayed: timedelta = mapped_column(Interval)
    totalTimeSpentDead: timedelta = mapped_column(Interval)
    created_at: datetime = mapped_column(TIMESTAMP(True, 0))
    win: bool = mapped_column(Boolean)
    kills: int = mapped_column(Integer)
    deaths: int = mapped_column(Integer)
    assists: int = mapped_column(Integer)
    visionScore: int = mapped_column(Integer)
    damage_dealt: int = mapped_column(Integer)
    damage_taken: int = mapped_column(Integer)
    double_kills: int = mapped_column(Integer)
    triple_kills: int = mapped_column(Integer)
    quadra_kills: int = mapped_column(Integer)
    penta_kills: int = mapped_column(Integer)
    gold_earned: int = mapped_column(Integer)
    total_minions_killed: int = mapped_column(Integer)
    turretKills: int = mapped_column(Integer)
    inhibitorKills: int = mapped_column(Integer)
    baronKills: int = mapped_column(Integer)
    dragonKills: int = mapped_column(Integer)
    item0: int = mapped_column(Integer)
    item1: int = mapped_column(Integer)
    item2: int = mapped_column(Integer)
    item3: int = mapped_column(Integer)
    item4: int = mapped_column(Integer)
    item5: int = mapped_column(Integer)
    item6: int = mapped_column(Integer)
    firstBloodKill: bool = mapped_column(Boolean)
    firstTowerKill: bool = mapped_column(Boolean)
    allInPings: int = mapped_column(Integer)
    assistMePings: int = mapped_column(Integer)
    basicPings: int = mapped_column(Integer)
    commandPings: int = mapped_column(Integer)
    dangerPings: int = mapped_column(Integer)
    enemyMissingPings: int = mapped_column(Integer)
    enemyVisionPings: int = mapped_column(Integer)
    getBackPings: int = mapped_column(Integer)
    holdPings: int = mapped_column(Integer)
    needVisionPings: int = mapped_column(Integer)
    onMyWayPings: int = mapped_column(Integer)
    pushPings: int = mapped_column(Integer)
    retreatPings: int = mapped_column(Integer)
    visionClearedPings: int = mapped_column(Integer)

class TwitchPoint(UserSchema):
    __tablename__ = "twitch_point"

    twitch_id: int = mapped_column(primary_key=True)
    broadcaster_id: int = mapped_column(primary_key=True)
    point: int = mapped_column(default=0)


class Community(AlchemyBasicSchema):
    __tablename__ = "community_info"

    id: str = mapped_column(String, primary_key=True)
    type: CommunityType = mapped_column(Integer, primary_key=True)
    username: str = mapped_column(String)
    display_name: str | None = mapped_column(String)


class NotifyChannel(AlchemyBasicSchema):
    __tablename__ = "notify_channel"

    guild_id: int = mapped_column(BigInteger, primary_key=True)
    notify_type: NotifyChannelType = mapped_column(Integer, primary_key=True)
    channel_id: int = mapped_column(BigInteger)
    role_id: int | None = mapped_column(BigInteger)
    message: str | None = mapped_column(String)

class NotifyCommunity(AlchemyBasicSchema):
    __tablename__ = "notify_community"

    notify_type: NotifyCommunityType = mapped_column(Integer, primary_key=True)
    community_id: str = mapped_column(String, primary_key=True)
    community_type: CommunityType = mapped_column(Integer, primary_key=True)
    guild_id: int = mapped_column(BigInteger, primary_key=True)
    channel_id: int = mapped_column(BigInteger)
    role_id: int | None = mapped_column(BigInteger)
    message: str | None = mapped_column(String)

class DynamicVoiceLobby(AlchemyBasicSchema):
    __tablename__ = "dynamic_voice_lobby"

    guild_id: int = mapped_column(BigInteger, primary_key=True)
    channel_id: int = mapped_column(BigInteger)
    default_room_name: str | None = mapped_column(String)

class DynamicVoice(AlchemyBasicSchema):
    __tablename__ = "dynamic_channel"

    channel_id: int = mapped_column(BigInteger, primary_key=True)
    creator_id: int = mapped_column(BigInteger)
    guild_id: int = mapped_column(BigInteger)
    password: str | None = mapped_column(String)


class Bet(AlchemyBasicSchema):
    __tablename__ = "bet_data"

    bet_id: int = mapped_column(BigInteger, primary_key=True)
    title: str = mapped_column(String)
    blue_title: str = mapped_column(String)
    pink_title: str = mapped_column(String)
    is_on: bool = mapped_column(Boolean)
    created_at: datetime = mapped_column(TIMESTAMP(True, 0))


class Poll(AlchemyBasicSchema):
    __tablename__ = "poll_data"

    poll_id: int = Base.auto_id_column()
    title: str = mapped_column(String)
    creator_id: int = mapped_column(BigInteger)
    created_at: datetime = mapped_column(TIMESTAMP(True, 0))
    guild_id: int = mapped_column(BigInteger)
    message_id: int | None = mapped_column(BigInteger)
    end_at: datetime | None = mapped_column(TIMESTAMP(True, 0), default=None)
    number_of_user_votes: int | None = mapped_column(Integer, default=0)
    ban_alternate_account_voting: bool | None = mapped_column(Boolean, default=False)
    show_name: bool | None = mapped_column(Boolean, default=False)
    check_results_in_advance: bool | None = mapped_column(Boolean, default=True)
    results_only_initiator: bool | None = mapped_column(Boolean, default=False)
    can_change_vote: bool | None = mapped_column(Boolean, default=True)


class PollOption(AlchemyBasicSchema):
    __tablename__ = "poll_options"

    poll_id: int = mapped_column(Integer, primary_key=True)
    option_id: int = mapped_column(Integer, primary_key=True)
    option_name: str = mapped_column(String)

class PollRole(AlchemyBasicSchema):
    __tablename__ = "poll_role"

    poll_id: int = mapped_column(Integer, primary_key=True)
    role_id: int = mapped_column(BigInteger, primary_key=True)
    is_only_role: bool = mapped_column(Boolean)
    role_magnification: int = mapped_column(Integer)

class TwitchBotJoinChannel(AlchemyBasicSchema):
    __tablename__ = "twitch_bot_join_channel"

    twitch_id: int = mapped_column(Integer, primary_key=True)
    action_channel_id: int | None = mapped_column(BigInteger)
    point_name: str | None = mapped_column(String)


class TwitchChatCommand(AlchemyBasicSchema):
    __tablename__ = "twitch_chat_command"

    twitch_id: int = mapped_column(Integer, primary_key=True)
    name: str = mapped_column(String, primary_key=True)
    response: str = mapped_column(String)


class InviteRecord(AlchemyBasicSchema):
    __tablename__ = "invite_record"

    invited_user: int = mapped_column(BigInteger, primary_key=True)
    invite_guild: int = mapped_column(BigInteger, primary_key=True)
    inviter_user: int = mapped_column(BigInteger, primary_key=True)
    invite_time: datetime = mapped_column(TIMESTAMP(True, 0))
    invite_code: str = mapped_column(String)


class PushRecord(AlchemyBasicSchema):
    __tablename__ = "push_record"

    channel_id: str = mapped_column(String, primary_key=True)
    push_at: datetime = mapped_column(TIMESTAMP(True, 0), default=datetime.min.replace(tzinfo=timezone.utc))
    expire_at: datetime = mapped_column(TIMESTAMP(True, 0), default=datetime.min.replace(tzinfo=timezone.utc))
    secret: str | None = mapped_column(String, default=None)

    @property
    def is_expired(self) -> bool:
        return self.expire_at < datetime.now(tz=tz) if self.expire_at else True


class ReactionRoleMessage(AlchemyBasicSchema):
    __tablename__ = "reaction_role_message"

    guild_id: int = mapped_column(BigInteger, primary_key=True)
    channel_id: int = mapped_column(BigInteger, primary_key=True)
    message_id: int = mapped_column(BigInteger, primary_key=True)


class ReactionRole(AlchemyBasicSchema):
    __tablename__ = "reaction_role"

    message_id: int = mapped_column(BigInteger, primary_key=True)
    role_id: int = mapped_column(BigInteger, primary_key=True)
    title: str = mapped_column(String)
    description: str | None = mapped_column(String)
    emoji: str | None = mapped_column(String)
    style: int | None = mapped_column(Integer)


class Giveaway(AlchemyBasicSchema):
    __tablename__ = "giveaway_data"

    id: int = mapped_column(Integer, Identity(), primary_key=True)
    guild_id: int = mapped_column(BigInteger)
    channel_id: int = mapped_column(BigInteger)
    message_id: int | None = mapped_column(BigInteger)
    creator_id: int = mapped_column(BigInteger)
    prize_name: str = mapped_column(String)
    winner_count: int = mapped_column(Integer)
    created_at: datetime = mapped_column(TIMESTAMP(True, 0))
    end_at: datetime | None = mapped_column(TIMESTAMP(True, 0))
    is_on: bool = mapped_column(Boolean, default=True)
    description: str | None = mapped_column(String, default=None)
    redraw_count: int = mapped_column(Integer, default=0)


class GiveawayUser(UserSchema):
    __tablename__ = "user_giveaway"

    giveaway_id: int = mapped_column(BigInteger, primary_key=True)
    user_id: int = mapped_column(BigInteger, primary_key=True)
    user_weight: int = mapped_column(Integer)
    join_at: datetime = mapped_column(TIMESTAMP(True, 0))
    is_winner: bool = mapped_column(Boolean, default=False)


class User(AlchemyBasicSchema):
    __tablename__ = "users"

    id: int = Base.auto_id_column()
    name: str = mapped_column(String, nullable=False)
    age: int = mapped_column(Integer, nullable=False)

    # 建立關聯：一個使用者對應多篇貼文
    posts: list["Post"] = relationship(back_populates="user", init=False)


class Post(AlchemyBasicSchema):
    __tablename__ = "posts"

    id: Mapped[int] = Base.auto_id_column()
    title: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(precision=0), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey(User.id), nullable=False)  # type: ignore
    tags: Mapped[str | None] = mapped_column(String, default=None)

    # 建立反向關聯
    user: User = relationship(back_populates="posts", init=False)


class ServerConfig(AlchemyBasicSchema):
    __tablename__ = "server_config"

    guild_id: int = mapped_column(BigInteger, primary_key=True)
    timeout_after_warning_times: int | None = mapped_column(Integer)

class MemorialDay(AlchemyBasicSchema):
    __tablename__ = "memorial_days"

    day_id: int = mapped_column(Integer, Identity(), primary_key=True)
    discord_id: int = mapped_column(BigInteger)
    target_date: date = mapped_column(Date)
    name: str = mapped_column(String)

class IPLastSeen(AlchemyBasicSchema):
    __tablename__ = "ip_last_seen"

    ip: str = mapped_column(CIDR, primary_key=True)
    last_seen: datetime = mapped_column(TIMESTAMP(True, 0))
    mac: str | None = mapped_column(MACADDR)
    discord_id: int | None = mapped_column(BigInteger, default=None)
    name: str | None = mapped_column(String, default=None)

class Party(IdbaseSchema):
    __tablename__ = "party_datas"

    party_id: int = mapped_column(primary_key=True)
    party_name: str = mapped_column(String)
    role_id: int = mapped_column(BigInteger)
    creator_id: int = mapped_column(BigInteger)
    created_at: date = mapped_column(Date)

    members: list[UserParty] = relationship(back_populates="party", init=False)

class DiscordRegistration(IdbaseSchema):
    __tablename__ = "discord_registrations"

    registrations_id: int = mapped_column(primary_key=True)
    guild_id: int = mapped_column(BigInteger)
    role_id: int = mapped_column(BigInteger)

    members: list[DiscordUser] = relationship(back_populates="registration", init=False)


class TRPGStoryPlot(IdbaseSchema):
    __tablename__ = "trpg_storyplots"

    id: int = mapped_column(primary_key=True)
    title: str = mapped_column(String)
    content: str = mapped_column(Text)
    options: list["TRPGStoryOption"] = relationship(back_populates="plot", init=False)


class TRPGStoryOption(IdbaseSchema):
    __tablename__ = "trpg_plot_options"

    plot_id: int = mapped_column(ForeignKey("stardb_idbase.trpg_storyplots.id"), primary_key=True)
    option_id: int = mapped_column(primary_key=True)
    option_title: str = mapped_column(String)
    lead_to_plot: int | None = mapped_column(Integer)
    check_ability: int | None = mapped_column(Integer)
    san_check_fall_dice: str | None = mapped_column(String)
    success_plot: int | None = mapped_column(Integer)
    fail_plot: int | None = mapped_column(Integer)
    plot: TRPGStoryPlot = relationship(back_populates="options", init=False)


class TRPGCharacter(IdbaseSchema):
    __tablename__ = "trpg_characters"

    discord_id: int = mapped_column(BigInteger, primary_key=True)
    character_name: str = mapped_column(String)

    abilities: list["TRPGCharacterAbility"] = relationship(back_populates="character", init=False)


class TRPGCharacterAbility(IdbaseSchema):
    __tablename__ = "trpg_character_abilities"

    discord_id: int = mapped_column(BigInteger, ForeignKey("stardb_idbase.trpg_characters.discord_id"), primary_key=True)
    ability_id: int = mapped_column(ForeignKey("stardb_idbase.trpg_abilities.ability_id"), primary_key=True)
    san_lower_limit: int | None = mapped_column(Integer)
    value: int = mapped_column(Integer)

    character: TRPGCharacter = relationship(back_populates="abilities", init=False)
    ability: "TRPGAbility" = relationship(back_populates="characters", init=False)


class TRPGAbility(IdbaseSchema):
    __tablename__ = "trpg_abilities"

    ability_id: int = mapped_column(primary_key=True)
    ability_name: str = mapped_column(String)

    characters: list[TRPGCharacterAbility] = relationship(back_populates="ability", init=False)


class BackupRole(AlchemyBackupSchema):
    __tablename__ = "roles_backup"

    role_id: int = mapped_column(BigInteger, primary_key=True)
    role_name: str = mapped_column(String)
    created_at: datetime = mapped_column(TIMESTAMP(True, 0))
    guild_id: int = mapped_column(BigInteger)
    colour_r: int = mapped_column(Integer)
    colour_g: int = mapped_column(Integer)
    colour_b: int = mapped_column(Integer)
    description: str = mapped_column(String)

    members: list["BackupRoleUser"] = relationship(back_populates="role", init=False)

    def embed(self, bot:Bot):
        embed = BotEmbed.simple(self.role_name,self.description)
        embed.add_field(name="創建於", value=self.created_at.strftime("%Y/%m/%d %H:%M:%S"))
        embed.add_field(name="顏色", value=f"({self.colour_r}, {self.colour_g}, {self.colour_b})")
        if bot and self.members:
            user_list = list()
            for user in self.members:
                user = bot.get_user(user.discord_id)
                if user:
                    user_list.append(user.mention)
            embed.add_field(name="成員", value=",".join(user_list),inline=False)

        return embed

class BackupRoleUser(AlchemyBackupSchema):
    __tablename__ = "role_user_backup"

    role_id: int = mapped_column(BigInteger, ForeignKey("stardb_backup.roles_backup.role_id"), primary_key=True)
    discord_id: int = mapped_column(BigInteger, primary_key=True)
    role: BackupRole = relationship(back_populates="members", init=False)

class BackupCategory(AlchemyBackupSchema):
    __tablename__ = "category_backup"

    category_id: int = mapped_column(BigInteger, primary_key=True)
    name: str = mapped_column(String)
    created_at: datetime = mapped_column(TIMESTAMP(True, 0))
    guild_id: int = mapped_column(BigInteger)
    description: str | None = mapped_column(String)

    def embed(self, bot: Bot):
        embed = BotEmbed.simple(self.name, self.description)
        embed.add_field(name="創建於", value=self.created_at.strftime("%Y/%m/%d %H:%M:%S"))
        return embed


class BackupChannel(AlchemyBackupSchema):
    __tablename__ = "channel_backup"

    channel_id: int = mapped_column(BigInteger, primary_key=True)
    name: str = mapped_column(String)
    created_at: datetime = mapped_column(TIMESTAMP(True, 0))
    guild_id: int = mapped_column(BigInteger)
    category_id: int | None = mapped_column(BigInteger)
    description: str | None = mapped_column(String)

    def embed(self, bot: Bot):
        embed = BotEmbed.simple(self.name, self.description)
        embed.add_field(name="創建於", value=self.created_at.strftime("%Y/%m/%d %H:%M:%S"))
        return embed


class BackupMessage(AlchemyBackupSchema):
    __tablename__ = "message_backup"

    message_id: int = mapped_column(BigInteger, primary_key=True)
    channel_id: int = mapped_column(BigInteger, primary_key=True)
    content: str | None = mapped_column(Text)
    created_at: datetime = mapped_column(TIMESTAMP(True, 0))
    author_id: int = mapped_column(BigInteger)
    description: str | None = mapped_column(String)

    def embed(self, bot: Bot):
        user = bot.get_user(self.author_id)
        embed = BotEmbed.simple(f"Message from {user.name if user else self.author_id}", self.content or "No content")
        embed.add_field(name="Created at", value=self.created_at.strftime("%Y/%m/%d %H:%M:%S"))
        return embed

class UsersCountRecord(AlchemyBackupSchema):
    __tablename__ = "users_count_backup"

    record_date: date = mapped_column(Date, primary_key=True)
    shard_id: int | None = mapped_column(SmallInteger)
    users_count: int = mapped_column(Integer)
    servers_count: int = mapped_column(Integer)

class OAuth2Token(TokensSchema):
    __tablename__ = "oauth_token"

    user_id: str = mapped_column(String, primary_key=True)
    type: CommunityType = mapped_column(Integer, primary_key=True)
    access_token: str = mapped_column(String)
    refresh_token: str | None = mapped_column(String)
    expires_at: datetime = mapped_column(TIMESTAMP(True, 0))

    @property
    def valid(self):
        return self.expires_at > datetime.now(tz)


class BotToken(TokensSchema):
    __tablename__ = "bot_token"

    api_type: APIType = mapped_column(SmallInteger, primary_key=True)
    token_seq: int = mapped_column(SmallInteger, primary_key=True)
    client_id: str | None = mapped_column(String)
    client_secret: str | None = mapped_column(String)
    access_token: str | None = mapped_column(String)
    refresh_token: str | None = mapped_column(String)
    revoke_token: str | None = mapped_column(String)
    redirect_uri: str | None = mapped_column(String)
    callback_uri: str | None = mapped_column(String)
    expires_at: datetime | None = mapped_column(TIMESTAMP(True, 0))


class CommunityCache(CacheSchema):
    """社群快取資料表"""

    __tablename__ = "community_cache"

    notify_type: NotifyCommunityType = mapped_column(Integer, primary_key=True)
    community_id: str = mapped_column(String, primary_key=True)
    value: datetime = mapped_column(TIMESTAMP(True, 0))


class NotifyCache(CacheSchema):
    """通知快取資料表"""

    __tablename__ = "notify_cache"

    notify_type: NotifyChannelType = mapped_column(Integer, primary_key=True)
    value: datetime = mapped_column(TIMESTAMP(True, 0))

class YoutubeCache(CacheSchema):
    """YouTube快取資料表"""

    __tablename__ = "youtube_cache"

    video_id: str = mapped_column(String, primary_key=True)
    scheduled_live_start: datetime = mapped_column(TIMESTAMP(True, 0))

class LOLGameCache(CacheSchema):
    """LOL遊戲快取資料表"""

    __tablename__ = "lol_game_cache"

    puuid: str = mapped_column(String, primary_key=True)
    newest_game_time: datetime = mapped_column(TIMESTAMP(True, 0))

class WarningList(ListObject[UserModerate]):
    def __init__(self, items: list[UserModerate], discord_id: int):
        super().__init__(items)
        self.discord_id = discord_id

    def display(self, bot: Bot, user: discord.User | None = None) -> discord.Embed:
        """生成警告單列表的嵌入消息

        Args:
            bot (Bot): 由Bot取得使用者與伺服器訊息
            user (discord.User | None, optional): 若機器人找不到使用者，則使用此參數指定使用者。預設為None。

        Returns:
            discord.Embed
        """
        user = bot.get_user(self.discord_id) or user
        embed = BotEmbed.general(
            f"{user.name if user else f'<@{self.discord_id}>'} 的警告單列表（共{len(self.items)}筆）",
            user.display_avatar.url if user else None,
        )
        for i in self.items:
            name, value = i.display_embed_field(bot)
            embed.add_field(name=name, value=value)
        return embed
