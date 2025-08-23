import threading
from collections.abc import Callable, Generator
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from functools import wraps
from typing import TYPE_CHECKING, Any, Literal, ParamSpec, Self, TypeVar, overload

import discord
import sqlalchemy
from google.oauth2.credentials import Credentials
from sqlalchemy import and_, delete, desc, func, not_, or_, Select
from sqlalchemy.engine import URL, Result, ScalarResult
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session as ALSession
from sqlalchemy.orm import joinedload, sessionmaker
from sqlmodel import Session, SQLModel, create_engine, select, update

from starlib.models.mysql import Community, NotifyCommunity

from ..errors import *
from ..fileDatabase import Jsondb
from ..models.mysql import *
from ..models.rpg import *
from ..models.sqlSchema import Base
from ..settings import tz
from ..types import *
from ..utils import log

T = TypeVar("T")
P = ParamSpec("P")

# 外部裝飾器定義
def with_session(func):
    @wraps(func)
    def wrapper(self: "BaseSQLEngine", *args, **kwargs):
        with self.session_scope():
            return func(self, *args, **kwargs)

    return wrapper


class BaseSQLEngine:
    def __init__(self,connection_url):
        # TODO: change sqlmodel to sqlalchemy.
        self.alengine = sqlalchemy.create_engine(connection_url, echo=False)
        Base.metadata.create_all(self.alengine)
        Sessionmkr = sessionmaker(bind=self.alengine)
        self.alsession = Sessionmkr()
        self._local = threading.local()

        self.engine = create_engine(connection_url, echo=False, pool_pre_ping=True)
        self.SessionLocal = sessionmaker(bind=self.engine, class_=Session, expire_on_commit=False)
        # SessionLocal = sessionmaker(bind=self.engine)
        # self.session:Session = SessionLocal()

        Base.metadata.create_all(self.engine)
        SQLModel.metadata.create_all(self.engine)
        # SQLModel.metadata.drop_all(engine, schema="my_schema")

        # with Session(self.engine) as session:
        self.session = Session(bind=self.engine)

        self.cache = dict()

    @overload
    def __getitem__(self, key: Literal[DBCacheType.DynamicVoiceRoom]) -> list[int]: ...
    @overload
    def __getitem__(self, key: Literal[DBCacheType.VoiceLog, NotifyChannelType.VoiceLog]) -> dict[int, tuple[int, int | None]]: ...
    @overload
    def __getitem__(self, key: Literal[DBCacheType.TwitchCmd]) -> dict[int, dict[str, TwitchChatCommand]]: ...
    @overload
    def __getitem__(self, key: Literal[DBCacheType.DynamicVoiceLobby]) -> dict[int, DynamicVoiceLobby]: ...
    def __getitem__(self, key: DBCacheType | NotifyChannelType):
        """#**在使用 cache 時，若 key 找不到（通常為未執行初始化），會回傳 None，但在Type Hint中未標示**"""
        if isinstance(key, NotifyChannelType):
            return self.cache.get(DBCacheType.from_notify_channel(key))
        return self.cache.get(key)

    def __delitem__(self, key: DBCacheType | NotifyChannelType):
        if isinstance(key, NotifyChannelType):
            del self.cache[DBCacheType.from_notify_channel(key)]
        del self.cache[key]

    def __setitem__(self, key: DBCacheType | NotifyChannelType, value):
        if isinstance(key, NotifyChannelType):
            self.cache[DBCacheType.from_notify_channel(key)] = value
        self.cache[key] = value

    # @property
    # def alsession(self) -> Session:
    #     if not hasattr(self._local, "alsession"):
    #         raise RuntimeError("Session not initialized. Use inside a session context.")
    #     return self._local.alsession

    @contextmanager
    def session_scope(self) -> Generator[None, None, None]:
        self._local.alsession = self.SessionLocal()
        try:
            yield
            self.alsession.commit()
        except Exception:
            self.alsession.rollback()
            raise
        finally:
            self.alsession.close()
            del self._local.alsession

    def with_session(self, func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            with self.session_scope():
                return func(*args, **kwargs)

        return wrapper

    # * Base
    def add(self, db_obj):
        self.session.add(db_obj)
        self.session.commit()

    def batch_add(self, db_obj_list: list):
        if db_obj_list:
            for db_obj in db_obj_list:
                self.session.add(db_obj)
            self.session.commit()

    def merge(self, db_obj: T):  # type: ignore
        obj = self.session.merge(db_obj)
        self.session.commit()
        return obj

    def batch_merge(self, db_obj_list: list[T]):
        if db_obj_list:
            lst: list[T] = list()
            for db_obj in db_obj_list:
                lst.append(self.session.merge(db_obj))
            self.session.commit()
            return lst

    def delete(self, db_obj):
        self.session.delete(db_obj)
        self.session.commit()

    def expire(self, db_obj):
        # self.session.expunge(db_obj)
        self.session.expire(db_obj)

    def get(self, db_obj: T, primary_keys: tuple) -> T | None:
        return self.session.get(db_obj, primary_keys)  # type: ignore

    def exec_typed(self, stmt: Select[T]) -> Result[T]:  # type: ignore
        return self.alsession.execute(stmt)

class SQLUserSystem(BaseSQLEngine):
    # * User
    def get_cloud_user(self, discord_id: int):
        """
        Retrieve a CloudUser from the database based on the provided Discord ID.

        Args:
            discord_id (int): The Discord ID of the user to retrieve.

        Returns:
            CloudUser: The CloudUser object if found, otherwise a new CloudUser instance.
        """
        stmt = select(CloudUser).where(CloudUser.discord_id == discord_id)
        result = self.session.exec(stmt).one_or_none()
        return result if result is not None else CloudUser(discord_id=discord_id)

    def get_dcuser(self, discord_id: int, with_registration: bool = False):
        stmt = select(DiscordUser).where(DiscordUser.discord_id == discord_id)
        if with_registration:
            stmt = stmt.options(joinedload(DiscordUser.registration))
        result = self.session.exec(stmt).one_or_none()
        return result or DiscordUser(discord_id=discord_id)

    def get_cloud_user_privilege(self, discord_id: int):
        """
        Retrieve the privilege level of a CloudUser based on their Discord ID.

        Args:
            discord_id (int): The Discord ID of the user.

        Returns:
            PrivilegeLevel: The privilege level of the user.
        """
        stmt = select(CloudUser.privilege_level).where(CloudUser.discord_id == discord_id)
        result = self.session.exec(stmt).one_or_none()
        return PrivilegeLevel(result) if result else PrivilegeLevel.User

    @with_session
    def get_dcuser_test_session(self, discord_id: int, with_registration: bool = False):
        stmt = select(DiscordUser).where(DiscordUser.discord_id == discord_id)
        if with_registration:
            stmt = stmt.options(joinedload(DiscordUser.registration))
        result = self.alsession.exec(stmt).one_or_none()
        return result or DiscordUser(discord_id=discord_id)

    def get_main_account(self, alternate_account):
        stmt = select(UserAccount.main_account).where(UserAccount.alternate_account == alternate_account)
        result = self.session.exec(stmt).one_or_none()
        return result

    def get_alternate_account(self, main_account):
        stmt = select(UserAccount.alternate_account).where(UserAccount.main_account == main_account)
        result = self.session.exec(stmt).all()
        return result

    def get_raw_resgistrations(self):
        stmt = select(DiscordRegistration)
        result = self.session.exec(stmt).all()
        return {i.guild_id: i.role_id for i in result}

    def get_resgistration(self, registrations_id: int):
        stmt = select(DiscordRegistration).where(DiscordRegistration.registrations_id == registrations_id)
        result = self.session.exec(stmt).one_or_none()
        return result

    def get_resgistration_by_guildid(self,guild_id:int):
        stmt = select(DiscordRegistration).where(DiscordRegistration.guild_id == guild_id)
        result = self.session.exec(stmt).one_or_none()
        return result

    def get_raw_user_names(self):
        stmt = select(CloudUser).where(CloudUser.name is not None)
        result = self.session.exec(stmt).all()
        return {i.discord_id: i.name for i in result}

    def add_date(self, discord_id: int, target_date: date, name: str):
        """新增紀念日"""
        memorial_day = MemorialDay(discord_id=discord_id, target_date=target_date, name=name)
        self.session.add(memorial_day)
        self.session.commit()


class SQLCurrencySystem(BaseSQLEngine):
    def get_coin(self, discord_id: int):
        """取得用戶擁有的貨幣數"""
        stmt = select(UserPoint).where(UserPoint.discord_id == discord_id)
        result = self.session.exec(stmt).one_or_none()
        return result if result is not None else UserPoint(discord_id=discord_id)

    # def getif_coin(self,discord_id:int,amount:int,coin=Coins.Stardust) -> int | None:
    #     """取得指定貨幣足夠的用戶
    #     :return: 若足夠則回傳傳入的discord_id
    #     """
    #     coin = Coins(coin)
    #     self.cursor.execute(f"USE `stardb_user`;")
    #     self.cursor.execute(f'SELECT `discord_id` FROM `user_point` WHERE discord_id = %s AND `{coin.value}` >= %s;',(discord_id,amount))
    #     records = self.cursor.fetchall()
    #     if records:
    #         return records[0].get("discord_id")

    # def transfer_scoin(self,giver_id:int,given_id:int,amount:int):
    #     """轉移星幣
    #     :param giver_id: 給予點數者
    #     :param given_id: 被給予點數者
    #     :param amount: 轉移的點數數量
    #     """
    #     records = self.getif_coin(giver_id,amount)
    #     if records:
    #         self.cursor.execute(f"UPDATE `user_point` SET scoin = scoin - %s WHERE discord_id = %s;",(amount,giver_id))
    #         self.cursor.execute(f"INSERT INTO `user_point` SET discord_id = %s, scoin = %s ON DUPLICATE KEY UPDATE discord_id = %s, scoin = scoin + %s",(given_id,amount,given_id,amount))
    #         self.connection.commit()
    #         #self.cursor.execute(f"UPDATE `user_point` SET `point` = REPLACE(`欄位名`, '要被取代的欄位值', '取代後的欄位值') WHERE `欄位名` LIKE '%欄位值%';",(giver_id,amount))
    #     else:
    #         return "點數不足"

    # def user_sign(self,discord_id:int):
    #     '''新增簽到資料'''
    #     time = date.today()
    #     yesterday = time - timedelta(days=1)
    #     self.cursor.execute(f"USE `stardb_user`;")

    #     #檢測是否簽到過
    #     self.cursor.execute(f"SELECT `discord_id` FROM `user_sign` WHERE `discord_id` = {discord_id} AND `date` = '{time}';")
    #     record = self.cursor.fetchall()
    #     if record:
    #         return '已經簽到過了喔'

    #     #更新最後簽到日期+計算連續簽到
    #     self.cursor.execute(f"INSERT INTO `user_sign` VALUES(%s,%s,%s) ON DUPLICATE KEY UPDATE `consecutive_days` = CASE WHEN `date` = %s THEN `consecutive_days` + 1 ELSE 1 END, `date` = %s;",(discord_id,time,1,yesterday.isoformat(),time))
    #     #更新最大連續簽到日
    #     self.cursor.execute(f"UPDATE `user_discord` AS `data` JOIN `user_sign` AS `sign` ON `data`.`discord_id` = `sign`.`discord_id` SET `data`.`max_sign_consecutive_days` = `sign`.`consecutive_days` WHERE `sign`.`discord_id` = {discord_id} AND (`data`.`max_sign_consecutive_days` < `sign`.`consecutive_days` OR `data`.`max_sign_consecutive_days` IS NULL);")
    #     self.connection.commit()

    # def sign_add_coin(self,discord_id:int,scoin:int=0,Rcoin:int=0):
    #     """簽到獎勵點數"""
    #     self.cursor.execute(f"USE `stardb_user`;")
    #     self.cursor.execute(f"INSERT INTO `user_point` SET discord_id = %s, scoin = %s,rcoin = %s ON DUPLICATE KEY UPDATE scoin = scoin + %s, rcoin = rcoin + %s",(discord_id,scoin,Rcoin,scoin,Rcoin))
    #     self.connection.commit()

    # def get_scoin_shop_item(self,item_uid:int):
    #     self.cursor.execute(f"SELECT * FROM `stardb_idbase`.`scoin_shop` WHERE `item_uid` = {item_uid};")
    #     record = self.cursor.fetchall()
    #     if record:
    #         return ShopItem(record[0])

class SQLBetSystem(BaseSQLEngine):
    def get_bet(self, bet_id: int):
        """取得指定的賭注資料"""
        stmt = select(Bet).where(Bet.bet_id == bet_id)
        result = self.session.exec(stmt).one_or_none()
        return result

    def place_bet(self, bet_id: int, discord_id: int, bet_option: int, bet_amount: int):
        user_bet = UserBet(discord_id=discord_id, bet_id=bet_id, bet_option=bet_option, bet_amount=bet_amount, bet_time=datetime.now(tz=tz))
        self.session.add(user_bet)
        self.session.commit()
        return user_bet


#     def create_bet(self,bet_id:int,title:str,pink:str,blue:str):
#         self.cursor.execute(f"USE `database`;")
#         self.cursor.execute(f'INSERT INTO `bet_data` VALUES(%s,%s,%s,%s,%s);',(bet_id,title,pink,blue,True))
#         self.connection.commit()

#     def update_bet(self,bet_id:int):
#         self.cursor.execute(f"USE `database`;")
#         self.cursor.execute(f"UPDATE `bet_data` SET IsOn = %s WHERE bet_id = %s;",(False,bet_id))
#         self.connection.commit()

#     def get_bet_total(self,bet_id:int):
#         self.cursor.execute(f"USE `stardb_user`;")
#         self.cursor.execute(f'SELECT SUM(money) FROM `user_bet` WHERE `bet_id` = %s AND `choice` = %s;',(bet_id,'pink'))
#         total_pink = self.cursor.fetchone()
#         self.cursor.execute(f'SELECT SUM(money) FROM `user_bet` WHERE `bet_id` = %s AND `choice` = %s;',(bet_id,'blue'))
#         total_blue = self.cursor.fetchone()
#         return [int(total_pink['SUM(money)'] or 0),int(total_blue['SUM(money)'] or 0)]

#     def get_bet_winner(self,bet_id:int,winner:str):
#         self.cursor.execute(f"USE `stardb_user`;")
#         self.cursor.execute(f'SELECT * FROM `user_bet` WHERE `bet_id` = %s AND `choice` = %s;',(bet_id,winner))
#         records = self.cursor.fetchall()
#         return records

#     def remove_bet(self,bet_id:int):
#         self.cursor.execute(f'DELETE FROM `stardb_user`.`user_bet` WHERE `bet_id` = %s;',(bet_id,))
#         self.cursor.execute(f'DELETE FROM `database`.`bet_data` WHERE `bet_id` = %s;',(bet_id,))
#         self.connection.commit()

class SQLGameSystem(BaseSQLEngine):
    def get_user_game(self, discord_id: int, game: GameType):
        stmt = select(UserGame).where(UserGame.discord_id == discord_id, UserGame.game == game)
        result = self.session.exec(stmt).one_or_none()
        return result

    def get_user_game_all(self, discord_id: int):
        stmt = select(UserGame).where(UserGame.discord_id == discord_id)
        result = self.session.exec(stmt).all()
        return result

    def remove_user_game(self, discord_id: int, game: GameType):
        stmt = delete(UserGame).where(UserGame.discord_id == discord_id, UserGame.game == game)
        self.session.exec(stmt)
        self.session.commit()

    def get_lol_record_with_champion(self, puuid: str):
        """取得指定玩家的英雄戰績"""
        stmt = (
            select(LOLGameRecord.champion_id, func.count()).where(LOLGameRecord.puuid == puuid).group_by(LOLGameRecord.champion_id).order_by(desc(func.count()))
        )
        result = self.session.exec(stmt).all()
        return result

    def get_lol_record_with_win(self, puuid: str):
        """取得指定玩家的勝率"""
        stmt = select(LOLGameRecord.win, func.count()).where(LOLGameRecord.puuid == puuid).group_by(LOLGameRecord.win).order_by(desc(func.count()))
        result = self.session.exec(stmt).all()
        return {i: cnt for i, cnt in result}

class SQLPetSystem(BaseSQLEngine):
    def get_pet(self, discord_id: int):
        """取得寵物"""
        stmt = select(Pet).where(Pet.discord_id == discord_id)
        result = self.session.exec(stmt).one_or_none()
        return result

    def create_user_pet(self, discord_id: int, pet_species: str, pet_name: str):
        try:
            pet = Pet(discord_id=discord_id, pet_species=pet_species, pet_name=pet_name, food=20)
            self.session.add(pet)
            self.session.commit()
        except IntegrityError:
            return "已經有寵物了喔"

    def remove_user_pet(self, discord_id: int):
        stmt = delete(Pet).where(Pet.discord_id == discord_id)
        self.session.exec(stmt)
        self.session.commit()


class SQLNotifySystem(BaseSQLEngine):
    # * notify channel
    def add_notify_channel(self, guild_id: int, notify_type: NotifyChannelType, channel_id: int, role_id: int = None, message: str = None):
        """設定自動通知頻道"""
        channel = NotifyChannel(guild_id=guild_id, notify_type=notify_type, channel_id=channel_id, role_id=role_id, message=message)
        self.session.merge(channel)
        self.session.commit()

        cache_type = DBCacheType.from_notify_channel(notify_type)
        if cache_type:
            self.cache[cache_type] = self.get_notify_channel_rawdict(notify_type)

    def remove_notify_channel(self, guild_id: int, notify_type: NotifyChannelType):
        """移除自動通知頻道"""
        stmt = delete(NotifyChannel).where(NotifyChannel.guild_id == guild_id, NotifyChannel.notify_type == notify_type)
        self.session.exec(stmt)
        self.session.commit()

        cache_type = DBCacheType.from_notify_channel(notify_type)
        if cache_type:
            del self[cache_type][guild_id]

    def get_notify_channel(self, guild_id: int, notify_type: NotifyChannelType):
        """取得自動通知頻道"""
        statement = select(NotifyChannel).where(NotifyChannel.guild_id == guild_id, NotifyChannel.notify_type == notify_type)
        result = self.session.exec(statement).one_or_none()
        return result

    def get_notify_channel_by_type(self, notify_type: NotifyChannelType):
        """取得自動通知頻道（依據通知種類）"""
        statement = select(NotifyChannel).where(NotifyChannel.notify_type == notify_type)
        result = self.session.exec(statement).all()
        return result

    def get_notify_channel_rawdict(self, notify_type: NotifyChannelType):
        """取得自動通知頻道（原始dict）"""
        statement = select(NotifyChannel).where(NotifyChannel.notify_type == notify_type)
        result = self.session.exec(statement).all()
        return {data.guild_id: (data.channel_id, data.role_id) for data in result}

    def get_notify_channel_all(self, guild_id: str):
        """取得伺服器的所有自動通知頻道"""
        statement = select(NotifyChannel).where(NotifyChannel.guild_id == guild_id)
        result = self.session.exec(statement).all()
        return result

    # * notify community
    def add_notify_community(
        self,
        notify_type: NotifyCommunityType,
        community_id: str,
        guild_id: int,
        channel_id: int,
        role_id: int | None = None,
        message: str | None = None,
        cache_time: datetime | None = None,
    ):
        """設定社群通知"""
        community = NotifyCommunity(
            notify_type=notify_type,
            community_id=str(community_id),
            community_type=CommunityType.from_notify(notify_type),
            guild_id=guild_id,
            channel_id=channel_id,
            role_id=role_id,
            message=message,
        )
        self.session.merge(community)
        self.session.commit()

        # 新增快取
        if cache_time:
            cache = CommunityCache(community_id=community_id, notify_type=notify_type, value=cache_time)
            try:
                self.session.add(cache)
                self.session.commit()
            except IntegrityError:
                self.session.rollback()

    def remove_notify_community(self, notify_type: NotifyCommunityType, community_id: str, guild_id: int | None = None):
        """移除社群通知，同時判斷移除相關資料"""
        if guild_id is None:
            statement = delete(NotifyCommunity).where(NotifyCommunity.notify_type == notify_type, NotifyCommunity.community_id == community_id)
        else:
            statement = delete(NotifyCommunity).where(
                NotifyCommunity.notify_type == notify_type, NotifyCommunity.community_id == community_id, NotifyCommunity.guild_id == guild_id
            )
        self.session.exec(statement)
        self.session.commit()

        community_type = CommunityType.from_notify(notify_type)
        if community_type is None:
            return

        # 檢查是否還有其他通知使用此社群
        stmt = select(func.count()).where(NotifyCommunity.community_type == community_type, NotifyCommunity.community_id == community_id)
        count = self.session.exec(stmt).one()
        if not count:
            # 刪除社群資料
            stmt = delete(Community).where(Community.id == community_id, Community.type == community_type)
            self.session.exec(stmt)

            # 刪除社群快取
            stmt = delete(CommunityCache).where(CommunityCache.community_id == community_id, CommunityCache.notify_type == notify_type)
            self.session.exec(stmt)

            if community_type == CommunityType.Youtube:
                # 刪除推播紀錄
                stmt = delete(PushRecord).where(PushRecord.channel_id == community_id)
                self.session.exec(stmt)

            self.session.commit()

    def get_notify_community(self, notify_type: NotifyCommunityType):
        """取得社群通知（依據社群）"""
        statement = select(NotifyCommunity).where(NotifyCommunity.notify_type == notify_type)
        result = self.session.exec(statement).all()
        return result

    def get_notify_community_rawlist(self, notify_type: NotifyCommunityType):
        """取得自動通知頻道（原始list）"""
        statement = select(NotifyCommunity.community_id).where(NotifyCommunity.notify_type == notify_type).distinct()
        result = self.session.exec(statement).all()
        return result

    def get_notify_community_guild(self, notify_type: NotifyCommunityType, community_id: str):
        """取得指定社群的所有通知"""
        notify_type = NotifyCommunityType(notify_type)
        statement = select(NotifyCommunity.guild_id, NotifyCommunity.channel_id, NotifyCommunity.role_id, NotifyCommunity.message).where(
            NotifyCommunity.notify_type == notify_type.value, NotifyCommunity.community_id == community_id
        )
        return self.session.exec(statement).all()

    def get_notify_community_user_byid(self, notify_type: NotifyCommunityType, community_id: str, guild_id: int):
        """取得伺服器內的指定社群通知"""
        statement = (
            select(NotifyCommunity)
            .join(Community, and_(NotifyCommunity.community_id == Community.id, NotifyCommunity.community_type == Community.type))
            .where(NotifyCommunity.notify_type == notify_type, Community.id == community_id, NotifyCommunity.guild_id == guild_id)
        )
        result = self.session.exec(statement).one_or_none()
        return result

    def get_notify_community_user_byname(self, notify_type: NotifyCommunityType, community_username: str, guild_id: int):
        """取得伺服器內的指定社群通知"""
        statement = (
            select(NotifyCommunity)
            .join(Community, and_(NotifyCommunity.community_id == Community.id, NotifyCommunity.community_type == Community.type))
            .where(NotifyCommunity.notify_type == notify_type, Community.username == community_username, NotifyCommunity.guild_id == guild_id)
        )
        result = self.session.exec(statement).one_or_none()
        return result

    def get_notify_community_userlist(self, notify_type: NotifyCommunityType):
        """取得指定類型的社群通知清單"""
        statement = select(NotifyCommunity.community_id).distinct().where(NotifyCommunity.notify_type == notify_type)
        result = self.session.exec(statement).all()
        return result

    def get_notify_community_list(self, notify_type: NotifyCommunityType, guild_id: int):
        """取得伺服器內指定種類的所有通知"""
        statement = (
            select(NotifyCommunity, Community)
            .join(Community, and_(NotifyCommunity.community_id == Community.id, NotifyCommunity.community_type == Community.type))
            .where(NotifyCommunity.notify_type == notify_type, NotifyCommunity.guild_id == guild_id)
        )
        result = self.session.exec(statement).all()
        return result

    def get_notify_community_count(self, notify_type: NotifyCommunityType, community_id: str):
        """取得指定通知的數量"""
        statement = select(func.count()).where(NotifyCommunity.notify_type == notify_type, NotifyCommunity.community_id == community_id)
        result = self.session.exec(statement).one()
        return result

    def get_community_by_notify(self, notify: NotifyCommunity):
        """取得指定通知的社群資料"""
        statement = select(Community).where(Community.id == notify.community_id, Community.type == notify.community_type)
        result = self.session.exec(statement).one()
        return result

    def update_community_name(self, community_type: CommunityType, community_id: str, username: str, display_name: str):
        """更新社群名稱"""
        stmt = select(Community).where(Community.id == community_id, Community.type == community_type)
        community = self.session.exec(stmt).one_or_none()
        if community and (community.username != username or community.display_name != display_name):
            community.username = username
            community.display_name = display_name
            self.session.merge(community)

    def get_expired_push_records(self):
        refresh_time = datetime.now() - timedelta(hours=6)
        statement = select(PushRecord).where(PushRecord.expire_at < refresh_time)
        result = self.session.exec(statement).all()
        return result

    def get_push_record(self, ytchannel_id: str):
        """取得推播紀錄"""
        stmt = select(PushRecord).where(PushRecord.channel_id == ytchannel_id)
        result = self.session.exec(stmt).one_or_none()
        return result or PushRecord(channel_id=ytchannel_id)

    def remove_push_record(self, ytchannel_id: str):
        """移除推播紀錄"""
        stmt = delete(PushRecord).where(PushRecord.channel_id == ytchannel_id)
        self.session.exec(stmt)
        self.session.commit()

class SQLDynamicVoiceSystem(BaseSQLEngine):
    def add_dynamic_voice_lobby(self, guild_id: int, channel_id: int, default_room_name: str | None = None):
        """新增動態語音大廳"""
        lobby = DynamicVoiceLobby(guild_id=guild_id, channel_id=channel_id, default_room_name=default_room_name)
        lobby = self.session.merge(lobby)
        self.session.commit()
        if self[DBCacheType.DynamicVoiceLobby] is not None:
            self[DBCacheType.DynamicVoiceLobby][channel_id] = lobby

    def get_all_dynamic_voice_lobby(self):
        """取得目前所有的動態語音大廳"""
        statement = select(DynamicVoiceLobby)
        result = self.session.exec(statement).all()
        return {i.channel_id: i for i in result}

    def get_dynamic_voice_lobby(self, guild_id: int):
        """取得指定伺服器的動態語音大廳"""
        statement = select(DynamicVoiceLobby).where(DynamicVoiceLobby.guild_id == guild_id)
        result = self.session.exec(statement).one_or_none()
        return result

    def remove_dynamic_voice_lobby(self, guild_id: int):
        """移除動態語音大廳"""
        lobby = self.get_dynamic_voice_lobby(guild_id)
        stmt = delete(DynamicVoiceLobby).where(DynamicVoiceLobby.guild_id == guild_id)
        self.session.exec(stmt)
        self.session.commit()

        if self[DBCacheType.DynamicVoiceLobby] is not None and lobby is not None:
            del self[DBCacheType.DynamicVoiceLobby][lobby.channel_id]

    def get_all_dynamic_voice(self):
        """取得目前所有的動態語音"""
        statement = select(DynamicVoice.channel_id)
        result = self.session.exec(statement).all()
        return result

    def add_dynamic_voice(self, channel_id, creator_id, guild_id):
        """設定動態語音"""
        voice = DynamicVoice(channel_id=channel_id, creator_id=creator_id, guild_id=guild_id)
        self.session.add(voice)
        self.session.commit()
        if self[DBCacheType.DynamicVoiceRoom] is not None:
            self[DBCacheType.DynamicVoiceRoom].append(channel_id)

    def remove_dynamic_voice(self, channel_id):
        """移除動態語音"""
        stmt = delete(DynamicVoice).where(DynamicVoice.channel_id == channel_id)
        self.session.exec(stmt)
        self.session.commit()
        if self[DBCacheType.DynamicVoiceRoom] is not None:
            self[DBCacheType.DynamicVoiceRoom].remove(channel_id)

    def batch_remove_dynamic_voice(self, channel_ids: list[int]):
        """批次移除動態語音"""
        if not channel_ids:
            return
        stmt = delete(DynamicVoice).where(DynamicVoice.channel_id.in_(channel_ids))
        self.session.exec(stmt)
        self.session.commit()
        if self[DBCacheType.DynamicVoiceRoom] is not None:
            for channel_id in channel_ids:
                if channel_id in self[DBCacheType.DynamicVoiceRoom]:
                    self[DBCacheType.DynamicVoiceRoom].remove(channel_id)

class SQLRoleSaveSystem(BaseSQLEngine):
    # * role_save
    def get_role_save(self, discord_id: int):
        stmt = select(RoleSave).where(RoleSave.discord_id == discord_id).order_by(RoleSave.time, desc(RoleSave.role_id))
        result = self.session.exec(stmt).all()
        return result

    def get_role_save_count(self, discord_id: int):
        stmt = select(func.count()).select_from(RoleSave).where(RoleSave.discord_id == discord_id)
        result = self.session.exec(stmt).one_or_none()
        return result

    def get_role_save_count_list(self):
        stmt = select(RoleSave.discord_id,func.count()).select_from(RoleSave).group_by(RoleSave.discord_id).order_by(desc(func.count()))
        result = self.session.exec(stmt).all()
        return {i[0]: i[1] for i in result}

    def add_role_save(self,discord_id:int,role:discord.Role):
        role_save = RoleSave(discord_id=discord_id, role_id=role.id, role_name=role.name, time=role.created_at.date())
        self.session.merge(role_save)
        self.session.commit()

    #* ReactionRole
    def get_reaction_roles_all(self) -> dict[int, list[ReactionRole]]:
        stmt = select(ReactionRole)
        result = self.session.exec(stmt).all()
        dct = dict()
        for i in result:
            if i.message_id not in dct:
                dct[i.message_id] = list()
            dct[i.message_id].append(i)
        return dct

    def get_reaction_roles_by_message(self, message_id: int):
        stmt = select(ReactionRole).where(ReactionRole.message_id == message_id)
        result = self.session.exec(stmt).all()
        return result

    def get_reaction_role_message_all(self):
        stmt = select(ReactionRoleMessage)
        result = self.session.exec(stmt).all()
        return result

    def get_reaction_role_message(self, message_id: int):
        stmt = select(ReactionRoleMessage).where(ReactionRoleMessage.message_id == message_id)
        result = self.session.exec(stmt).one_or_none()
        return result

    def delete_reaction_role_message(self, message_id:int):
        stmt = delete(ReactionRoleMessage).where(ReactionRoleMessage.message_id == message_id)
        self.session.exec(stmt)

        stmt = delete(ReactionRole).where(ReactionRole.message_id == message_id)
        self.session.exec(stmt)
        self.session.commit()

    def delete_reaction_role(self, message_id:int, role_id:int):
        stmt = delete(ReactionRole).where(ReactionRole.message_id == message_id, ReactionRole.role_id == role_id)
        self.session.exec(stmt)
        self.session.commit()

class SQLWarningSystem(BaseSQLEngine):
    #* warning
    def add_warning(self, discord_id:int, moderate_type:WarningType, moderate_user:int, create_guild:int, create_time:datetime, reason:str=None, last_time:timedelta=None, guild_only=True) -> int:
        """給予用戶警告\n
        returns: 新增的warning_id
        """
        warning = UserModerate(discord_id=discord_id,moderate_type=moderate_type,moderate_user=moderate_user,create_guild=create_guild,create_time=create_time,reason=reason,last_time=last_time,guild_only=guild_only, officially_given=create_guild in Jsondb.config["debug_guilds"]) #type: ignore
        self.session.add(warning)
        self.session.commit()
        return warning.warning_id

    def get_warning(self,warning_id:int):
        """取得警告單"""
        stmt = select(UserModerate).where(UserModerate.warning_id == warning_id)
        result = self.session.exec(stmt).one_or_none()
        return result

    def get_warnings(self, discord_id: int, guild_id: int = None):
        """取得用戶的警告列表
        :param guild_id: 若給予，則額外查詢該伺服器內的紀錄
        """
        if guild_id:
            stmt = select(UserModerate).where(UserModerate.discord_id == discord_id, or_(not_(UserModerate.guild_only), UserModerate.create_guild == guild_id))
        else:
            stmt = select(UserModerate).where(UserModerate.discord_id == discord_id, not_(UserModerate.guild_only))
        result = self.session.exec(stmt).all()
        return WarningList(result, discord_id)

    def get_warnings_count(self,discord_id:int,guild_id:int=None):
        if guild_id:
            stmt = select(func.count()).where(UserModerate.discord_id == discord_id, UserModerate.create_guild == guild_id)
        else:
            stmt = select(func.count()).where(UserModerate.discord_id == discord_id, not_(UserModerate.guild_only))
        result = self.session.exec(stmt).one()
        return result

    def remove_warning(self,warning_id:int):
        """移除用戶警告"""
        stmt = delete(UserModerate).where(UserModerate.warning_id == warning_id)
        self.session.exec(stmt)
        self.session.commit()

    def get_warning_count(self, discord_id: int, guild_id: int) -> int:
        """查詢自上次禁言後的警告次數"""
        # 查找該用戶最後一次禁言的時間
        last_ban_time_query = select(UserModerate).where(
            UserModerate.discord_id == discord_id,
            UserModerate.create_guild == guild_id,
            UserModerate.moderate_type == WarningType.Timeout
        ).order_by(desc(UserModerate.create_time)).limit(1)

        last_ban_time_result = self.session.exec(last_ban_time_query).first()

        # 如果該用戶沒有被禁言過，則最後禁言時間為當前時間
        if last_ban_time_result is None:
            last_ban_time = datetime.min.replace(tzinfo=timezone.utc)
        else:
            last_ban_time = last_ban_time_result.create_time

        # 查找該用戶在最後一次禁言後的警告次數
        warning_count_query = select(func.count()).where(
            UserModerate.discord_id == discord_id,
            UserModerate.create_guild == guild_id,
            UserModerate.moderate_type == WarningType.Warning,
            UserModerate.create_time > last_ban_time
        )

        warning_count = self.session.exec(warning_count_query).one()

        return warning_count

class SQLPollSystem(BaseSQLEngine):
    #* poll
    def remove_poll(self,poll_id:int):
        self.session.exec(delete(Poll).where(Poll.poll_id == poll_id))
        self.session.exec(delete(UserPoll).where(Poll.poll_id == poll_id))
        self.session.exec(delete(PollOption).where(Poll.poll_id == poll_id))
        self.session.commit()

    def get_poll(self,poll_id:int):
        stmt = select(Poll).where(Poll.poll_id == poll_id)
        result = self.session.exec(stmt).one_or_none()
        return result

    def get_active_polls(self):
        stmt = select(Poll).where(Poll.end_at.is_(None))
        result = self.session.exec(stmt).all()
        return result

    def get_poll_options(self,poll_id:int):
        stmt = select(PollOption).where(PollOption.poll_id == poll_id)
        result = self.session.exec(stmt).all()
        return result

    def add_poll_option(self,poll_id:int,options:list):
        lst = list()
        count = 0
        for option in options:
            count += 1
            lst.append(PollOption(poll_id=poll_id, option_id=count, option_name=option))

        self.session.add_all(lst)
        self.session.commit()

    def set_user_poll(
        self,
        poll_id: int,
        discord_id: int,
        vote_option: int,
        vote_at: datetime | None = None,
        vote_magnification: int = 1,
        max_can_vote: int | None = None,
    ):
        """
        Sets the user's poll vote in the database.

        Args:
            poll_id (int): The ID of the poll.
            discord_id (int): The ID of the user on Discord.
            vote_option (int): The option the user voted for.
            vote_at (datetime, optional): The timestamp of the vote. Defaults to None.
            vote_magnification (int, optional): The magnification of the vote. Defaults to 1.
            max_can_vote (int, optional): The maximum number of votes the user can cast. Defaults to None.

        Returns:
            int: The result of the operation.
                -1 if the user's vote was deleted,\n
                1 if the user's vote was inserted or updated, \n
                2 if the user's vote reach the max poll can vote.

        Raises:
            SQLNotFoundError: If the poll with the given ID is not found in the database.
        """
        count = self.get_user_vote_count(poll_id, discord_id) if max_can_vote else 0
        stmt = select(UserPoll).where(UserPoll.poll_id == poll_id, UserPoll.discord_id == discord_id, UserPoll.vote_option == vote_option)
        result = self.session.exec(stmt).one_or_none()
        if result:
            # 已投選項->取消
            self.session.delete(result)
            text = -1

        elif max_can_vote is not None and count >= max_can_vote:
            # 未投選項+已達到最大投票數
            return 2

        else:
            # 未投選項->投票
            vote = UserPoll(poll_id=poll_id, discord_id=discord_id, vote_option=vote_option, vote_at=vote_at, vote_magnification=vote_magnification)
            self.session.add(vote)
            text = 1

        self.session.commit()
        return text

    def get_user_vote_count(self, poll_id, discord_id):
        stmt = select(func.count()).where(UserPoll.poll_id == poll_id, UserPoll.discord_id == discord_id)
        result = self.session.exec(stmt).one()
        return result

    def add_user_poll(self, poll_id: int, discord_id: int, vote_option: int, vote_at: datetime, vote_magnification: int = 1):
        self.session.merge(UserPoll(poll_id=poll_id, discord_id=discord_id, vote_option=vote_option, vote_at=vote_at, vote_magnification=vote_magnification))
        self.session.commit()

    def remove_user_poll(self,poll_id:int,discord_id:int):
        stmt = delete(UserPoll).where(UserPoll.poll_id == poll_id, UserPoll.discord_id == discord_id)
        self.session.exec(stmt)
        self.session.commit()

    def get_user_poll(self, poll_id: int, discord_id: int):
        stmt = (
            select(UserPoll, PollOption.option_name)
            .select_from(UserPoll)
            .join(PollOption, and_(UserPoll.vote_option == PollOption.option_id, UserPoll.poll_id == PollOption.poll_id), isouter=True)
            .where(UserPoll.poll_id == poll_id, UserPoll.discord_id == discord_id)
        )
        result = self.session.exec(stmt).all()
        return result

    def get_users_poll(self,poll_id:int,include_alternatives_accounts=True):
        if include_alternatives_accounts:
            stmt = select(UserPoll).where(UserPoll.poll_id == poll_id)
        else:
            stmt = (
                select(UserPoll)
                .select_from(UserPoll)
                .join(UserAccount, UserPoll.discord_id == UserAccount.alternate_account)
                .where(
                    UserPoll.poll_id == poll_id, UserAccount.alternate_account is None
                )
            )
        result = self.session.exec(stmt).all()
        return result

    def get_poll_vote_count(self, poll_id: int, include_alternatives_accounts=True):
        if include_alternatives_accounts:
            stmt = select(UserPoll.vote_option, func.sum(UserPoll.vote_magnification)).where(UserPoll.poll_id == poll_id).group_by(UserPoll.vote_option)
        else:
            stmt = (
                select(UserPoll.vote_option, func.sum(UserPoll.vote_magnification))
                .select_from(UserPoll)
                .join(UserAccount, UserPoll.discord_id == UserAccount.alternate_account)
                .where(UserPoll.poll_id == poll_id, UserAccount.alternate_account is None)
                .group_by(UserPoll.vote_option)
            )
        result = self.session.exec(stmt).all()
        return {str(i[0]): i[1] for i in result}

    def get_poll_role(self, poll_id: int, is_only_role: bool | None = None):
        if is_only_role is not None:
            stmt = select(PollRole).where(PollRole.poll_id == poll_id, PollRole.is_only_role == is_only_role)
        else:
            stmt = select(PollRole).where(PollRole.poll_id == poll_id)
        result = self.session.exec(stmt).all()
        return result

    # * Giveaway
    def get_user_in_giveaway(self, giveaway_id: int, discord_id: int):
        stmt = select(GiveawayUser).where(GiveawayUser.giveaway_id == giveaway_id, GiveawayUser.user_id == discord_id)
        result = self.session.exec(stmt).one_or_none()
        return result

    def get_giveaway_users(self, giveaway_id:int):
        stmt = select(GiveawayUser).where(GiveawayUser.giveaway_id == giveaway_id)
        result = self.session.exec(stmt).all()
        return result

    def get_giveaway(self, giveaway_id:int):
        stmt = select(Giveaway).where(Giveaway.id == giveaway_id)
        result = self.session.exec(stmt).one_or_none()
        return result

    def get_active_giveaways(self):
        stmt = select(Giveaway).where(Giveaway.is_on)
        result = self.session.exec(stmt).all()
        return result

    def set_giveaway_winner(self, giveaway_id:int, winners_id:list[int]):
        for winner in winners_id:
            stmt = update(GiveawayUser).where(GiveawayUser.giveaway_id == giveaway_id, GiveawayUser.user_id == winner).values(is_winner = True)
            self.session.exec(stmt)

        self.session.commit()

    def reset_giveaway_winner(self, giveaway_id:int):
        stmt = update(GiveawayUser).where(GiveawayUser.giveaway_id == giveaway_id).values(is_winner=False).where(GiveawayUser.is_winner)
        self.session.exec(stmt)
        self.session.commit()


class SQLElectionSystem(BaseSQLEngine):
    # * party
    def join_party(self, discord_id: int, party_id: int):
        up = UserParty(discord_id=discord_id, party_id=party_id)
        self.session.add(up)
        self.session.commit()

    def leave_party(self, discord_id: int, party_id: int):
        up = UserParty(discord_id=discord_id, party_id=party_id)
        self.session.delete(up)
        self.session.commit()

    def get_all_party_data(self):
        stmt = (
            select(Party, func.count(UserParty.party_id).label("member_count"))
            .join(UserParty, Party.party_id == UserParty.party_id, isouter=True)
            .group_by(Party.party_id)
            .order_by(Party.party_id)
        )
        result = self.session.exec(stmt).all()
        return result

    def get_user_party(self, discord_id: int):
        stmt = select(Party).select_from(UserParty).join(Party, UserParty.party_id == Party.party_id, isouter=True).where(UserParty.discord_id == discord_id)
        result = self.session.exec(stmt).all()
        return result

    def get_party(self, party_id: int):
        stmt = select(Party).where(Party.party_id == party_id)
        result = self.session.exec(stmt).one_or_none()
        return result


class SQLTwitchSystem(BaseSQLEngine):
    # * twitch
    def get_bot_join_channel_all(self):
        stmt = select(TwitchBotJoinChannel)
        result = self.session.exec(stmt).all()
        return {i.twitch_id: i for i in result}

    def list_chat_command_by_channel(self, channel_id:int):
        stmt = select(TwitchChatCommand).where(TwitchChatCommand.twitch_id == channel_id)
        result = self.session.exec(stmt).all()
        return result

    def get_chat_command(self, command: str, channel_id: int):
        stmt = select(TwitchChatCommand).where(TwitchChatCommand.twitch_id == channel_id, TwitchChatCommand.name == command)
        result = self.session.exec(stmt).one_or_none()
        return result

    def get_raw_chat_command_all(self):
        stmt = select(TwitchChatCommand)
        result = self.session.exec(stmt).all()
        dct = {i.twitch_id: dict() for i in result}
        for i in result:
            dct[i.twitch_id][i.name] = i
        return dct

    def get_raw_chat_command_channel(self, twitch_id: int):
        stmt = select(TwitchChatCommand).where(TwitchChatCommand.twitch_id == twitch_id)
        result = self.session.exec(stmt).all()
        return {i.name: i.response for i in result}

    def get_chat_command_names(self):
        stmt = select(TwitchChatCommand.twitch_id,TwitchChatCommand.name)
        return self.session.exec(stmt).all()

    def get_twitch_point(self, twitch_id: int, broadcaster_id: int):
        stmt = select(TwitchPoint).where(TwitchPoint.twitch_id == twitch_id, TwitchPoint.broadcaster_id == broadcaster_id)
        result = self.session.exec(stmt).one_or_none()
        return result or TwitchPoint(twitch_id=twitch_id, broadcaster_id=broadcaster_id)

    def update_twitch_point(self, twitch_id:int, broadcaster_id:int, point:int):
        stmt = select(TwitchPoint).where(TwitchPoint.twitch_id == twitch_id, TwitchPoint.broadcaster_id == broadcaster_id)
        result = self.session.exec(stmt).one_or_none()
        if result:
            result.point += point
            self.session.merge(result)
        else:
            self.session.add(TwitchPoint(twitch_id=twitch_id, broadcaster_id=broadcaster_id, point=point))
        self.session.commit()


class SQLRPGSystem(BaseSQLEngine):
    def get_user_rpg(self, discord_id):
        stmt = select(RPGUser).where(RPGUser.discord_id == discord_id)
        result = self.session.exec(stmt).one_or_none()
        return result or RPGUser(discord_id=discord_id)

    def get_rpg_dungeon(self, dungeon_id):
        stmt = select(RPGDungeon).where(RPGDungeon.id == dungeon_id)
        result = self.session.exec(stmt).one()
        return result

    def get_monster(self, monster_id):
        stmt = select(Monster).where(Monster.id == monster_id)
        result = self.session.exec(stmt).one()
        return result

    def get_player_item(self, discord_id, item_id):
        stmt = select(RPGPlayerItem).where(RPGPlayerItem.discord_id == discord_id, RPGPlayerItem.item_id == item_id)
        result = self.session.exec(stmt).one_or_none()
        return result

    def get_player_equipments(self, discord_id):
        stmt = select(RPGEquipment).where(RPGEquipment.discord_id == discord_id)
        result = self.session.exec(stmt).all()
        return result

class SQLTRPGSystem(BaseSQLEngine):
    def get_trpg_plot(self, plot_id):
        stmt = select(TRPGStoryPlot).where(TRPGStoryPlot.id == plot_id)
        result = self.session.exec(stmt).one()
        return result

    def get_trpg_cheracter(self, discord_id):
        stmt = select(TRPGCharacter).where(TRPGCharacter.discord_id == discord_id)
        result = self.session.exec(stmt).one_or_none()
        return result

    def get_trpg_cheracter_ability(self, discord_id, ability_id):
        stmt = select(TRPGCharacterAbility).where(TRPGCharacterAbility.discord_id == discord_id, TRPGCharacterAbility.ability_id == ability_id)
        result = self.session.exec(stmt).one()
        return result

class SQLBackupSystem(BaseSQLEngine):
    #* backup
    def backup_role(self,role:discord.Role,description:str=None):
        backup_role = BackupRole(role_id=role.id,role_name=role.name,created_at=role.created_at.astimezone(tz),guild_id=role.guild.id,colour_r=role.colour.r,colour_g=role.colour.g,colour_b=role.colour.b,description=description)
        self.session.add(backup_role)
        for member in role.members:
            self.session.add(BackupRoleUser(role_id=role.id,discord_id=member.id))
        self.session.commit()

    def get_backup_roles_userlist(self,role_id:int):
        stmt = select(BackupRoleUser.discord_id).where(BackupRoleUser.role_id == role_id)
        result = self.session.exec(stmt).all()
        return result

    def get_all_backup_roles(self):
        stmt = select(BackupRole)
        result = self.session.exec(stmt).all()
        return result

    def backup_category(self, category: discord.CategoryChannel, description: str = None):
        backup_category = BackupCategory(
            category_id=category.id,
            name=category.name,
            created_at=category.created_at.astimezone(tz),
            guild_id=category.guild.id,
            description=description,
        )
        self.session.add(backup_category)
        self.session.commit()

    def backup_channel(self, channel: discord.abc.GuildChannel, description: str = None):
        backup_channel = BackupChannel(
            channel_id=channel.id,
            name=channel.name,
            created_at=channel.created_at.astimezone(tz),
            guild_id=channel.guild.id,
            category_id=channel.category_id,
            description=description,
        )
        self.session.add(backup_channel)
        self.session.commit()

    def backup_message(self, message: discord.Message, description: str = None):
        backup_message = BackupMessage(
            message_id=message.id,
            channel_id=message.channel.id,
            content=message.content,
            created_at=message.created_at.astimezone(tz),
            author_id=message.author.id,
            description=description,
        )
        self.session.add(backup_message)
        self.session.commit()

    def backup_messages(self, messages: list[discord.Message]):
        for message in messages:
            backup_message = BackupMessage(
                message_id=message.id,
                channel_id=message.channel.id,
                content=message.content,
                created_at=message.created_at.astimezone(tz),
                author_id=message.author.id,
                description=None,
            )
            self.session.add(backup_message)
        self.session.commit()


class SQLTokensSystem(BaseSQLEngine):
    def set_oauth(self, user_id: int, type: CommunityType, access_token: str, refresh_token: str = None, expires_at: datetime = None):
        token = OAuth2Token(user_id=user_id, type=type, access_token=access_token, refresh_token=refresh_token, expires_at=expires_at)
        self.session.merge(token)
        self.session.commit()

    def get_oauth(self, user_id: str, type: CommunityType):
        stmt = select(OAuth2Token).where(OAuth2Token.user_id == user_id, OAuth2Token.type == type)
        result = self.session.exec(stmt).one_or_none()
        return result

    def get_bot_token(self, api_type: APIType, token_seq: int = 1):
        stmt = select(BotToken).where(BotToken.api_type == api_type, BotToken.token_seq == token_seq).limit(1)
        return self.session.exec(stmt).one()

    def get_google_credentials(self, token_seq: int = 2):
        token = self.get_bot_token(APIType.Google, token_seq)
        return Credentials(
            token=token.access_token,
            refresh_token=token.refresh_token,
            client_id=token.client_id,
            client_secret=token.client_secret,
            token_uri="https://oauth2.googleapis.com/token",
            scopes=["https://www.googleapis.com/auth/drive"],
            expiry=token.expires_at,
        )

    def get_google_client_config(self, token_seq: int = 3):
        token = self.get_bot_token(APIType.Google, token_seq)
        if token_seq in (2,):
            client_config = {
                "installed": {
                    "client_id": token.client_id,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                    "client_secret": token.client_secret,
                    "redirect_uris": ["http://localhost"],
                }
            }
        else:
            client_config = {
                "web": {
                    "client_id": token.client_id,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                    "client_secret": token.client_secret,
                }
            }

        return client_config


class SQLCacheSystem(BaseSQLEngine):
    def set_community_caches(self, type: NotifyCommunityType, data: dict[str, datetime | None]):
        """批量設定社群快取"""
        for community_id, value in data.items():
            cache = CommunityCache(community_id=community_id, notify_type=type, value=value)
            if value is None:
                self.session.exec(delete(CommunityCache).where(CommunityCache.community_id == community_id, CommunityCache.notify_type == type))
            else:
                self.session.merge(cache)
        self.session.commit()

    def set_community_cache(self, type: NotifyCommunityType, community_id: str, value: datetime | None):
        """設定社群快取"""
        if value is None:
            self.session.exec(delete(CommunityCache).where(CommunityCache.community_id == community_id, CommunityCache.notify_type == type))
        else:
            cache = CommunityCache(community_id=community_id, notify_type=type, value=value)
            self.session.merge(cache)
        self.session.commit()

    def add_community_cache(self, type: NotifyCommunityType, community_id: str, value: datetime | None):
        """新增社群快取"""
        cache = CommunityCache(community_id=community_id, notify_type=type, value=value)
        try:
            self.session.add(cache)
            self.session.commit()
        except IntegrityError:
            self.session.rollback()

    def get_community_cache(self, type: NotifyCommunityType, community_id: str):
        """取得社群快取"""
        stmt = select(CommunityCache).where(CommunityCache.notify_type == type, CommunityCache.community_id == community_id)
        result = self.session.exec(stmt).one_or_none()
        return result

    def get_community_caches(self, type: NotifyCommunityType):
        stmt = (
            select(NotifyCommunity.community_id, CommunityCache)
            .select_from(NotifyCommunity)
            .join(
                CommunityCache,
                and_(NotifyCommunity.community_id == CommunityCache.community_id, NotifyCommunity.notify_type == CommunityCache.notify_type),
                isouter=True,
            )
            .where(NotifyCommunity.notify_type == type)
            .distinct()
        )
        result = self.session.exec(stmt).all()
        return {i[0]: i[1] for i in result}

    def get_community_cache_with_default(self, type: NotifyCommunityType, community_id: str):
        """取得指定社群的快取"""
        stmt = select(CommunityCache).where(CommunityCache.notify_type == type, CommunityCache.community_id == community_id)
        result = self.session.exec(stmt).one_or_none()
        return result or CommunityCache(community_id=community_id, notify_type=type, value=datetime.min.replace(tzinfo=timezone.utc))

    def set_notify_cache(self, type: NotifyChannelType, value: datetime | None):
        """設定通知快取"""
        if value is None:
            self.session.exec(delete(NotifyCache).where(NotifyCache.notify_type == type))
        else:
            cache = NotifyCache(notify_type=type, value=value)
            self.session.merge(cache)
        self.session.commit()

    def get_notify_cache(self, type: NotifyChannelType):
        """取得通知快取"""
        stmt = select(NotifyCache).where(NotifyCache.notify_type == type)
        result = self.session.exec(stmt).one_or_none()
        return result

    def get_yt_cache(self, video_id: str):
        """取得YouTube快取"""
        stmt = select(YoutubeCache).where(YoutubeCache.video_id == video_id)
        result = self.session.exec(stmt).one_or_none()
        return result

    def add_yt_cache(self, video_id: str, scheduled_live_start: datetime):
        """新增YouTube快取"""
        cache = YoutubeCache(video_id=video_id, scheduled_live_start=scheduled_live_start)
        try:
            self.session.add(cache)
            self.session.commit()
        except IntegrityError:
            self.session.rollback()

    def remove_yt_cache(self, video_id: str):
        """移除YouTube快取"""
        stmt = delete(YoutubeCache).where(YoutubeCache.video_id == video_id)
        self.session.exec(stmt)
        self.session.commit()

    def get_lol_cache(self, puuid: str):
        """取得LOL快取"""
        stmt = select(LOLGameCache).where(LOLGameCache.puuid == puuid)
        result = self.session.exec(stmt).one_or_none()
        return result

class SQLNetwork(BaseSQLEngine):
    def set_ips_last_seen(self, data: dict[tuple[str, str], datetime]):
        """設定IP最後出現時間"""
        for (ip, mac), last_seen in data.items():
            cache = IPLastSeen(ip=ip, mac=mac, last_seen=last_seen)
            self.session.merge(cache)
        self.session.commit()

class SQLTest(BaseSQLEngine):
    pass


# class MYSQLElectionSystem(MySQLBaseModel):
#     def add_election(self,discord_id:int,session:int,position,represent_party_id:int=None):
#         position = Position(position)
#         self.cursor.execute(f"INSERT INTO `database`.`candidate_list` VALUES(%s,%s,%s,%s);",(discord_id,session,position.value,represent_party_id))
#         self.connection.commit()

#     def remove_election(self,discord_id:int,session:int,position=None):
#         if position:
#             position = Position(position)
#             self.cursor.execute(f"DELETE FROM `database`.`candidate_list` WHERE `discord_id` = %s AND `session` = %s AND `position` = %s;",(discord_id,session,position.value))
#         else:
#             self.cursor.execute(f"DELETE FROM `database`.`candidate_list` WHERE `discord_id` = %s AND `session` = %s;",(discord_id,session))
#         self.connection.commit()

#     def get_election_by_session(self,session:int):
#         self.cursor.execute(f"SELECT * FROM `database`.`candidate_list` WHERE session = {session};")
#         records = self.cursor.fetchall()
#         return records

#     def get_election_full_by_session(self,session:int):
#         self.cursor.execute(f"""
#             SELECT
#                 cl.discord_id,
#                 cl.session,
#                 cl.position,
#                 COALESCE(cl.represent_party_id, up.party_id) AS party_id,
#                 pd.party_name,
#                 pd.role_id
#             FROM
#                 `database`.`candidate_list` cl
#                     LEFT JOIN
#                 `stardb_user`.`user_party` up ON cl.discord_id = up.discord_id
#                     LEFT JOIN
#                 `database`.`party_data` pd ON COALESCE(cl.represent_party_id, up.party_id) = pd.party_id
#             WHERE
#                 session = {session};
#         """)
#         return self.cursor.fetchall()

#     def get_election_by_session_position(self,session:int,position=str):
#         position = Position(position)
#         self.cursor.execute(f"SELECT * FROM `database`.`candidate_list` WHERE session = {session} AND position = {position.value};")
#         records = self.cursor.fetchall()
#         return records

#     def get_election_count(self,session:int):
#         self.cursor.execute(f"SELECT position,count(*) AS count FROM `database`.`candidate_list` WHERE session = {session} GROUP BY position ORDER BY `position`;")
#         records = self.cursor.fetchall()
#         return records

#     def add_official(self, discord_id, session, position):
#         self.cursor.execute(f"INSERT INTO `database`.`official_list` VALUES(%s,%s,%s);",(discord_id,session,position))
#         self.connection.commit()

#     def add_officials(self, lst:list[list[int, int, int]]):
#         self.cursor.executemany(f"INSERT INTO `database`.`official_list` VALUES(%s,%s,%s);",lst)
#         self.connection.commit()

#     def join_party(self,discord_id:int,party_id:int):
#         self.cursor.execute(f"INSERT INTO `stardb_user`.`user_party` VALUES(%s,%s);",(discord_id,party_id))
#         self.connection.commit()

#     def leave_party(self,discord_id:int,party_id:int):
#         self.cursor.execute(f"DELETE FROM `stardb_user`.`user_party` WHERE `discord_id` = %s AND `party_id` = %s;",(discord_id,party_id))
#         self.connection.commit()

#     def get_all_party_data(self):
#         self.cursor.execute(f"""
#             SELECT
#                 `party_data`.*, COUNT(`user_party`.party_id) AS member_count
#             FROM
#                 `database`.`party_data`
#                     LEFT JOIN
#                 `stardb_user`.`user_party` ON party_data.party_id = user_party.party_id
#             GROUP BY `party_id`
#             ORDER BY `party_id`;
#         """)
#         records = self.cursor.fetchall()
#         return [Party(**i) for i in records]

#     def get_user_party(self,discord_id:int):
#         self.cursor.execute(f"SELECT `user_party`.discord_id,`party_data`.* FROM `stardb_user`.`user_party` LEFT JOIN `database`.`party_data` ON user_party.party_id = party_data.party_id WHERE `discord_id` = {discord_id}")
#         records = self.cursor.fetchall()
#         return [Party(**i) for i in records]

#     def get_party_data(self,party_id:int):
#         self.cursor.execute(f"SELECT * FROM `database`.`party_data` WHERE `party_id` = {party_id};")
#         records = self.cursor.fetchall()
#         if records:
#             return Party(**records[0])


class SQLEngine(
    SQLUserSystem,
    SQLCurrencySystem,
    SQLBetSystem,
    SQLGameSystem,
    SQLPetSystem,
    SQLNotifySystem,
    SQLDynamicVoiceSystem,
    SQLRoleSaveSystem,
    SQLWarningSystem,
    SQLPollSystem,
    SQLElectionSystem,
    SQLTwitchSystem,
    SQLRPGSystem,
    SQLTRPGSystem,
    SQLBackupSystem,
    SQLTokensSystem,
    SQLCacheSystem,
    SQLNetwork,
    SQLTest,
):
    """SQL引擎"""

    dict_type = [DBCacheType.DynamicVoiceLobby, DBCacheType.VoiceLog, DBCacheType.TwitchCmd]
    list_type = [DBCacheType.DynamicVoiceRoom]

    def init_cache(self):
        """初始化快取"""
        self.update_notify_channel(NotifyChannelType.VoiceLog)
        self[DBCacheType.DynamicVoiceLobby] = self.get_all_dynamic_voice_lobby()
        self[DBCacheType.DynamicVoiceRoom] = self.get_all_dynamic_voice()
        self[DBCacheType.TwitchCmd] = self.get_raw_chat_command_all()
        log.debug("dbcache: init.")

    def update_notify_channel(self, notify_type: NotifyChannelType):
        """更新通知頻道"""
        cache_type = DBCacheType.from_notify_channel(notify_type)
        if cache_type:
            self[cache_type] = self.get_notify_channel_rawdict(notify_type)

    def getif_dynamic_voice_room(self, channel_id: int):
        """取得動態語音房間"""
        return channel_id if channel_id in self[DBCacheType.DynamicVoiceRoom] else None

    def add_twitch_cmd(self, twitch_channel_id: int, command: str, response: str):
        """新增Twitch指令"""
        self.session.merge(TwitchChatCommand(twitch_id=twitch_channel_id, name=command, response=response))
        self.session.commit()

        self[DBCacheType.TwitchCmd][int(twitch_channel_id)] = self.get_raw_chat_command_channel(twitch_channel_id)

    def remove_twitch_cmd(self, twitch_channel_id: int, command: str):
        """移除Twitch指令"""
        self.session.exec(delete(TwitchChatCommand).where(TwitchChatCommand.twitch_id == twitch_channel_id, TwitchChatCommand.name == command))
        self.session.commit()

        self[DBCacheType.TwitchCmd][int(twitch_channel_id)] = self.get_raw_chat_command_channel(twitch_channel_id)

    def get_twitch_cmd_response_cache(self, twitch_channel_id_input: int, command: str):
        """取得Twitch指令回應"""
        twitch_channel_id = int(twitch_channel_id_input)
        if twitch_channel_id in self[DBCacheType.TwitchCmd]:
            return self[DBCacheType.TwitchCmd][twitch_channel_id].get(command)
        return None
