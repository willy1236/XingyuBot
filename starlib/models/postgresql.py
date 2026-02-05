from datetime import date, datetime, timedelta, timezone
from typing import Any

import discord
from sqlalchemy import JSON, BigInteger, Boolean, Column, Date, ForeignKey, ForeignKeyConstraint, Identity, Integer, Interval, SmallInteger, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, CIDR, MACADDR, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlmodel import Field, Relationship, text

from ..base import ListObject
from ..fileDatabase import Jsondb
from ..settings import tz
from ..types import *
from ..utils import BotEmbed
from .sqlSchema import *


class CloudUserOld(UserSchema, table=True):
    __tablename__ = "cloud_user"

    id: str | None = Field(sa_column=Column(String, unique=True))
    discord_id: int = Field(sa_column=Column(BigInteger, primary_key=True, autoincrement=False))
    drive_gmail: str | None = Field(sa_column=Column(String))
    drive_share_id: str | None = Field(sa_column=Column(String))
    twitch_id: int | None = Field(sa_column=Column(Integer, unique=True))
    name: str | None = Field(sa_column=Column(String))
    privilege_level: PrivilegeLevel = Field(sa_column=Column(SmallInteger, nullable=True), default=PrivilegeLevel.User)

class CloudUser(UsersSchema, table=True):
    __tablename__ = "cloud_user"

    id: int = Field(sa_column=Column(Integer, Identity(), primary_key=True))
    drive_gmail: str | None = Field(sa_column=Column(String))
    drive_share_id: str | None = Field(sa_column=Column(String))
    name: str | None = Field(sa_column=Column(String))
    created_at: datetime = Field(sa_column=Column(TIMESTAMP(True, 0), default=datetime.now(tz), server_default=text("now()")))
    privilege_level: PrivilegeLevel = Field(sa_column=Column(SmallInteger, nullable=True), default=PrivilegeLevel.User)


class ExternalAccount(UsersSchema, table=True):
    __tablename__ = "external_account"

    id: int = Field(sa_column=Column(Integer, Identity(), primary_key=True))
    user_id: int = Field(foreign_key="users.cloud_user.id", index=True)

    # 平台類型與該平台的唯一 ID
    platform: GameType = Field(sa_column=Column(SmallInteger, index=True))
    external_id: str = Field(sa_column=Column(String, index=True))

    # 顯示名稱 (例如 Discord 名稱或遊戲 ID)
    display_name: str | None = Field(sa_column=Column(String))

    # 使用 JSONB 儲存不同平台差異化的資料
    platform_data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    __table_args__ = (
        # 確保同一個平台下的 external_id 唯一，避免重複綁定
        UniqueConstraint("platform", "external_id", name="unique_platform_account"),
        {**UsersSchema.__table_args__},
    )


class LinkCode(UsersSchema, table=True):
    __tablename__ = "link_code"

    user_id: int = Field(foreign_key="users.cloud_user.id", primary_key=True)
    code: str = Field(index=True)
    expires_at: datetime = Field(sa_column=Column(TIMESTAMP(True, 0)))

class DiscordUser(UserSchema, table=True):
    __tablename__ = "user_discord"

    discord_id: int = Field(sa_column=Column(BigInteger, primary_key=True, autoincrement=False))
    max_sign_consecutive_days: int | None = Field(sa_column=Column(Integer))
    meatball_times: int | None = Field(sa_column=Column(Integer))
    guaranteed: int | None = Field(sa_column=Column(Integer))
    registrations_id: int | None = Field(sa_column=Column(Integer, ForeignKey("stardb_idbase.discord_registrations.registrations_id"), default=None))

    registration: "DiscordRegistration" = Relationship(back_populates="members")


class UserPoint(UserSchema, table=True):
    __tablename__ = "user_point"

    discord_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    stardust: int = Field(sa_column=Column(Integer), default=0)
    point: int = Field(sa_column=Column(Integer), default=0)
    rcoin: int = Field(sa_column=Column(Integer), default=0)


class UserBet(UserSchema, table=True):
    __tablename__ = "user_bet"

    bet_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    discord_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    bet_option: int = Field(sa_column=Column(SmallInteger))
    bet_amount: int = Field(sa_column=Column(Integer))
    bet_at: datetime = Field(sa_column=Column(TIMESTAMP(True, 0)))


class UserGame(UserSchema, table=True):
    __tablename__ = "game_data"

    discord_id: int = Field(sa_column=Column(BigInteger, primary_key=True, autoincrement=False))
    game: GameType = Field(sa_column=Column(SmallInteger, primary_key=True, autoincrement=False))
    player_name: str = Field(sa_column=Column(String))
    player_id: str | None = Field(sa_column=Column(String))
    account_id: str | None = Field(sa_column=Column(String))
    other_id: str | None = Field(sa_column=Column(String))


class UserPoll(UserSchema, table=True):
    __tablename__ = "user_poll"

    poll_id: int = Field(sa_column=Column(Integer, primary_key=True))
    discord_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    vote_option: int = Field(sa_column=Column(Integer, primary_key=True))
    vote_at: datetime = Field(sa_column=Column(TIMESTAMP(True, 0)))
    vote_magnification: int = Field(sa_column=Column(Integer), default=1)


class UserAccount(UserSchema, table=True):
    __tablename__ = "user_account"

    main_account: int = Field(sa_column=Column(BigInteger, primary_key=True))
    alternate_account: int = Field(sa_column=Column(BigInteger, primary_key=True))


class UserParty(UserSchema, table=True):
    __tablename__ = "user_party"

    discord_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    party_id: int = Field(sa_column=Column(Integer, ForeignKey("stardb_idbase.party_datas.party_id"), primary_key=True))

    party: "Party" = Relationship(back_populates="members")


class UserModerate(UserSchema, table=True):
    __tablename__ = "user_moderate"

    warning_id: int = Field(sa_column=Column(Integer, Identity(), primary_key=True))
    discord_id: int = Field(sa_column=Column(BigInteger))
    moderate_type: WarningType = Field(sa_column=Column(Integer))
    moderate_user: int = Field(sa_column=Column(BigInteger))
    create_guild: int = Field(sa_column=Column(BigInteger))
    create_time: datetime = Field(sa_column=Column(TIMESTAMP(True, 0)))
    reason: str | None = Field(sa_column=Column(String))
    last_time: timedelta | None = Field(sa_column=Column(Interval))
    guild_only: bool | None = Field(sa_column=Column(Boolean))
    officially_given: bool | None = Field(sa_column=Column(Boolean))

    def embed(self, bot: discord.Bot) -> discord.Embed:
        user = bot.get_user(self.discord_id)
        moderate_user = bot.get_user(self.moderate_user)
        guild = bot.get_guild(self.create_guild)

        name = f"{user.name if user else f'<@{self.discord_id}>'} 的警告單"
        description = f"**編號：{self.warning_id}（{Jsondb.get_tw(self.moderate_type, 'warning_type')}）**\n- 被警告用戶：{user.mention if user else f'<@{self.discord_id}>'}\n- 管理員：{guild.name if guild else self.create_guild}/{moderate_user.mention if moderate_user else f'<@{self.moderate_user}>'}\n- 原因：{self.reason}\n- 時間：{self.create_time.strftime('%Y-%m-%d %H:%M:%S')}"
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

    def display_embed_field(self, bot: discord.Bot) -> tuple[str, str]:
        moderate_user = bot.get_user(self.moderate_user)
        guild = bot.get_guild(self.create_guild)
        name = f"編號：{self.warning_id}（{Jsondb.get_tw(self.moderate_type, 'warning_type')}）"
        value = f"{guild.name if guild else self.create_guild}/{moderate_user.mention if moderate_user else f'<@{self.moderate_user}>'}\n{self.reason}\n{self.create_time.strftime('%Y-%m-%d %H:%M:%S')}"
        if self.officially_given and self.guild_only:
            value += "\n官方認證警告 & 伺服器內警告"
        elif self.officially_given:
            value += "\n官方認證警告"
        elif self.guild_only:
            value += "\n伺服器內警告"

        return name, value


class RoleSave(UserSchema, table=True):
    __tablename__ = "role_save"

    discord_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    role_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    role_name: str = Field(sa_column=Column(String))
    time: date = Field(sa_column=Column(Date))


class Pet(UserSchema, table=True):
    __tablename__ = "user_pet"

    discord_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    pet_species: str = Field(sa_column=Column(String))
    pet_name: str = Field(sa_column=Column(String))
    food: int | None = Field(sa_column=Column(Integer))


class LOLGameRecord(UserSchema, table=True):
    __tablename__ = "lol_game_record"

    puuid: str = Field(sa_column=Column(String, primary_key=True))
    game_id: int = Field(sa_column=Column(Integer, primary_key=True))
    game_type: str = Field(sa_column=Column(String))
    game_mode: str = Field(sa_column=Column(String))
    champion_id: int = Field(sa_column=Column(Integer))
    teamId: int = Field(sa_column=Column(SmallInteger))
    timePlayed: timedelta = Field(sa_column=Column(Interval))
    totalTimeSpentDead: timedelta = Field(sa_column=Column(Interval))
    created_at: datetime = Field(sa_column=Column(TIMESTAMP(True, 0)))
    win: bool = Field(sa_column=Column(Boolean))
    kills: int = Field(sa_column=Column(Integer))
    deaths: int = Field(sa_column=Column(Integer))
    assists: int = Field(sa_column=Column(Integer))
    visionScore: int = Field(sa_column=Column(Integer))
    damage_dealt: int = Field(sa_column=Column(Integer))
    damage_taken: int = Field(sa_column=Column(Integer))
    double_kills: int = Field(sa_column=Column(Integer))
    triple_kills: int = Field(sa_column=Column(Integer))
    quadra_kills: int = Field(sa_column=Column(Integer))
    penta_kills: int = Field(sa_column=Column(Integer))
    gold_earned: int = Field(sa_column=Column(Integer))
    total_minions_killed: int = Field(sa_column=Column(Integer))
    turretKills: int = Field(sa_column=Column(Integer))
    inhibitorKills: int = Field(sa_column=Column(Integer))
    baronKills: int = Field(sa_column=Column(Integer))
    dragonKills: int = Field(sa_column=Column(Integer))
    item0: int = Field(sa_column=Column(Integer))
    item1: int = Field(sa_column=Column(Integer))
    item2: int = Field(sa_column=Column(Integer))
    item3: int = Field(sa_column=Column(Integer))
    item4: int = Field(sa_column=Column(Integer))
    item5: int = Field(sa_column=Column(Integer))
    item6: int = Field(sa_column=Column(Integer))
    firstBloodKill: bool = Field(sa_column=Column(Boolean))
    firstTowerKill: bool = Field(sa_column=Column(Boolean))
    allInPings: int = Field(sa_column=Column(Integer))
    assistMePings: int = Field(sa_column=Column(Integer))
    basicPings: int = Field(sa_column=Column(Integer))
    commandPings: int = Field(sa_column=Column(Integer))
    dangerPings: int = Field(sa_column=Column(Integer))
    enemyMissingPings: int = Field(sa_column=Column(Integer))
    enemyVisionPings: int = Field(sa_column=Column(Integer))
    getBackPings: int = Field(sa_column=Column(Integer))
    holdPings: int = Field(sa_column=Column(Integer))
    needVisionPings: int = Field(sa_column=Column(Integer))
    onMyWayPings: int = Field(sa_column=Column(Integer))
    pushPings: int = Field(sa_column=Column(Integer))
    retreatPings: int = Field(sa_column=Column(Integer))
    visionClearedPings: int = Field(sa_column=Column(Integer))


class TwitchPoint(UserSchema, table=True):
    __tablename__ = "twitch_point"

    twitch_id: int = Field(sa_column=Column(primary_key=True))
    broadcaster_id: int = Field(sa_column=Column(primary_key=True))
    point: int = Field(default=0)


class HappycampVIP(HappycampSchema, table=True):
    __tablename__ = "vip_info"

    discord_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    vip_level: int = Field(sa_column=Column(Integer))
    vip_admin: bool = Field(default=False)
    created_at: datetime = Field(sa_column=Column(TIMESTAMP(True, 0)))
    updated_at: datetime = Field(sa_column=Column(TIMESTAMP(True, 0)))


class HappycampVIPChannel(HappycampSchema, table=True):
    __tablename__ = "vip_channel"

    channel_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    vip_level: int = Field(sa_column=Column(Integer, primary_key=True))


class HappycampQuizRecord(HappycampSchema, table=True):
    __tablename__ = "quiz_record"

    record_id: int = Field(sa_column=Column(Integer, Identity(), primary_key=True))
    discord_id: int = Field(sa_column=Column(BigInteger))
    quiz_id: int = Field(sa_column=Column(Integer))
    score: int = Field(sa_column=Column(Integer))
    taken_at: datetime = Field(sa_column=Column(TIMESTAMP(True, 0)))


class HappycampApplicationForm(HappycampSchema, table=True):
    __tablename__ = "application_form"

    form_id: int = Field(sa_column=Column(Integer, Identity(), primary_key=True))
    discord_id: int = Field(sa_column=Column(BigInteger))
    content: str = Field(sa_column=Column(Text))
    status: int = Field(sa_column=Column(SmallInteger), default=0)  # 0: pending, 1: approved, 2: rejected
    submitted_at: datetime = Field(sa_column=Column(TIMESTAMP(True, 0)))
    reviewed_at: datetime | None = Field(sa_column=Column(TIMESTAMP(True, 0), nullable=True))
    reviewer_id: int | None = Field(sa_column=Column(BigInteger, nullable=True))
    review_comment: str | None = Field(sa_column=Column(Text, nullable=True))
    change_vip_level: int | None = Field(sa_column=Column(Integer, nullable=True))

    def embed(self):
        user_mention = f"<@{self.discord_id}>"
        status_dict = {0: "待審核", 1: "已通過", 2: "已拒絕"}
        embed = BotEmbed.general(
            name=f"申請表單 #{self.form_id} - {status_dict.get(self.status, '未知狀態')}",
            description=f"- 申請人：{user_mention}\n- 提交時間：{self.submitted_at.strftime('%Y-%m-%d %H:%M:%S')}\n- 審核時間：{self.reviewed_at.strftime('%Y-%m-%d %H:%M:%S') if self.reviewed_at else '尚未審核'}\n- 審核者：{f'<@{self.reviewer_id}>' if self.reviewer_id else '尚未審核'}\n- 審核意見：{self.review_comment if self.review_comment else '無'}",
            icon_url=None,
        )
        embed.add_field(name="申請內容", value=self.content or "無")
        embed.add_field(name="變更 VIP 等級", value=str(self.change_vip_level) if self.change_vip_level is not None else "無")
        return embed


class Community(BasicSchema, table=True):
    __tablename__ = "community_info"

    id: str = Field(primary_key=True)
    type: CommunityType = Field(sa_column=Column(Integer, primary_key=True))
    username: str
    display_name: str | None


class NotifyChannel(BasicSchema, table=True):
    __tablename__ = "notify_channel"

    guild_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    notify_type: NotifyChannelType = Field(sa_column=Column(Integer, primary_key=True))
    channel_id: int = Field(sa_column=Column(BigInteger))
    role_id: int | None = Field(sa_column=Column(BigInteger))
    message: str | None


class NotifyCommunity(BasicSchema, table=True):
    __tablename__ = "notify_community"

    notify_type: NotifyCommunityType = Field(sa_column=Column(Integer, primary_key=True))
    community_id: str = Field(primary_key=True)
    community_type: CommunityType = Field(sa_column=Column(Integer, primary_key=True))
    guild_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    channel_id: int = Field(sa_column=Column(BigInteger))
    role_id: int | None = Field(sa_column=Column(BigInteger))
    message: str | None


class DynamicVoiceLobby(BasicSchema, table=True):
    __tablename__ = "dynamic_voice_lobby"

    guild_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    channel_id: int = Field(sa_column=Column(BigInteger))
    default_room_name: str | None = Field(sa_column=Column(String(255), nullable=True))


class DynamicVoice(BasicSchema, table=True):
    __tablename__ = "dynamic_channel"

    channel_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    creator_id: int = Field(sa_column=Column(BigInteger))
    guild_id: int = Field(sa_column=Column(BigInteger))
    password: str | None = Field(sa_column=Column(String(255), nullable=True))


class Bet(BasicSchema, table=True):
    __tablename__ = "bet_data"

    bet_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    title: str
    blue_title: str
    pink_title: str
    is_on: bool
    created_at: datetime = Field(sa_column=Column(TIMESTAMP(True, 0)))


class Poll(BasicSchema, table=True):
    __tablename__ = "poll_data"

    poll_id: int = Field(sa_column=Column(Integer, Identity(), primary_key=True))
    title: str
    creator_id: int = Field(sa_column=Column(BigInteger))
    created_at: datetime = Field(sa_column=Column(TIMESTAMP(True, 0)))
    guild_id: int = Field(sa_column=Column(BigInteger))
    message_id: int | None = Field(sa_column=Column(BigInteger))
    end_at: datetime | None = Field(sa_column=Column(TIMESTAMP(True, 0), nullable=True))
    number_of_user_votes: int | None
    ban_alternate_account_voting: bool | None
    show_name: bool | None
    check_results_in_advance: bool | None
    results_only_initiator: bool | None
    can_change_vote: bool | None  # not implemented yet


class PollOption(BasicSchema, table=True):
    __tablename__ = "poll_options"

    poll_id: int = Field(primary_key=True)
    option_id: int = Field(primary_key=True)
    option_name: str


class PollRole(BasicSchema, table=True):
    __tablename__ = "poll_role"

    poll_id: int = Field(primary_key=True)
    role_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    is_only_role: bool
    role_magnification: int


class TwitchBotJoinChannel(BasicSchema, table=True):
    __tablename__ = "twitch_bot_join_channel"

    twitch_id: int = Field(primary_key=True)
    action_channel_id: int | None = Field(sa_column=Column(BigInteger))
    point_name: str | None = Field(sa_column=Column(String(255)))


class TwitchChatCommand(BasicSchema, table=True):
    __tablename__ = "twitch_chat_command"

    twitch_id: int = Field(primary_key=True)
    name: str = Field(primary_key=True)
    response: str = Field(nullable=False)


class InviteRecord(AlchemyBasicSchema):
    __tablename__ = "invite_record"

    invited_user: int = Column(BigInteger, primary_key=True)
    invite_guild: int = Column(BigInteger, primary_key=True)
    inviter_user: int = Column(BigInteger, primary_key=True)
    invite_time: datetime = Column(TIMESTAMP(True, 0))
    invite_code: str = Column(String(255))


class PushRecord(BasicSchema, table=True):
    __tablename__ = "push_record"

    channel_id: str = Field(sa_column=Column(String(255), primary_key=True))
    push_at: datetime = Field(sa_column=Column(TIMESTAMP(True, 0), default=datetime.min.replace(tzinfo=timezone.utc)))
    expire_at: datetime = Field(sa_column=Column(TIMESTAMP(True, 0), default=datetime.min.replace(tzinfo=timezone.utc)))
    secret: str | None = Field(sa_column=Column(String(255), nullable=True))

    @property
    def is_expired(self) -> bool:
        return self.expire_at < datetime.now(tz=tz) if self.expire_at else True


class ReactionRoleMessage(AlchemyBasicSchema):
    __tablename__ = "reaction_role_message"

    guild_id: int = Column(BigInteger, primary_key=True)
    channel_id: int = Column(BigInteger, primary_key=True)
    message_id: int = Column(BigInteger, primary_key=True)


class ReactionRoleOption(AlchemyBasicSchema):
    __tablename__ = "reaction_role"

    message_id: int = Column(BigInteger, primary_key=True)
    role_id: int = Column(BigInteger, primary_key=True)
    title: str = Column(String(255))
    description: str | None = Column(String(255), nullable=True)
    emoji: str | None = Column(String(255), nullable=True)
    style: int | None = Column(SmallInteger, nullable=True)


class Giveaway(BasicSchema, table=True):
    __tablename__ = "giveaway_data"

    id: int = Field(sa_column=Column(Integer, Identity(), primary_key=True))
    guild_id: int = Field(sa_column=Column(BigInteger))
    channel_id: int = Field(sa_column=Column(BigInteger))
    message_id: int | None = Field(sa_column=Column(BigInteger))
    creator_id: int = Field(sa_column=Column(BigInteger))
    prize_name: str = Field(sa_column=Column(String))
    winner_count: int = Field(sa_column=Column(Integer))
    created_at: datetime = Field(sa_column=Column(TIMESTAMP(True, 0)))
    end_at: datetime | None = Field(sa_column=Column(TIMESTAMP(True, 0)))
    is_on: bool = Field(sa_column=Column(Boolean), default=True)
    description: str | None = Field(sa_column=Column(String(255)))
    redraw_count: int = Field(sa_column=Column(Integer, nullable=True), default=0)


class GiveawayUser(UserSchema, table=True):
    __tablename__ = "user_giveaway"

    giveaway_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    user_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    user_weight: int = Field(sa_column=Column(Integer))
    join_at: datetime = Field(sa_column=Column(TIMESTAMP(True, 0)))
    is_winner: bool = Field(sa_column=Column(Boolean), default=False)


class User(AlchemyBasicSchema):
    __tablename__ = "users"

    id: int = Base.auto_id_column()
    name: str = mapped_column(String, nullable=False, default=None)
    age: int = mapped_column(Integer, default=None)

    # 建立關聯：一個使用者對應多篇貼文
    posts: list["Post"] = relationship(back_populates="user", init=False)


class Post(AlchemyBasicSchema):
    __tablename__ = "posts"

    id: int = Base.auto_id_column()
    title: str = Column(String, nullable=False)
    content: str = Column(String, nullable=False)
    created_at: datetime = Column(TIMESTAMP(precision=0), nullable=False)  # 只記錄到秒
    user_id: int = Column(Integer, ForeignKey(User.id), nullable=False)  # type: ignore

    # 建立反向關聯
    user: User = relationship(back_populates="posts", init=False)


class ServerConfig(BasicSchema, table=False):
    __tablename__ = "server_config"

    guild_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    timeout_after_warning_times: int | None
    voice_time_counter: bool | None


class MemorialDay(BasicSchema, table=True):
    __tablename__ = "memorial_days"

    day_id: int = Field(sa_column=Column(Integer, Identity(), primary_key=True))
    discord_id: int = Field(sa_column=Column(BigInteger))
    target_date: date
    name: str


class UserIPDetails(BasicSchema, table=True):
    __tablename__ = "user_ip_details"

    ip: str = Field(sa_column=Column(CIDR, primary_key=True))
    last_seen: datetime = Field(sa_column=Column(TIMESTAMP(True, 0)))
    discord_id: int | None = Field(sa_column=Column(BigInteger))
    address: str | None = Field(sa_column=Column(String))
    mac: str | None = Field(sa_column=Column(MACADDR))
    name: str | None = Field(sa_column=Column(String))
    registration_at: datetime | None = Field(sa_column=Column(TIMESTAMP(True, 0)))


class TicketChannelLobby(BasicSchema, table=True):
    __tablename__ = "ticket_channel_lobby"
    channel_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    category_id: int = Field(sa_column=Column(BigInteger))
    guild_id: int = Field(sa_column=Column(BigInteger))
    message_id: int = Field(sa_column=Column(BigInteger))


class TicketChannel(BasicSchema, table=True):
    __tablename__ = "ticket_channel"

    channel_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    guild_id: int = Field(sa_column=Column(BigInteger))
    creator_id: int = Field(sa_column=Column(BigInteger))
    created_at: datetime = Field(sa_column=Column(TIMESTAMP(True, 0)))
    closed_at: datetime | None = Field(sa_column=Column(TIMESTAMP(True, 0)))
    closer_id: int | None = Field(sa_column=Column(BigInteger))
    view_message_id: int | None = Field(sa_column=Column(BigInteger))


class VoiceTime(BasicSchema, table=True):
    __tablename__ = "voice_time"

    discord_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    guild_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    total_minute: timedelta = Field(sa_column=Column(Interval, default=timedelta()))


class Party(IdbaseSchema, table=True):
    __tablename__ = "party_datas"

    party_id: int = Field(sa_column=Column(primary_key=True))
    party_name: str = Field(sa_column=Column(String))
    role_id: int = Field(sa_column=Column(BigInteger))
    creator_id: int = Field(sa_column=Column(BigInteger))
    created_at: date = Field(sa_column=Column(Date))

    members: list[UserParty] = Relationship(back_populates="party")


class DiscordRegistration(IdbaseSchema, table=True):
    __tablename__ = "discord_registrations"

    registrations_id: int = Field(sa_column=Column(primary_key=True))
    guild_id: int = Field(sa_column=Column(BigInteger))
    role_id: int = Field(sa_column=Column(BigInteger))

    members: list[DiscordUser] = Relationship(back_populates="registration")


class TRPGStoryPlot(IdbaseSchema, table=True):
    __tablename__ = "trpg_storyplots"

    id: int = Field(sa_column=Column(primary_key=True))
    title: str = Field(sa_column=Column(String))
    content: str = Field(sa_column=Column(Text))
    options: list["TRPGStoryOption"] = Relationship(back_populates="plot")


class TRPGStoryOption(IdbaseSchema, table=True):
    __tablename__ = "trpg_plot_options"

    plot_id: int = Field(sa_column=Column(ForeignKey("stardb_idbase.trpg_storyplots.id"), primary_key=True))
    option_id: int = Field(sa_column=Column(primary_key=True))
    option_title: str = Field(sa_column=Column(String))
    lead_to_plot: int | None = Field(sa_column=Column(Integer))
    check_ability: int | None = Field(sa_column=Column(Integer))
    san_check_fall_dice: str | None = Field(sa_column=Column(String))
    success_plot: int | None = Field(sa_column=Column(Integer))
    fail_plot: int | None = Field(sa_column=Column(Integer))
    plot: TRPGStoryPlot = Relationship(back_populates="options")


class TRPGCharacter(IdbaseSchema, table=True):
    __tablename__ = "trpg_characters"

    discord_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    character_name: str = Field(sa_column=Column(String))

    abilities: list["TRPGCharacterAbility"] = Relationship(back_populates="character")


class TRPGCharacterAbility(IdbaseSchema, table=True):
    __tablename__ = "trpg_character_abilities"

    discord_id: int = Field(sa_column=Column(BigInteger, ForeignKey("stardb_idbase.trpg_characters.discord_id"), primary_key=True))
    ability_id: int = Field(sa_column=Column(ForeignKey("stardb_idbase.trpg_abilities.ability_id"), primary_key=True))
    san_lower_limit: int = Field(sa_column=Column(Integer))
    value: int = Field(sa_column=Column(Integer))

    character: TRPGCharacter = Relationship(back_populates="abilities")
    ability: "TRPGAbility" = Relationship(back_populates="characters")


class TRPGAbility(IdbaseSchema, table=True):
    __tablename__ = "trpg_abilities"

    ability_id: int = Field(sa_column=Column(primary_key=True))
    ability_name: str = Field(sa_column=Column(String))

    characters: list[TRPGCharacterAbility] = Relationship(back_populates="ability")


class BackupRole(BackupSchema, table=True):
    __tablename__ = "roles_backup"

    role_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    role_name: str = Field(sa_column=Column(String))
    created_at: datetime = Field(sa_column=Column(TIMESTAMP(True, 0)))
    guild_id: int = Field(sa_column=Column(BigInteger))
    colour_r: int = Field(sa_column=Column(Integer))
    colour_g: int = Field(sa_column=Column(Integer))
    colour_b: int = Field(sa_column=Column(Integer))
    description: str = Field(sa_column=Column(String))

    members: list["BackupRoleUser"] = Relationship(back_populates="role")

    def embed(self, bot: discord.Bot):
        embed = BotEmbed.simple(self.role_name, self.description)
        embed.add_field(name="創建於", value=self.created_at.strftime("%Y/%m/%d %H:%M:%S"))
        embed.add_field(name="顏色", value=f"({self.colour_r}, {self.colour_g}, {self.colour_b})")
        if bot and self.members:
            user_list = list()
            for user in self.members:
                user = bot.get_user(user.discord_id)
                if user:
                    user_list.append(user.mention)
            embed.add_field(name="成員", value=",".join(user_list), inline=False)

        return embed


class BackupRoleUser(BackupSchema, table=True):
    __tablename__ = "role_user_backup"

    role_id: int = Field(sa_column=Column(BigInteger, ForeignKey("stardb_backup.roles_backup.role_id"), primary_key=True))
    discord_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    role: BackupRole = Relationship(back_populates="members")


class BackupCategory(BackupSchema, table=True):
    __tablename__ = "category_backup"

    category_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    name: str = Field(sa_column=Column(String))
    created_at: datetime = Field(sa_column=Column(TIMESTAMP(True, 0)))
    guild_id: int = Field(sa_column=Column(BigInteger))
    description: str | None = Field(sa_column=Column(String))

    def embed(self, bot: discord.Bot):
        embed = BotEmbed.simple(self.name, self.description)
        embed.add_field(name="創建於", value=self.created_at.strftime("%Y/%m/%d %H:%M:%S"))
        return embed


class BackupChannel(BackupSchema, table=True):
    __tablename__ = "channel_backup"

    channel_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    name: str = Field(sa_column=Column(String))
    created_at: datetime = Field(sa_column=Column(TIMESTAMP(True, 0)))
    guild_id: int = Field(sa_column=Column(BigInteger))
    category_id: int | None = Field(sa_column=Column(BigInteger))
    description: str | None = Field(sa_column=Column(String))

    def embed(self, bot: discord.Bot):
        embed = BotEmbed.simple(self.name, self.description)
        embed.add_field(name="創建於", value=self.created_at.strftime("%Y/%m/%d %H:%M:%S"))
        return embed


class BackupMessage(BackupSchema, table=True):
    __tablename__ = "message_backup"

    message_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    channel_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    content: str | None = Field(sa_column=Column(Text))
    created_at: datetime = Field(sa_column=Column(TIMESTAMP(True, 0)))
    author_id: int = Field(sa_column=Column(BigInteger))
    description: str | None = Field(sa_column=Column(String))

    def embed(self, bot: discord.Bot):
        user = bot.get_user(self.author_id)
        embed = BotEmbed.simple(f"Message from {user.name if user else self.author_id}", self.content or "No content")
        embed.add_field(name="Created at", value=self.created_at.strftime("%Y/%m/%d %H:%M:%S"))
        return embed


class UsersCountRecord(BackupSchema, table=True):
    __tablename__ = "users_count_backup"

    record_date: date = Field(sa_column=Column(Date, primary_key=True))
    shard_id: int | None = Field(sa_column=Column(SmallInteger))
    users_count: int = Field(sa_column=Column(Integer))
    servers_count: int = Field(sa_column=Column(Integer))


class OAuth2Token(TokensSchema, table=True):
    __tablename__ = "oauth_token2"

    user_id: str = Field(sa_column=Column(String, primary_key=True))
    type: CommunityType = Field(sa_column=Column(Integer, primary_key=True))
    access_token: str = Field(sa_column=Column(String))
    refresh_token: str | None = Field(sa_column=Column(String))
    expires_at: datetime = Field(sa_column=Column(TIMESTAMP(True, 0)))

    @property
    def valid(self):
        return self.expires_at > datetime.now(tz)


class BotToken(TokensSchema, table=True):
    __tablename__ = "bot_token2"

    api_type: APIType = Field(sa_column=Column(SmallInteger, primary_key=True))
    token_seq: int = Field(sa_column=Column(SmallInteger, primary_key=True))
    client_id: str | None = Field(sa_column=Column(String))
    client_secret: str | None = Field(sa_column=Column(String))
    access_token: str | None = Field(sa_column=Column(String))
    refresh_token: str | None = Field(sa_column=Column(String))
    revoke_token: str | None = Field(sa_column=Column(String))
    redirect_uri: str | None = Field(sa_column=Column(String))
    callback_uri: str | None = Field(sa_column=Column(String))
    expires_at: datetime | None = Field(sa_column=Column(TIMESTAMP(True, 0)))


class Credential(TokensSchema, table=True):
    __tablename__ = "credential"

    id: int = Field(sa_column=Column(Integer, Identity(), primary_key=True))
    type: CredentialType = Field(sa_column=Column(SmallInteger, nullable=False))
    source: APIType = Field(sa_column=Column(SmallInteger, nullable=False))
    source_seq: int
    client_name: str
    # created_at: datetime
    # updated_at: datetime


class IdentifierSecret(TokensSchema, table=True):
    __tablename__ = "id_secret"

    credential_id: int = Field(sa_column=Column(Integer, ForeignKey("credentials.credential.id"), primary_key=True))
    client_id: str = Field(sa_column=Column(String, unique=True, nullable=False))
    client_secret: str = Field(sa_column=Column(String, nullable=False))


class AccessToken(TokensSchema, table=True):
    __tablename__ = "access_token"

    credential_id: int = Field(sa_column=Column(Integer, ForeignKey("credentials.credential.id"), primary_key=True))
    access_token: str = Field(sa_column=Column(String, nullable=False))
    expires_at: datetime = Field(sa_column=Column(TIMESTAMP(True, 0)))

    @property
    def valid(self):
        return not self.expires_at or self.expires_at > datetime.now(tz)


class OAuthClient(TokensSchema, table=True):
    __tablename__ = "oauth_client"

    credential_id: int = Field(sa_column=Column(Integer, ForeignKey("credentials.credential.id"), primary_key=True))
    client_id: str = Field(sa_column=Column(String, nullable=False))
    client_secret: str = Field(sa_column=Column(String, nullable=False))
    redirect_uri: str = Field(sa_column=Column(String, nullable=False))
    callback_uri: str = Field(sa_column=Column(String))
    grant_types: str = Field(sa_column=Column(String))
    default_scopes: list[str] = Field(sa_column=Column(ARRAY(String)))


class OAuthToken(TokensSchema, table=True):
    __tablename__ = "oauth_token"

    user_id: str = Field(sa_column=Column(String, primary_key=True))
    client_credential_id: int = Field(sa_column=Column(Integer, ForeignKey("credentials.oauth_client.credential_id"), primary_key=True))
    access_token: str = Field(sa_column=Column(String))
    refresh_token: str = Field(sa_column=Column(String))
    scope: list[str] = Field(sa_column=Column(ARRAY(String)))
    expires_at: datetime = Field(sa_column=Column(TIMESTAMP(True, 0)))

    @property
    def valid(self):
        return self.expires_at > datetime.now(tz)


class WebSubConfig(TokensSchema, table=True):
    __tablename__ = "websub_config"
    credential_id: int = Field(foreign_key="credentials.credential.id", primary_key=True)
    callback_uri: str
    hub_secret: str | None = None


class WebsubInstance(TokensSchema, table=True):
    __tablename__ = "websub_instance"
    id: int | None = Field(default=None, primary_key=True)
    config_id: int = Field(foreign_key="credentials.websub_config.credential_id")
    topic: str
    lease_seconds: int | None = None
    expires_at: datetime | None = None
    hub_mode: str | None = None
    status: str | None = None
    hub_challenge: str | None = None


class CommunityCache(CacheSchema, table=True):
    """社群快取資料表"""

    __tablename__ = "community_cache"

    notify_type: NotifyCommunityType = Field(sa_column=Column(Integer, primary_key=True))
    community_id: str = Field(sa_column=Column(String, primary_key=True))
    value: datetime = Field(sa_column=Column(TIMESTAMP(True, 0)))


class NotifyCache(CacheSchema, table=True):
    """通知快取資料表"""

    __tablename__ = "notify_cache"

    notify_type: NotifyChannelType = Field(sa_column=Column(Integer, primary_key=True))
    value: datetime = Field(sa_column=Column(TIMESTAMP(True, 0)))


class YoutubeCache(CacheSchema, table=True):
    """YouTube快取資料表"""

    __tablename__ = "youtube_cache"

    video_id: str = Field(sa_column=Column(String, primary_key=True))
    scheduled_live_start: datetime = Field(sa_column=Column(TIMESTAMP(True, 0)))


class LOLGameCache(CacheSchema, table=True):
    """LOL遊戲快取資料表"""

    __tablename__ = "lol_game_cache"

    puuid: str = Field(sa_column=Column(String, primary_key=True))
    newest_game_time: datetime = Field(sa_column=Column(TIMESTAMP(True, 0)))


class WarningList(ListObject[UserModerate]):
    def __init__(self, items: list[UserModerate], discord_id: int):
        super().__init__(items)
        self.discord_id = discord_id

    def display(self, bot: discord.Bot, user: discord.User | None = None) -> discord.Embed:
        """生成警告單列表的嵌入消息

        Args:
            bot (discord.Bot): 由Bot取得使用者與伺服器訊息
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
