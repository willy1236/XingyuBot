from datetime import date, datetime, time, timedelta, timezone
from typing import TYPE_CHECKING, Optional, Tuple, TypeVar, overload

import discord
import mysql.connector
import sqlalchemy
from mysql.connector.errors import Error as sqlerror
from sqlalchemy import and_, delete, desc, func, or_
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, SQLModel, create_engine, select

from starlib.models.mysql import Community, NotifyCommunity
from ..models.sqlSchema import Base

from ..errors import *
from ..fileDatabase import Jsondb
from ..models.mysql import *
from ..models.rpg import *
from ..settings import tz
from ..types import *
from ..utils import log

SQLsettings = Jsondb.config["SQLsettings"]

O = TypeVar("O")
class DBCache:
    def __init__(self):
        self.cache = {i.value: dict() for i in DBCacheType}

    def __setitem__(self, key, value):
        cache_key = DBCacheType.map(key)
        if cache_key:
            self.cache[cache_key.value][key] = value
        else:
            self.cache[key] = value

    def __delitem__(self, key):
        try:
            cache_key = DBCacheType.map(key)
            if cache_key:
                del self.cache[cache_key][key]
            else:
                del self.cache[key]
        except KeyError:
            log.warning(f"dbcache KeyError: {key}")
            pass

    @overload
    def __getitem__(self, key:str) -> list[int]:
        ...
    @overload
    def __getitem__(self, key:NotifyChannelType) -> dict[int, tuple[int, Optional[int]]]:
        ...
    @overload
    def __getitem__(self, key:NotifyCommunityType) -> list[str]:
        ...

    def __getitem__(self, key):
        try:
            cache_key = DBCacheType.map(key)
            if cache_key:
                value = self.cache[cache_key.value][key]
            else:
                value = self.cache[key]
            return value
        except KeyError:
            log.warning(f"dbcache KeyError: {key}")
            return None
    
    def get(self, key):
        cache_key = DBCacheType.map(key)
        if cache_key:
            value = self.cache[cache_key.value].get(key)
        else:
            value = self.cache.get(key)
        return value

class BaseSQLEngine:
    def __init__(self,connection_url):
        self.alengine = sqlalchemy.create_engine(connection_url, echo=False)
        Base.metadata.create_all(self.alengine)
        Sessionmkr = sessionmaker(bind=self.alengine)
        self.alsession = Sessionmkr()

        self.engine = create_engine(connection_url, echo=False, pool_pre_ping=True)
        # SessionLocal = sessionmaker(bind=self.engine)
        # self.session:Session = SessionLocal()
        
        SQLModel.metadata.create_all(self.engine)
        # SQLModel.metadata.drop_all(engine, schema="my_schema")

        # with Session(self.engine) as session:
        self.session = Session(bind=self.engine)

        self.cache = DBCache()

    #* Base
    def add(self, db_obj):
        self.session.add(db_obj)
        self.session.commit()
    
    def batch_add(self, db_obj_list:list):
        if db_obj_list:
            for db_obj in db_obj_list:
                self.session.add(db_obj)
            self.session.commit()

    def merge(self, db_obj):
        self.session.merge(db_obj)
        self.session.commit()

    def batch_merge(self, db_obj_list:list):
        if db_obj_list:
            for db_obj in db_obj_list:
                self.session.merge(db_obj)
            self.session.commit()

    def delete(self, db_obj):
        self.session.delete(db_obj)
        self.session.commit()

    def expire(self, db_obj):
        #self.session.expunge(db_obj)
        self.session.expire(db_obj)

    def get(self, db_obj:O, primary_keys:tuple) -> O | None:
        return self.session.get(db_obj, primary_keys)
    
class SQLUserSystem(BaseSQLEngine):
    #* User
    def get_cloud_user(self, discord_id:int):
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

    def get_dcuser(self, discord_id:int):
        stmt = select(DiscordUser).where(DiscordUser.discord_id == discord_id)
        result = self.session.exec(stmt).one_or_none()
        return result
    
    def get_main_account(self, alternate_account):
        stmt = select(UserAccount.main_account).where(UserAccount.alternate_account == alternate_account)
        result = self.session.exec(stmt).one_or_none()
        return result
        
    def get_alternate_account(self,main_account):
        stmt = select(UserAccount.alternate_account).where(UserAccount.main_account == main_account)
        result = self.session.exec(stmt).all()
        return result
    
    def get_raw_resgistrations(self):
        stmt = select(DiscordRegistration)
        result = self.session.exec(stmt).all()
        return {i.guild_id: i.role_id for i in result}
    
    def get_resgistration(self, registrations_id:int):
        stmt = select(DiscordRegistration).where(DiscordRegistration.registrations_id == registrations_id)
        result = self.session.exec(stmt).one_or_none()
        return result
        
    def get_resgistration_by_guildid(self,guild_id:int):
        stmt = select(DiscordRegistration).where(DiscordRegistration.guild_id == guild_id)
        result = self.session.exec(stmt).one_or_none()
        return result

class SQLCurrencySystem(BaseSQLEngine):
    def get_coin(self,discord_id:int):
        """取得用戶擁有的貨幣數"""
        stmt = select(UserPoint).where(UserPoint.discord_id == discord_id)
        result = self.session.exec(stmt).one_or_none()
        return result if result is not None else UserPoint(discord_id=discord_id)

    def getif_coin(self,discord_id:int,amount:int,coin=Coins.Stardust) -> int | None:
        """取得指定貨幣足夠的用戶
        :return: 若足夠則回傳傳入的discord_id
        """
        coin = Coins(coin)
        self.cursor.execute(f"USE `stardb_user`;")
        self.cursor.execute(f'SELECT `discord_id` FROM `user_point` WHERE discord_id = %s AND `{coin.value}` >= %s;',(discord_id,amount))
        records = self.cursor.fetchall()
        if records:
            return records[0].get("discord_id")

    def transfer_scoin(self,giver_id:int,given_id:int,amount:int):
        """轉移星幣
        :param giver_id: 給予點數者
        :param given_id: 被給予點數者
        :param amount: 轉移的點數數量
        """
        records = self.getif_coin(giver_id,amount)
        if records:
            self.cursor.execute(f"UPDATE `user_point` SET scoin = scoin - %s WHERE discord_id = %s;",(amount,giver_id))
            self.cursor.execute(f"INSERT INTO `user_point` SET discord_id = %s, scoin = %s ON DUPLICATE KEY UPDATE discord_id = %s, scoin = scoin + %s",(given_id,amount,given_id,amount))
            self.connection.commit()
            #self.cursor.execute(f"UPDATE `user_point` SET `point` = REPLACE(`欄位名`, '要被取代的欄位值', '取代後的欄位值') WHERE `欄位名` LIKE '%欄位值%';",(giver_id,amount))
        else:
            return "點數不足"

    def user_sign(self,discord_id:int):
        '''新增簽到資料'''
        time = date.today()
        yesterday = time - timedelta(days=1)
        self.cursor.execute(f"USE `stardb_user`;")

        #檢測是否簽到過
        self.cursor.execute(f"SELECT `discord_id` FROM `user_sign` WHERE `discord_id` = {discord_id} AND `date` = '{time}';")
        record = self.cursor.fetchall()
        if record:
            return '已經簽到過了喔'

        #更新最後簽到日期+計算連續簽到
        self.cursor.execute(f"INSERT INTO `user_sign` VALUES(%s,%s,%s) ON DUPLICATE KEY UPDATE `consecutive_days` = CASE WHEN `date` = %s THEN `consecutive_days` + 1 ELSE 1 END, `date` = %s;",(discord_id,time,1,yesterday.isoformat(),time))
        #更新最大連續簽到日
        self.cursor.execute(f"UPDATE `user_discord` AS `data` JOIN `user_sign` AS `sign` ON `data`.`discord_id` = `sign`.`discord_id` SET `data`.`max_sign_consecutive_days` = `sign`.`consecutive_days` WHERE `sign`.`discord_id` = {discord_id} AND (`data`.`max_sign_consecutive_days` < `sign`.`consecutive_days` OR `data`.`max_sign_consecutive_days` IS NULL);")
        self.connection.commit()

    def sign_add_coin(self,discord_id:int,scoin:int=0,Rcoin:int=0):
        """簽到獎勵點數"""
        self.cursor.execute(f"USE `stardb_user`;")
        self.cursor.execute(f"INSERT INTO `user_point` SET discord_id = %s, scoin = %s,rcoin = %s ON DUPLICATE KEY UPDATE scoin = scoin + %s, rcoin = rcoin + %s",(discord_id,scoin,Rcoin,scoin,Rcoin))
        self.connection.commit()
    
    def get_scoin_shop_item(self,item_uid:int):
        self.cursor.execute(f"SELECT * FROM `stardb_idbase`.`scoin_shop` WHERE `item_uid` = {item_uid};")
        record = self.cursor.fetchall()
        if record:
            return ShopItem(record[0])

class SQLGameSystem(BaseSQLEngine):
    def get_user_game(self, discord_id:int, game:GameType):
        stmt = select(UserGame).where(UserGame.discord_id == discord_id, UserGame.game == game)
        result = self.session.exec(stmt).one_or_none()
        return result
    
    def get_user_game_all(self, discord_id:int):
        stmt = select(UserGame).where(UserGame.discord_id == discord_id)
        result = self.session.exec(stmt).all()
        return result

    def remove_user_game(self, discord_id:int, game:GameType):
        stmt = delete(UserGame).where(UserGame.discord_id == discord_id, UserGame.game == game)
        self.session.exec(stmt)
        self.session.commit()

class SQLPetSystem(BaseSQLEngine):
    def get_pet(self,discord_id:int):
        """取得寵物"""
        stmt = select(Pet).where(Pet.discord_id == discord_id)
        result = self.session.exec(stmt).one_or_none()
        return result

    def create_user_pet(self,discord_id:int,pet_species:str,pet_name:str):
        try:
            pet = Pet(discord_id=discord_id, pet_species=pet_species, pet_name=pet_name, food=20)
            self.session.add(pet)
            self.session.commit()
        except IntegrityError:
            return "已經有寵物了喔"

    def remove_user_pet(self,discord_id:int):
        stmt = delete(Pet).where(Pet.discord_id == discord_id)
        self.session.exec(stmt)
        self.session.commit()

class SQLNotifySystem(BaseSQLEngine):
    #* notify channel
    def add_notify_channel(self,guild_id:int,notify_type:NotifyChannelType,channel_id:int,role_id:int=None, message:str=None):
        """設定自動通知頻道"""
        channel = NotifyChannel(guild_id=guild_id, notify_type=notify_type, channel_id=channel_id, role_id=role_id, message=message)
        self.session.merge(channel)
        self.session.commit()

        if self.cache.get(notify_type):
            self.cache[notify_type][guild_id] = (channel_id, role_id)

    def remove_notify_channel(self,guild_id:int,notify_type:NotifyChannelType):
        """移除自動通知頻道"""
        stmt = delete(NotifyChannel).where(
            NotifyChannel.guild_id == guild_id,
            NotifyChannel.notify_type == notify_type
        )
        self.session.exec(stmt)
        self.session.commit()

        if self.cache.get(notify_type):
            del self.cache[notify_type][guild_id]
    
    def get_notify_channel(self,guild_id:str,notify_type:NotifyChannelType):
        """取得自動通知頻道"""
        statement = select(NotifyChannel).where(NotifyChannel.guild_id == guild_id, NotifyChannel.notify_type == notify_type)
        result = self.session.exec(statement).one_or_none()
        return result

    def get_notify_channel_by_type(self,notify_type:NotifyChannelType):
        """取得自動通知頻道（依據通知種類）"""
        statement = select(NotifyChannel).where(NotifyChannel.notify_type == notify_type)
        result = self.session.exec(statement).all()
        return result

    def get_notify_channel_dict(self, notify_type:NotifyChannelType):
        """取得自動通知頻道（原始dict）"""
        statement = select(NotifyChannel).where(NotifyChannel.notify_type == notify_type)
        result = self.session.exec(statement).all()
        return {data.guild_id: (data.channel_id, data.role_id) for data in result}
    
    def get_notify_channel_all(self,guild_id:str):
        """取得伺服器的所有自動通知頻道"""
        statement = select(NotifyChannel).where(NotifyChannel.guild_id == guild_id)
        result = self.session.exec(statement).all()
        return result

    def get_all_dynamic_voice(self):
        """取得目前所有的動態語音"""
        statement = select(DynamicChannel.channel_id)
        result = self.session.exec(statement).all()
        return result
    
    def add_dynamic_voice(self, channel_id, creator_id, guild_id, created_at=None):
        """設定動態語音"""
        voice = DynamicChannel(channel_id=channel_id, creator_id=creator_id, guild_id=guild_id, created_at=created_at)
        self.session.add(voice)
        self.session.commit()
        if self.cache.get(NotifyChannelType.DynamicVoice):
            self.cache[NotifyChannelType.DynamicVoice].append(channel_id)

    def remove_dynamic_voice(self,channel_id):
        """移除動態語音"""
        stmt = delete(DynamicChannel).where(DynamicChannel.channel_id == channel_id)
        self.session.exec(stmt)
        self.session.commit()
        if self.cache.get(NotifyChannelType.DynamicVoice):
            self.cache[NotifyChannelType.DynamicVoice].remove(channel_id)

    #* notify community
    def add_notify_community(self, notify_type:NotifyCommunityType, community_id:str, community_type:CommunityType, guild_id:int, channel_id:int, role_id:int=None, message:str=None):
        """設定社群通知"""
        community = NotifyCommunity(notify_type=notify_type, community_id=community_id, community_type=community_type, guild_id=guild_id, channel_id=channel_id, role_id=role_id, message=message)
        self.session.merge(community)
        self.session.commit()

        if self.get(notify_type):
            self.cache[notify_type].append(community_id)

    def remove_notify_community(self,notify_type:NotifyCommunityType, community_id:str, guild_id:int):
        """移除社群通知，同時判斷移除社群"""
        statement = delete(NotifyCommunity).where(
            NotifyCommunity.notify_type == notify_type,
            NotifyCommunity.community_id == community_id,
            NotifyCommunity.guild_id == guild_id
        )
        self.session.exec(statement)
        self.session.commit()
        community_type = notify_to_community_map.get(notify_type)
        if community_type is not None:
            self.remove_community(community_type, community_id)
        
        if self.cache.get(notify_type):
            self.cache[notify_type].remove(community_id)

    def get_notify_community(self, notify_type:NotifyCommunityType):
        """取得社群通知（依據社群）"""
        statement = select(NotifyCommunity).where(NotifyCommunity.notify_type == notify_type)
        result = self.session.exec(statement).all()
        return result
    
    def get_notify_community_rawlist(self, notify_type:NotifyCommunityType):
        """取得自動通知頻道（原始list）"""
        statement = select(NotifyCommunity.community_id).where(NotifyCommunity.notify_type == notify_type).distinct()
        result = self.session.exec(statement).all()
        return result

    def get_notify_community_guild(self, notify_type:NotifyCommunityType, community_id:str):
        """取得指定社群的所有通知"""
        statement = select(NotifyCommunity.guild_id, NotifyCommunity.channel_id, NotifyCommunity.role_id, NotifyCommunity.message).where(NotifyCommunity.notify_type == notify_type, NotifyCommunity.community_id == community_id)
        result = self.session.exec(statement).all()
        return {i[0]: (i[1], i[2], i[3]) for i in result}
        

    def get_notify_community_user_byid(self,notify_type:NotifyCommunityType, community_id:str, guild_id:int):
        """取得伺服器內的指定社群通知"""
        statement = select(NotifyCommunity).join(Community, and_(NotifyCommunity.community_id == Community.id, NotifyCommunity.community_type == Community.type)).where(NotifyCommunity.notify_type == notify_type, Community.id == community_id, NotifyCommunity.guild_id == guild_id)
        result = self.session.exec(statement).one_or_none()
        return result
    
    def get_notify_community_user_bylogin(self,notify_type:NotifyCommunityType, community_login:str, guild_id:int):
        """取得伺服器內的指定社群通知"""
        statement = select(NotifyCommunity).join(Community, and_(NotifyCommunity.community_id == Community.id, NotifyCommunity.community_type == Community.type)).where(NotifyCommunity.notify_type == notify_type, Community.login == community_login, NotifyCommunity.guild_id == guild_id)
        result = self.session.exec(statement).one_or_none()
        return result

    def get_notify_community_userlist(self, notify_type:NotifyCommunityType):
        """取得指定類型的社群通知清單"""
        statement = select(NotifyCommunity.community_id).distinct().where(NotifyCommunity.notify_type == notify_type)
        result = self.session.exec(statement).all()
        return result

    def get_notify_community_list(self,notify_type:NotifyCommunityType, guild_id:int) -> list[Tuple[NotifyCommunity, Community]]:
        """取得伺服器內指定種類的所有通知"""
        statement = select(NotifyCommunity, Community).join(Community, and_(NotifyCommunity.community_id == Community.id, NotifyCommunity.community_type == Community.type)).where(NotifyCommunity.notify_type == notify_type, NotifyCommunity.guild_id == guild_id)
        result = self.session.exec(statement).all()
        return result
    
    def get_notify_community_count(self, notify_type:NotifyCommunityType, community_id:str):
        """取得指定通知的數量"""
        statement = select(func.count()).where(NotifyCommunity.notify_type == notify_type, NotifyCommunity.community_id == community_id)
        result = self.session.exec(statement).one()
        return result

    def remove_community(self, community_type:CommunityType, community_id:str):
        """在沒有設定任何通知下移除社群"""
        statement = select(func.count()).where(NotifyCommunity.community_type == community_type, NotifyCommunity.community_id == community_id)
        result = self.session.exec(statement).one()
        if not result:
            statement = delete(Community).where(Community.id == community_id, Community.type == community_type)
            self.session.exec(statement)
            self.session.commit()

    def get_expired_push_records(self):
        now = datetime.now()
        statement = select(PushRecord).where(PushRecord.expire_at < now)
        result = self.session.exec(statement).all()
        return result

class SQLRoleSaveSystem(BaseSQLEngine):
    #* role_save
    def get_role_save(self,discord_id:int):
        stmt = select(RoleSave).where(RoleSave.discord_id == discord_id).order_by(RoleSave.time, desc(RoleSave.role_id))
        result = self.session.exec(stmt).all()
        return result

    def get_role_save_count(self,discord_id:int):
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
    
    def get_reaction_roles_by_message(self, message_id:int) -> list[ReactionRole]:
        stmt = select(ReactionRole).where(ReactionRole.message_id == message_id)
        result = self.session.exec(stmt).all()
        return result
    
    def get_reaction_role_message_all(self):
        stmt = select(ReactionRoleMessage)
        result = self.session.exec(stmt).all()
        return result
    
    def get_reaction_role_message(self, message_id:int):
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
    def add_warning(self,discord_id:int,moderate_type:WarningType,moderate_user:int,create_guild:int,create_time:datetime,reason:str=None,last_time:str=None,guild_only=True) -> int:
        """給予用戶警告\n
        returns: 新增的warning_id
        """
        warning = UserModerate(discord_id=discord_id,moderate_type=moderate_type,moderate_user=moderate_user,create_guild=create_guild,create_time=create_time,reason=reason,last_time=last_time,guild_only=guild_only, officially_given=create_guild in Jsondb.config["debug_guilds"])
        self.session.add(warning)
        self.session.commit()
        return warning.warning_id

    def get_warning(self,warning_id:int):
        """取得警告單"""
        stmt = select(UserModerate).where(UserModerate.warning_id == warning_id)
        result = self.session.exec(stmt).one_or_none()
        return result
    
    def get_warnings(self,discord_id:int,guild_id:int=None):
        """取得用戶的警告列表
        :param guild_id: 若給予，則同時查詢該伺服器的紀錄
        """
        if guild_id:
            stmt = select(UserModerate).where(UserModerate.discord_id == discord_id, UserModerate.create_guild == guild_id)
        else:
            stmt = select(UserModerate).where(UserModerate.discord_id == discord_id, UserModerate.guild_only == False)
        result = self.session.exec(stmt).all()
        return WarningList(result, discord_id)
    
    def get_warnings_count(self,discord_id:int,guild_id:int=None):
        if guild_id:
            stmt = select(func.count()).where(UserModerate.discord_id == discord_id, UserModerate.create_guild == guild_id)
        else:
            stmt = select(func.count()).where(UserModerate.discord_id == discord_id, UserModerate.guild_only == False)
        result = self.session.exec(stmt).one()
        return result

    def remove_warning(self,warning_id:int):
        """移除用戶警告"""
        stmt = delete(UserModerate).where(UserModerate.warning_id == warning_id)
        self.session.exec(stmt)
        self.session.commit()

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
        stmt = select(Poll).where(Poll.is_on == True)
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

    def set_user_poll(self, poll_id: int, discord_id: int, vote_option: int = None, vote_at: datetime = None, vote_magnification: int = 1, max_can_vote:int = None):
        """
        Sets the user's poll vote in the database.

        Args:
            poll_id (int): The ID of the poll.
            discord_id (int): The ID of the user on Discord.
            vote_option (int, optional): The option the user voted for. Defaults to None.
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
        count = 0
        if max_can_vote:
            count = self.get_user_vote_count(poll_id,discord_id)
            if count > max_can_vote:
                return 2

        vote = UserPoll(poll_id=poll_id,discord_id=discord_id,vote_option=vote_option,vote_at=vote_at,vote_magnification=vote_magnification)
        stmt = select(UserPoll).where(UserPoll.poll_id == poll_id, UserPoll.discord_id == discord_id, UserPoll.vote_option == vote_option)
        result = self.session.exec(stmt).one_or_none()
        if result:
            self.session.delete(vote)
            text = -1
        
        elif count == max_can_vote:
            return 2
        
        else:
            self.session.add(vote)
            text = 1
        
        self.session.commit()
        return text

    def get_user_vote_count(self,poll_id,discord_id):
        stmt = select(func.count()).where(UserPoll.poll_id == poll_id, UserPoll.discord_id == discord_id)
        result = self.session.exec(stmt).one_or_none()
        return result

    def add_user_poll(self,poll_id:int,discord_id:int,vote_option:int,vote_at:datetime,vote_magnification:int=1):
        self.session.merge(UserPoll(poll_id=poll_id,discord_id=discord_id,vote_option=vote_option,vote_at=vote_at,vote_magnification=vote_magnification))
        self.session.commit()
    
    def remove_user_poll(self,poll_id:int,discord_id:int):
        stmt = delete(UserPoll).where(UserPoll.poll_id == poll_id, UserPoll.discord_id == discord_id)
        self.session.exec(stmt)
        self.session.commit()
    
    def get_user_poll(self,poll_id:int,discord_id:int):
        stmt = select(UserPoll, PollOption.option_name).select_from(UserPoll).join(PollOption, and_(UserPoll.vote_option == PollOption.option_id, UserPoll.poll_id == PollOption.poll_id), isouter=True).where(UserPoll.poll_id == poll_id, UserPoll.discord_id == discord_id)
        result = self.session.exec(stmt).all()
        return result
    
    def get_users_poll(self,poll_id:int,include_alternatives_accounts=True):
        if include_alternatives_accounts:
            stmt = select(UserPoll).where(UserPoll.poll_id == poll_id)
        else:
            stmt = select(UserPoll).select_from(UserPoll).join(UserAccount, UserPoll.discord_id == UserAccount.alternate_account).where(UserPoll.poll_id == poll_id, UserAccount.alternate_account == None)
        result = self.session.exec(stmt).all()
        return result
    
    def get_poll_vote_count(self,poll_id:int,include_alternatives_accounts=True):
        if include_alternatives_accounts:
            stmt = select(UserPoll.vote_option,func.sum(UserPoll.vote_magnification)).where(UserPoll.poll_id == poll_id).group_by(UserPoll.vote_option)
        else:
            stmt = select(UserPoll.vote_option,func.sum(UserPoll.vote_magnification)).select_from(UserPoll).join(UserAccount, UserPoll.discord_id == UserAccount.alternate_account).where(UserPoll.poll_id == poll_id, UserAccount.alternate_account == None).group_by(UserPoll.vote_option)
        result = self.session.exec(stmt).all()
        return {str(i[0]): i[1] for i in result}
    
    def get_poll_role(self,poll_id:int,is_only_role:int=None):
        if is_only_role:
            stmt = select(PollRole).where(PollRole.poll_id == poll_id, PollRole.is_only_role == is_only_role)
        else:
            stmt = select(PollRole).where(PollRole.poll_id == poll_id)
        result = self.session.exec(stmt).all()
        return result
    
class SQLElectionSystem(BaseSQLEngine):
    #* party
    def join_party(self,discord_id:int,party_id:int):
        up = UserParty(discord_id=discord_id,party_id=party_id)
        self.session.add(up)
        self.session.commit()

    def leave_party(self,discord_id:int,party_id:int):
        up = UserParty(discord_id=discord_id,party_id=party_id)
        self.session.delete(up)
        self.session.commit()

    def get_all_party_data(self):
        stmt = (
            select(Party,func.count(UserParty.party_id).label('member_count'))
            .join(UserParty, Party.party_id == UserParty.party_id, isouter=True)
            .group_by(Party.party_id)
            .order_by(Party.party_id)
        )
        result = self.session.exec(stmt).all()
        return result
    
    def get_user_party(self,discord_id:int):
        stmt = select(Party).select_from(UserParty).join(Party, UserParty.party_id == Party.party_id, isouter=True).where(UserParty.discord_id == discord_id)
        result = self.session.exec(stmt).all()
        return result
    
    def get_party(self,party_id:int):
        stmt = select(Party).where(Party.party_id == party_id)
        result = self.session.exec(stmt).one_or_none()
        return result

class SQLTwitchSystem(BaseSQLEngine):    
    #* twitch
    def get_bot_join_channel_all(self):
        stmt = select(TwitchBotJoinChannel)
        result = self.session.exec(stmt).all()
        return {i.twitch_id: i.action_channel_id for i in result}
    
    def list_chat_command_by_channel(self, channel_id:str):
        stmt = select(TwitchChatCommand).where(TwitchChatCommand.twitch_id == channel_id)
        result = self.session.exec(stmt).all()
        return result
    
    def get_chat_command(self, command:str, channel_id:str):
        stmt = select(TwitchChatCommand).where(TwitchChatCommand.twitch_id == channel_id, TwitchChatCommand.name == command)
        result = self.session.exec(stmt).one_or_none()
        return result

class SQLRPGSystem(BaseSQLEngine):
    def get_user_rpg(self, discord_id):
        stmt = select(RPGUser).where(RPGUser.discord_id == discord_id)
        result = self.session.exec(stmt).one_or_none()
        return result
    
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
    
class SQLTokensSystem(BaseSQLEngine):
    def set_oauth(self, user_id:int, type:CommunityType, access_token:str, refresh_token:str=None, expires_at:datetime=None):
        token = OAuth2Token(user_id=user_id,type=type,access_token=access_token,refresh_token=refresh_token,expires_at=expires_at)
        self.session.merge(token)
        self.session.commit()

    def get_oauth(self, user_id:int, type:CommunityType):
        stmt = select(OAuth2Token).where(OAuth2Token.user_id == user_id, OAuth2Token.type == type)
        result = self.session.exec(stmt).one_or_none()
        return result
    
    def get_bot_token(self, type:CommunityType):
        stmt = select(BotToken).where(OAuth2Token.type == type).limit(1)
        return self.session.exec(stmt).one()

class SQLTest(BaseSQLEngine):
    pass

class MySQLBaseModel(object):
    """MySQL資料庫基本模型"""
    def __init__(self,mysql_settings:dict):
        '''MySQL 資料庫連接\n
        settings = {"host": "","port": ,"user": "","password": "","db": "","charset": ""}
        '''
        #建立連線
        self.connection = mysql.connector.connect(**mysql_settings)
        self.cursor = self.connection.cursor(dictionary=True)

    def truncate_table(self,table:str,database="database"):
        self.cursor.execute(f"USE `{database}`;")
        self.cursor.execute(f"TRUNCATE TABLE `{table}`;")
    
    def set_userdata(self,discord_id:int,table:str,column:str,value):
        """設定或更新用戶資料（只要PK為discord_id的皆可）"""
        self.cursor.execute(f"USE `stardb_user`;")
        self.cursor.execute(f"INSERT INTO `{table}` SET discord_id = {discord_id}, {column} = {value} ON DUPLICATE KEY UPDATE discord_id = {discord_id}, {column} = {value};")
        self.connection.commit()

    def get_userdata(self,discord_id:int,table:str='user_discord'):
        """取得用戶資料（只要PK為discord_id的皆可）"""
        self.cursor.execute(f"USE `stardb_user`;")
        self.cursor.execute(f'SELECT * FROM `{table}` WHERE discord_id = %s;',(discord_id,))
        records = self.cursor.fetchall()
        if records:
            return records[0]

    def remove_userdata(self,discord_id:int,table:str='user_discord'):
        """移除用戶資料（只要PK為discord_id的皆可）"""
        self.cursor.execute(f"USE `stardb_user`;")
        self.cursor.execute(f"DELETE FROM `{table}` WHERE `discord_id` = %s;",(discord_id,))
        self.connection.commit()

    def add_userdata_value(self,discord_id:int,table:str,column:str,value):
        """增加用戶數值資料的值（只要PK為discord_id的皆可）"""
        self.cursor.execute(f"USE `stardb_user`;")
        self.cursor.execute(f"INSERT INTO `{table}` SET discord_id = {discord_id}, {column} = {value} ON DUPLICATE KEY UPDATE `discord_id` = {discord_id}, `{column}` = CASE WHEN `{column}` IS NOT NULL THEN `{column}` + {value} ELSE {value} END;")
        self.connection.commit()

    def set_userdata_v2(self, discord_id:int, column:str, value, table="user_discord"):
        """設定用戶資料"""
        self.cursor.execute(f"INSERT INTO `stardb_user`.`{table}` SET discord_id = {discord_id}, {column} = {value} ON DUPLICATE KEY UPDATE discord_id = {discord_id}, {column} = {value};")
        self.connection.commit()
class MySQLBetSystem(MySQLBaseModel):
    def get_bet_data(self,bet_id:int):
        self.cursor.execute(f"USE `database`;")
        self.cursor.execute(f'SELECT `bet_id`,`IsOn` FROM `bet_data` WHERE `bet_id` = %s;',(bet_id,))
        records = self.cursor.fetchone()
        return records

    def place_bet(self,bet_id:int,choice:str,money:int):
        self.cursor.execute(f"USE `stardb_user`;")
        self.cursor.execute(f'INSERT INTO `user_bet` VALUES(%s,%s,%s);',(bet_id,choice,money))
        self.connection.commit()

    def create_bet(self,bet_id:int,title:str,pink:str,blue:str):
        self.cursor.execute(f"USE `database`;")
        self.cursor.execute(f'INSERT INTO `bet_data` VALUES(%s,%s,%s,%s,%s);',(bet_id,title,pink,blue,True))
        self.connection.commit()

    def update_bet(self,bet_id:int):
        self.cursor.execute(f"USE `database`;")
        self.cursor.execute(f"UPDATE `bet_data` SET IsOn = %s WHERE bet_id = %s;",(False,bet_id))
        self.connection.commit()

    def get_bet_total(self,bet_id:int):
        self.cursor.execute(f"USE `stardb_user`;")
        self.cursor.execute(f'SELECT SUM(money) FROM `user_bet` WHERE `bet_id` = %s AND `choice` = %s;',(bet_id,'pink'))
        total_pink = self.cursor.fetchone()
        self.cursor.execute(f'SELECT SUM(money) FROM `user_bet` WHERE `bet_id` = %s AND `choice` = %s;',(bet_id,'blue'))
        total_blue = self.cursor.fetchone()
        return [int(total_pink['SUM(money)'] or 0),int(total_blue['SUM(money)'] or 0)]

    def get_bet_winner(self,bet_id:int,winner:str):
        self.cursor.execute(f"USE `stardb_user`;")
        self.cursor.execute(f'SELECT * FROM `user_bet` WHERE `bet_id` = %s AND `choice` = %s;',(bet_id,winner))
        records = self.cursor.fetchall()
        return records

    def remove_bet(self,bet_id:int):
        self.cursor.execute(f'DELETE FROM `stardb_user`.`user_bet` WHERE `bet_id` = %s;',(bet_id,))
        self.cursor.execute(f'DELETE FROM `database`.`bet_data` WHERE `bet_id` = %s;',(bet_id,))
        self.connection.commit()

class MYSQLElectionSystem(MySQLBaseModel):
    def add_election(self,discord_id:int,session:int,position,represent_party_id:int=None):
        position = Position(position)
        self.cursor.execute(f"INSERT INTO `database`.`candidate_list` VALUES(%s,%s,%s,%s);",(discord_id,session,position.value,represent_party_id))
        self.connection.commit()

    def remove_election(self,discord_id:int,session:int,position=None):
        if position:
            position = Position(position)
            self.cursor.execute(f"DELETE FROM `database`.`candidate_list` WHERE `discord_id` = %s AND `session` = %s AND `position` = %s;",(discord_id,session,position.value))
        else:
            self.cursor.execute(f"DELETE FROM `database`.`candidate_list` WHERE `discord_id` = %s AND `session` = %s;",(discord_id,session))
        self.connection.commit()

    def get_election_by_session(self,session:int):
        self.cursor.execute(f"SELECT * FROM `database`.`candidate_list` WHERE session = {session};")
        records = self.cursor.fetchall()
        return records
    
    def get_election_full_by_session(self,session:int):
        self.cursor.execute(f"""
            SELECT 
                cl.discord_id,
                cl.session,
                cl.position,
                COALESCE(cl.represent_party_id, up.party_id) AS party_id,
                pd.party_name,
                pd.role_id
            FROM
                `database`.`candidate_list` cl
                    LEFT JOIN
                `stardb_user`.`user_party` up ON cl.discord_id = up.discord_id
                    LEFT JOIN
                `database`.`party_data` pd ON COALESCE(cl.represent_party_id, up.party_id) = pd.party_id
            WHERE
                session = {session};
        """)
        return self.cursor.fetchall()

    def get_election_by_session_position(self,session:int,position=str):
        position = Position(position)
        self.cursor.execute(f"SELECT * FROM `database`.`candidate_list` WHERE session = {session} AND position = {position.value};")
        records = self.cursor.fetchall()
        return records
    
    def get_election_count(self,session:int):
        self.cursor.execute(f"SELECT position,count(*) AS count FROM `database`.`candidate_list` WHERE session = {session} GROUP BY position ORDER BY `position`;")
        records = self.cursor.fetchall()
        return records
    
    def add_official(self, discord_id, session, position):
        self.cursor.execute(f"INSERT INTO `database`.`official_list` VALUES(%s,%s,%s);",(discord_id,session,position))
        self.connection.commit()

    def add_officials(self, lst:list[list[int, int, int]]):
        self.cursor.executemany(f"INSERT INTO `database`.`official_list` VALUES(%s,%s,%s);",lst)
        self.connection.commit()

    def join_party(self,discord_id:int,party_id:int):
        self.cursor.execute(f"INSERT INTO `stardb_user`.`user_party` VALUES(%s,%s);",(discord_id,party_id))
        self.connection.commit()

    def leave_party(self,discord_id:int,party_id:int):
        self.cursor.execute(f"DELETE FROM `stardb_user`.`user_party` WHERE `discord_id` = %s AND `party_id` = %s;",(discord_id,party_id))
        self.connection.commit()

    def get_all_party_data(self):
        self.cursor.execute(f"""
            SELECT 
                `party_data`.*, COUNT(`user_party`.party_id) AS member_count
            FROM
                `database`.`party_data`
                    LEFT JOIN
                `stardb_user`.`user_party` ON party_data.party_id = user_party.party_id
            GROUP BY `party_id`
            ORDER BY `party_id`;
        """)
        records = self.cursor.fetchall()
        return [Party(**i) for i in records]
    
    def get_user_party(self,discord_id:int):
        self.cursor.execute(f"SELECT `user_party`.discord_id,`party_data`.* FROM `stardb_user`.`user_party` LEFT JOIN `database`.`party_data` ON user_party.party_id = party_data.party_id WHERE `discord_id` = {discord_id}")
        records = self.cursor.fetchall()
        return [Party(**i) for i in records]
    
    def get_party_data(self,party_id:int):
        self.cursor.execute(f"SELECT * FROM `database`.`party_data` WHERE `party_id` = {party_id};")
        records = self.cursor.fetchall()
        if records:
            return Party(**records[0])

class MySQLManager(MySQLBaseModel):
    def copy_data(self, remote_schema, remote_table, local_schema, local_table):
        remote = MySQLBaseModel(Jsondb.config["remote_SQLsettings"])
        remote.cursor.execute(f"SELECT * FROM `{remote_schema}`.`{remote_table}`;")
        records = remote.cursor.fetchall()

        col_count = len(records[0])
        values_str = ",".join(["%s" for _ in range(col_count)])
        try:
            self.cursor.executemany(f'INSERT INTO `{local_schema}`.`{local_table}` VALUES({values_str});', [tuple(r.values()) for r in records])
            self.connection.commit()
        except sqlerror as e:
            if e.errno == 1062:
                print(e.msg)
            else:
                raise e

class MySQLDatabase(
    MySQLBetSystem,
    MYSQLElectionSystem,
    MySQLManager,
):
    """Mysql操作"""

class SQLEngine(
    SQLUserSystem,
    SQLCurrencySystem,
    SQLGameSystem,
    SQLPetSystem,
    SQLNotifySystem,
    SQLRoleSaveSystem,
    SQLWarningSystem,
    SQLPollSystem,
    SQLElectionSystem,
    SQLTwitchSystem,
    SQLRPGSystem,
    SQLTRPGSystem,
    SQLBackupSystem,
    SQLTokensSystem,
    SQLTest,
    ):
    """SQL引擎"""

    dict_type = [NotifyChannelType.DynamicVoice, NotifyChannelType.VoiceLog]
    list_type = ["dynamic_voice_room"]

    def init_notify(self):
        for t in self.dict_type:
            self.update_notify_channel(t)

        for t in self.list_type:
            if t == "dynamic_voice_room":
                self.cache[t] = self.get_all_dynamic_voice()
    
        self.update_notify_community()
        log.debug("dbcache: notify init.")
    
    def __getitem__(self, key):
        return self.cache[key]
    
    def __delitem__(self, key):
        del self.cache[key]

    def __setitem__(self, key, value):
        self.cache[key] = value

    def update_notify_channel(self, notify_type:NotifyChannelType):
        """更新通知頻道"""
        if notify_type not in self.dict_type:
            raise KeyError(f"Not implemented notify type: {notify_type}")
        self.cache[notify_type] = self.get_notify_channel_dict(notify_type)

    def update_notify_community(self, notify_type:NotifyCommunityType=None):
        """更新社群通知"""
        if notify_type:
            if notify_type not in NotifyCommunityType:
                raise KeyError(f"Not implemented notify type: {notify_type}")
            self.cache[notify_type] = self.get_notify_community_rawlist(notify_type)
        else:
            for t in NotifyCommunityType:
                self.cache[t] = self.get_notify_community_rawlist(t)
    
    def update_dynamic_voice(self,add_channel=None,remove_channel=None):
        """更新動態語音頻道"""
        if add_channel and add_channel not in self.cache[NotifyChannelType.DynamicVoice]:
            self.cache[NotifyChannelType.DynamicVoice].append(add_channel)
        if remove_channel:
            self.cache[NotifyChannelType.DynamicVoice].remove(remove_channel)
    
    def getif_dynamic_voice_room(self,channel_id:int):
        """取得動態語音房間"""
        return channel_id if channel_id in self.cache["dynamic_voice_room"] else None