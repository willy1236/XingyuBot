from dataclasses import dataclass, field
from datetime import date, datetime
from typing import TYPE_CHECKING, TypedDict

from discord import Bot
from sqlalchemy import (BigInteger, Column, ForeignKey, Integer,
                        String, Text, ForeignKeyConstraint)
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlmodel import Field, Relationship

from ..base import ListObject
from ..fileDatabase import Jsondb
from ..settings import tz
from ..types import *
from ..utils import BotEmbed
from .sqlSchema import *

if TYPE_CHECKING:
    from ..database import SQLEngine
class CloudUser(UserSchema, table=True):
    __tablename__ = 'cloud_user'

    id: str | None
    discord_id: int = Field(sa_column=Column(BigInteger, primary_key=True, autoincrement=False))
    email: str | None
    drive_share_id: str | None
    twitch_id: int | None = Field(unique=True)

class DiscordUser(UserSchema, table=True):
    __tablename__ = "user_discord"

    discord_id: int = Field(sa_column=Column(BigInteger, primary_key=True, autoincrement=False))
    name: str | None
    max_sign_consecutive_days: int | None
    meatball_times: int | None
    guaranteed: int | None
    registrations_id: int | None = Field(foreign_key="stardb_idbase.discord_registrations.registrations_id")
    
    registration: "DiscordRegistration" = Relationship(back_populates="members")

class UserPoint(UserSchema, table=True):
    __tablename__ = "user_point"

    discord_id: int = Field(sa_column=Column(BigInteger, primary_key=True, autoincrement=False))
    stardust: int | None = Field(default=0)
    point: int | None = Field(default=0)
    rcoin: int | None = Field(default=0)

class UserGame(UserSchema, table=True):
    __tablename__ = "game_data"

    discord_id: int = Field(sa_column=Column(BigInteger, primary_key=True, autoincrement=False))
    game: GameType = Field(sa_column=Column(Integer, primary_key=True, autoincrement=False))
    player_name: str
    player_id: str | None
    account_id: str | None
    other_id: str | None

class UserPoll(UserSchema, table=True):
    __tablename__ = "user_poll"
    
    poll_id: int = Field(primary_key=True)
    discord_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    vote_option: int = Field(primary_key=True)
    vote_at: datetime
    vote_magnification: int = Field(default=1)

class UserAccount(UserSchema, table=True):
    __tablename__ = "user_account"

    main_account: int = Field(sa_column=Column(BigInteger, primary_key=True))
    alternate_account: int = Field(sa_column=Column(BigInteger, primary_key=True))

class UserParty(UserSchema, table=True):
    __tablename__ = "user_party"
    
    discord_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    party_id: int = Field(primary_key=True, foreign_key="stardb_idbase.party_datas.party_id")
    
    party: "Party" = Relationship(back_populates="members")

class UserModerate(UserSchema, table=True):
    __tablename__ = "user_moderate"

    warning_id: int = Field(primary_key=True, default=None)
    discord_id: int = Field(sa_column=Column(BigInteger))
    moderate_type: WarningType = Field(sa_column=Column(Integer, primary_key=True))
    moderate_user: int = Field(sa_column=Column(BigInteger))
    create_guild: int = Field(sa_column=Column(BigInteger))
    create_time: datetime
    reason: str | None
    last_time: str | None
    guild_only: bool | None
    officially_given: bool | None

    def embed(self,bot:Bot):
        user = bot.get_user(self.discord_id)
        moderate_user = bot.get_user(self.moderate_user)
        guild = bot.get_guild(self.create_guild)
        
        name = f'{user.name} 的警告單'
        description = f"**編號:{self.warning_id} ({Jsondb.get_tw(self.moderate_type,'warning_type')})**\n被警告用戶：{user.mention}\n管理員：{guild.name}/{moderate_user.mention}\n原因：{self.reason}\n時間：{self.create_time}"
        if self.officially_given:
            description += "\n官方警告"
        if self.guild_only:
            description += "\n伺服器區域警告"
        embed = BotEmbed.general(name=name,icon_url=user.display_avatar.url,description=description)
        return embed
    
    def display_embed_field(self,bot:Bot):
            moderate_user = bot.get_user(self.moderate_user)
            guild = bot.get_guild(self.create_guild)
            name = f"編號: {self.warning_id} ({Jsondb.get_tw(self.moderate_type,'warning_type')})"
            value = f"{guild.name}/{moderate_user.mention}\n{self.reason}\n{self.create_time}"
            if self.officially_given:
                value += "\n官方警告"
            if self.guild_only:
                value += "\n伺服器區域警告"
            return name, value

class RoleSave(UserSchema, table=True):
    __tablename__ = "role_save"

    discord_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    role_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    role_name: str
    time: date

class Pet(UserSchema, table=True):
    __tablename__ = "user_pet"

    discord_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    pet_species: str
    pet_name: str
    food: int | None

class Community(BasicSchema, table=True):
    __tablename__ = "community_info"
    
    id: str = Field(primary_key=True)
    type: CommunityType = Field(sa_column=Column(Integer, primary_key=True))
    name: str
    login: str | None

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


class DynamicChannel(BasicSchema, table=True):
    __tablename__ = "dynamic_channel"
    
    channel_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    discord_id: int = Field(sa_column=Column(BigInteger))
    guild_id: int = Field(sa_column=Column(BigInteger))
    created_at: datetime

class Poll(BasicSchema, table=True):
    __tablename__ = "poll_data"

    poll_id: int = Field(default=None, primary_key=True)
    title: str
    created_user: int = Field(sa_column=Column(BigInteger))
    created_at: datetime
    is_on: bool
    message_id: int = Field(sa_column=Column(BigInteger))
    guild_id: int = Field(sa_column=Column(BigInteger))
    ban_alternate_account_voting: bool
    show_name: bool
    check_results_in_advance: bool
    results_only_initiator: bool
    number_of_user_votes: int

class PollOption(BasicSchema, table=True):
    __tablename__ = "poll_options"

    poll_id: int = Field(primary_key=True)
    option_id: int = Field(primary_key=True)
    option_name: str

class PollRole(BasicSchema, table=True):
    __tablename__ = "poll_role"

    poll_id: int = Field(primary_key=True)
    role_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    role_type: int
    role_magnification: int

class TwitchBotJoinChannel(BasicSchema, table=True):
    __tablename__ = "twitch_bot_join_channel"
    
    twitch_id: int = Field(primary_key=True)
    action_channel_id: int | None = Field(sa_column=Column(BigInteger))

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

class PushRecord(AlchemyBasicSchema):
    __tablename__ = "push_record"

    channel_id: str = Column(String(255), primary_key=True)
    push_at: datetime = Column(TIMESTAMP(True, 0))
    expire_at: datetime = Column(TIMESTAMP(True, 0))

class ReactionRoleMessage(AlchemyBasicSchema):
    __tablename__ = "reaction_role_message"

    guild_id: int = Column(BigInteger, primary_key=True)
    channel_id: int = Column(BigInteger, primary_key=True)
    message_id: int = Column(BigInteger, primary_key=True)

class ReactionRole(AlchemyBasicSchema):
    __tablename__ = "reaction_role"

    message_id: int = Column(BigInteger, primary_key=True)
    role_id: int = Column(BigInteger, primary_key=True)
    title: str = Column(String(255))
    description: str | None = Column(String(255), nullable=True)
    emoji: str | None  = Column(String(255), nullable=True)
    style: int | None  = Column(Integer, nullable=True)

class User(AlchemyBasicSchema):
    __tablename__ = 'users'
    
    id: int = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    name: str = Column(String, nullable=False)

    # 建立關聯：一個使用者對應多篇貼文
    posts:list["Post"] = relationship(back_populates="user", init=False)

class Post(AlchemyBasicSchema):
    __tablename__ = 'posts'

    id: int = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    title: str = Column(String, nullable=False)
    content: str = Column(String, nullable=False)
    created_at: datetime = Column(TIMESTAMP(precision=0), nullable=False)  # 只記錄到秒
    user_id: int = Column(Integer, ForeignKey('stardb_basic.users.id'), nullable=False)

    # 建立反向關聯
    user:User = relationship(back_populates="posts", init=False)

class Party(IdbaseSchema, table=True):
    __tablename__ = "party_datas"

    party_id: int = Field(primary_key=True)
    party_name: str
    role_id: int = Field(sa_column=Column(BigInteger))
    creator_id: int = Field(sa_column=Column(BigInteger))
    created_at: date
    
    members: list[UserParty] = Relationship(back_populates="party")

class DiscordRegistration(IdbaseSchema, table=True):
    __tablename__ = "discord_registrations"
    
    registrations_id: int = Field(primary_key=True)
    guild_id: int = Field(sa_column=Column(BigInteger))
    role_id: int = Field(sa_column=Column(BigInteger))

    members: list[DiscordUser] = Relationship(back_populates="registration")

class TRPGStoryPlot(IdbaseSchema, table=True):
    __tablename__ = "trpg_storyplots"

    id: int = Field(primary_key=True)
    title: str
    content: str = Field(sa_column=Column(Text))
    options: list["TRPGStoryOption"] = Relationship(back_populates="plot")

class TRPGStoryOption(IdbaseSchema, table=True):
    __tablename__ = "trpg_plot_options"

    plot_id: int = Field(primary_key=True, foreign_key="stardb_idbase.trpg_storyplots.id")
    option_id: int = Field(primary_key=True)
    option_title: str
    lead_to_plot: int | None
    check_ability: int | None
    san_check_fall_dice: str | None
    success_plot: int | None
    fail_plot: int | None
    plot: TRPGStoryPlot = Relationship(back_populates="options")

class TRPGCharacter(IdbaseSchema, table=True):
    __tablename__ = "trpg_characters"

    discord_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    character_name: str

    abilities: list["TRPGCharacterAbility"] = Relationship(back_populates="character")

class TRPGCharacterAbility(IdbaseSchema, table=True):
    __tablename__ = "trpg_character_abilities"

    discord_id: int = Field(sa_column=Column(BigInteger, ForeignKey("stardb_idbase.trpg_characters.discord_id"), primary_key=True))
    ability_id: int = Field(primary_key=True, foreign_key="stardb_idbase.trpg_abilities.ability_id")
    san_lower_limit: int | None
    value: int

    character: TRPGCharacter = Relationship(back_populates="abilities")
    ability: "TRPGAbility" = Relationship(back_populates="characters")

class TRPGAbility(IdbaseSchema, table=True):
    __tablename__ = "trpg_abilities"

    ability_id: int = Field(primary_key=True)
    ability_name: str

    characters: list[TRPGCharacterAbility] = Relationship(back_populates="ability")

class BackupRole(BackupSchema, table=True):
    __tablename__ = "roles_backup"

    role_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    role_name: str
    created_at: datetime
    guild_id: int = Field(sa_column=Column(BigInteger))
    colour_r: int
    colour_g: int
    colour_b: int
    description: str

    members: list["BackupRoleUser"] = Relationship(back_populates="role")
    
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

class BackupRoleUser(BackupSchema, table=True):
    __tablename__ = "role_user_backup"
    
    role_id: int = Field(sa_column=Column(BigInteger, ForeignKey("stardb_backup.roles_backup.role_id"), primary_key=True))
    discord_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    role: BackupRole = Relationship(back_populates="members")

class OAuth2Token(TokensSchema, table=True):
    __tablename__ = "oauth_token"

    user_id: str = Field(primary_key=True)
    type: CommunityType = Field(sa_column=Column(Integer, primary_key=True))
    access_token: str
    refresh_token: str
    expires_at: datetime

    @property
    def valid(self):
        return self.expires_at > datetime.now()

class BotToken(TokensSchema, table=True):
    __tablename__ = "bot_token"

    api_type: CommunityType = Field(sa_column=Column(Integer, primary_key=True))
    id: int | None = Field(sa_column=Column(Integer, primary_key=True, autoincrement=True))
    client_id: str | None
    client_secret: str | None
    access_token: str | None
    refresh_token: str | None
    revoke_token: str | None
    redirect_uri: str | None
    callback_uri: str | None
    expires_at: datetime | None

class AccountDetails(LedgerSchema, table=True):
    __tablename__ = "account_details"

    id: int = Field(primary_key=True)
    title: str
    category: int
    Payment_method: int
    created_at: datetime
    total_money: int
    actual_paid_money: int
    irrelevant_money: int
    note: str
    import_source: int

class UpfrontDetails(LedgerSchema, table=True):
    __tablename__ = "upfront_details"

    account_details_id: int = Field(primary_key=True)
    upfront_id: int
    upfront_type: datetime
    upfront_amount: int
    note: str

class DetailsCategory(LedgerSchema, table=True):
    __tablename__ = "details_category"

    category_id: int = Field(primary_key=True)
    category_name: str

class PaymentMethod(LedgerSchema, table=True):
    __tablename__ = "payment_method"

    method_id: int = Field(primary_key=True)
    method_name: str

class ImportSource(LedgerSchema, table=True):
    __tablename__ = "import_source"

    source_id: int = Field(primary_key=True)
    source_name: str

class UpfrontType(LedgerSchema, table=True):
    __tablename__ = "upfront_type"

    type_id: int = Field(primary_key=True)
    type_name: str


class WarningList(ListObject):
    if TYPE_CHECKING:
        items: list[UserModerate]
        discord_id: int

    def __init__(self,items:list, discord_id:int):
        super().__init__(items)
        self.discord_id = discord_id
    
    def display(self,bot:Bot):
        user = bot.get_user(self.discord_id)
        embed = BotEmbed.general(f'{user.name} 的警告單列表（共{len(self.items)}筆）',user.display_avatar.url)
        for i in self.items:
            name, value = i.display_embed_field(bot)
            embed.add_field(name=name,value=value)
        return embed