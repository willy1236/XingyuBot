#from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import TYPE_CHECKING, List, Optional, TypedDict

from discord import Bot
from sqlalchemy import Column, Integer, String, DateTime, BigInteger
from sqlalchemy.orm import declarative_base
from sqlmodel import Field, Relationship, SQLModel

from ..settings import tz
from ..types import *
from ..utilities import BotEmbed, ChoiceList
from .BaseModel import ListObject

if TYPE_CHECKING:
    from ..database import SQLEngine

Base = declarative_base()

class Student(SQLModel, table=True):
    __tablename__ = 'students'
    __table_args__ = {'schema': 'database'}
    
    id: int = Field(sa_column=Column(Integer, primary_key=True))
    name: str = Field(sa_column=Column(String(255)))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), default=lambda: datetime.now(tz)))
    school_id: int | None = Field(foreign_key="database.schools.id")

    school: "School" = Relationship(back_populates="students")

class School(SQLModel, table=True):
    __tablename__ = 'schools'
    __table_args__ = {'schema': 'database'}

    id: int = Field(primary_key=True)
    name: str

    students: list[Student] = Relationship(back_populates="school")

class CloudUser(SQLModel, table=True):
    __tablename__ = 'cloud_user'
    __table_args__ = {'schema': 'stardb_user'}

    id: str = Field(unique=True, nullable=True)
    discord_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    email: str = Field(nullable=True)
    drive_share_id: str = Field(nullable=True)
    twitch_id: int = Field(nullable=True)

class DiscordUser(SQLModel, table=True):
    __tablename__ = "user_discord"
    __table_args__ = {'schema': 'stardb_user'}

    discord_id:int = Field(primary_key=True)
    name: str | None
    max_sign_consecutive_days: int | None
    meatball_times: int | None
    guaranteed: int | None
    registrations_id: int | None = Field(foreign_key="stardb_idbase.discord_registrations.registrations_id")
    
    registration: "DiscordRegistration" = Relationship(back_populates="members")

class UserPoint(SQLModel, table=True):
    __tablename__ = "user_point"
    __table_args__ = {'schema': 'stardb_user'}

    discord_id: int = Field(primary_key=True)
    scoin: int = Field(default=0)
    point: int = Field(default=0)
    rcoin: int = Field(default=0)

class UserPoll(SQLModel, table=True):
    __tablename__ = "user_poll"
    __table_args__ = {'schema': 'stardb_user'}
    
    poll_id: int = Field(primary_key=True, foreign_key="stardb_basic.poll_data.poll_id")
    discord_id: int = Field(primary_key=True)
    vote_option: int = Field(primary_key=True, foreign_key="stardb_basic.poll_options.option_id")
    vote_at: datetime
    vote_magnification: int = Field(default=1)

class UserAccount(SQLModel, table=True):
    __tablename__ = "user_account"
    __table_args__ = {'schema': 'stardb_user'}

    main_account: int = Field(primary_key=True)
    alternate_account: int = Field(primary_key=True)

class UserParty(SQLModel, table=True):
    __tablename__ = "user_party"
    __table_args__ = {'schema': 'stardb_user'}
    
    discord_id: int = Field(primary_key=True)
    party_id: int = Field(primary_key=True, foreign_key="database.party_data.party_id")
    
    party: "Party" = Relationship(back_populates="members")

class UserModerate(SQLModel, table=True):
    __tablename__ = "user_moderate"
    __table_args__ = {'schema': 'stardb_user'}

    warning_id: int = Field(primary_key=True, default=None)
    discord_id: int
    moderate_type: WarningType = Field(sa_column=Column(Integer, primary_key=True))
    moderate_user: int
    create_guild: int
    create_time: int
    reason: str
    last_time: str
    guild_only: bool
    officially_given: bool

    def embed(self,bot:Bot):
        user = bot.get_user(self.discord_id)
        moderate_user = bot.get_user(self.moderate_user)
        guild = bot.get_guild(self.create_guild)
        
        name = f'{user.name} 的警告單'
        description = f"**編號:{self.warning_id} ({ChoiceList.get_tw(self.moderate_type,'warning_type')})**\n被警告用戶：{user.mention}\n管理員：{guild.name}/{moderate_user.mention}\n原因：{self.reason}\n時間：{self.create_time}"
        if self.officially_given:
            description += "\n官方警告"
        if self.guild_only:
            description += "\n伺服器區域警告"
        embed = BotEmbed.general(name=name,icon_url=user.display_avatar.url,description=description)
        return embed
    
    def display_embed_field(self,bot:Bot):
            moderate_user = bot.get_user(self.moderate_user)
            guild = bot.get_guild(self.create_guild)
            name = f"編號: {self.warning_id} ({ChoiceList.get_tw(self.moderate_type,'warning_type')})"
            value = f"{guild.name}/{moderate_user.mention}\n{self.reason}\n{self.create_time}"
            if self.officially_given:
                value += "\n官方警告"
            if self.guild_only:
                value += "\n伺服器區域警告"
            return name, value


class RoleSave(SQLModel, table=True):
    __tablename__ = "role_save"
    __table_args__ = {'schema': 'stardb_user'}

    discord_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    role_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    role_name: str
    time: date

class NotifyChannel(SQLModel, table=True):
    __tablename__ = "notify_channel"
    __table_args__ = {'schema': 'stardb_basic'}
    
    guild_id: int = Field(primary_key=True)
    notify_type: NotifyChannelType = Field(sa_column=Column(Integer, primary_key=True))
    channel_id: int
    role_id: int | None

class NotifyCommunity(SQLModel, table=True):
    __tablename__ = "notify_community"
    __table_args__ = {'schema': 'stardb_basic'}
    
    notify_type: NotifyCommunityType = Field(sa_column=Column(Integer, primary_key=True))
    notify_name: str = Field(primary_key=True)
    guild_id: int = Field(primary_key=True)
    display_name: str
    channel_id: int
    role_id: int | None

class DynamicChannel(SQLModel, table=True):
    __tablename__ = "dynamic_channel"
    __table_args__ = {'schema': 'stardb_basic'}
    
    channel_id: int = Field(primary_key=True)
    discord_id: int
    guild_id: int
    created_at: datetime

class Poll(SQLModel, table=True):
    __tablename__ = "poll_data"
    __table_args__ = {'schema': 'stardb_basic'}

    poll_id: int = Field(default=None, primary_key=True)
    title: str
    created_user: int
    created_at: datetime
    is_on: bool
    message_id: int
    guild_id: int
    ban_alternate_account_voting: bool
    show_name: bool
    check_results_in_advance: bool
    results_only_initiator: bool
    number_of_user_votes: int

class PollOption(SQLModel, table=True):
    __tablename__ = "poll_options"
    __table_args__ = {'schema': 'stardb_basic'}

    poll_id: int = Field(primary_key=True, foreign_key="stardb_basic.poll_data.poll_id")
    option_id: int = Field(primary_key=True)
    option_name: str

class PollRole(SQLModel, table=True):
    __tablename__ = "poll_role"
    __table_args__ = {'schema': 'stardb_basic'}

    poll_id: int = Field(primary_key=True, foreign_key="stardb_basic.poll_data.poll_id")
    role_id: int = Field(primary_key=True)
    role_type: int
    role_magnification: int

class Party(SQLModel, table=True):
    __tablename__ = "party_data"
    __table_args__ = {'schema': 'database'}

    party_id: int = Field(primary_key=True)
    party_name: str
    role_id: int
    creator_id: int
    created_at: datetime
    
    members: list[UserParty] = Relationship(back_populates="party")

class TwitchBotJoinChannel(SQLModel, table=True):
    __tablename__ = "twitch_bot_join_channel"
    __table_args__ = {'schema': 'stardb_basic'}
    
    twitch_id: int = Field(primary_key=True)
    action_channel_id: int = Field(sa_column=Column(BigInteger))

class DiscordRegistration(SQLModel, table=True):
    __tablename__ = "discord_registrations"
    __table_args__ = {'schema': 'stardb_idbase'}
    
    registrations_id: int = Field(primary_key=True)
    guild_id: int
    role_id: int

    members: list[DiscordUser] = Relationship(back_populates="registration")

class BackupRole(SQLModel, table=True):
    __tablename__ = "roles_backup"
    __table_args__ = {'schema': 'stardb_backup'}

    role_id: int = Field(primary_key=True)
    role_name: str
    created_at: datetime
    guild_id: int
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

class BackupRoleUser(SQLModel, table=True):
    __tablename__ = "role_user_backup"
    __table_args__ = {'schema': 'stardb_backup'}
    
    role_id: int = Field(primary_key=True, foreign_key="stardb_backup.roles_backup.role_id")
    discord_id: int = Field(primary_key=True)

    role: BackupRole = Relationship(back_populates="members")

class OAuth2Token(SQLModel, table=True):
    __tablename__ = "oauth_token"
    __table_args__ = {'schema': 'stardb_tokens'}

    user_id: str = Field(primary_key=True)
    type: CommunityType = Field(sa_column=Column(Integer, primary_key=True))
    access_token: str
    refresh_token: str
    expires_at: datetime

class BotToken(SQLModel, table=True):
    __tablename__ = "bot_token"
    __table_args__ = {'schema': 'stardb_tokens'}

    api_type: CommunityType = Field(sa_column=Column(Integer, primary_key=True))
    client_id: str
    client_secret: str
    access_token: str
    refresh_token: str
    redirect_uri: str
    callback_uri: str

class WarningList(ListObject):
    if TYPE_CHECKING:
        items: list[UserModerate]
        discord_id: int

    def __init__(self,items:list, discord_id:int):
        super().__init__(items)
        self.discord_id = discord_id
    
    def display(self,bot:Bot):
        user = bot.get_user(self.discord_id)
        embed = BotEmbed.general(f'{user.name} 的警告單列表（共{len(self)}筆）',user.display_avatar.url)
        for i in self.items:
            name, value = i.display_embed_field(bot)
            embed.add_field(name=name,value=value)
        return embed