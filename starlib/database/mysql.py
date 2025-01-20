import json
from datetime import date, datetime, time, timedelta, timezone
from typing import Tuple, TypeVar

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

from ..errors import *
from ..fileDatabase import Jsondb
from ..models.mysql import *
from ..models.rpg import *
from ..settings import tz
from ..types import *

SQLsettings = Jsondb.config["SQLsettings"]

O = TypeVar("O")

# type: ignore
connection_url = URL.create(
    drivername="mysql+mysqlconnector",
    username=SQLsettings["user"], 
    password=SQLsettings["password"],
    host=SQLsettings["host"],
    port=SQLsettings["port"]
)

class BaseSQLEngine:
    def __init__(self,connection_url):
        self.engine = create_engine(connection_url, echo=False, pool_pre_ping=True)
        # SessionLocal = sessionmaker(bind=self.engine)
        # self.session:Session = SessionLocal()
        SQLModel.metadata.create_all(self.engine)
        # SQLModel.metadata.drop_all(engine, schema="my_schema")

        # with Session(self.engine) as session:
        self.session = Session(bind=self.engine)
        
        self.alengine = sqlalchemy.create_engine(connection_url, echo=False)
        # Base.metadata.create_all(self.alengine)
        Sessionmkr = sessionmaker(bind=self.alengine)
        self.alsession = Sessionmkr()

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

    def remove(self, db_obj):
        self.session.delete(db_obj)
        self.session.commit()

    def expire(self, db_obj):
        #self.session.expunge(db_obj)
        self.session.expire(db_obj)

    def get(self, db_obj:O, primary_keys:tuple) -> O | None:
        return self.session.get(db_obj, primary_keys)


    def get_student(self, student_id:int):
        stmt = select(Student).where(Student.id == student_id)
        result = self.session.exec(stmt).one_or_none()
        return result
    
    def get_school(self, school_id:int):
        stmt = select(School).where(School.id == school_id)
        result = self.session.exec(stmt).one_or_none()
        return result
    
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
    def add_notify_channel(self,guild_id:int,notify_type:NotifyChannelType,channel_id:int,role_id:int=None):
        """設定自動通知頻道"""
        channel = NotifyChannel(guild_id=guild_id, notify_type=notify_type, channel_id=channel_id, role_id=role_id)
        self.session.merge(channel)
        self.session.commit()

    def remove_notify_channel(self,guild_id:int,notify_type:NotifyChannelType):
        """移除自動通知頻道"""
        stmt = delete(NotifyChannel).where(
            NotifyChannel.guild_id == guild_id,
            NotifyChannel.notify_type == notify_type
        )
        self.session.exec(stmt)
        self.session.commit()
    
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
    
    def add_dynamic_voice(self, channel_id, discord_id, guild_id, created_at=None):
        """設定動態語音"""
        voice = DynamicChannel(channel_id=channel_id, discord_id=discord_id, guild_id=guild_id, created_at=created_at)
        self.session.add(voice)
        self.session.commit()

    def remove_dynamic_voice(self,channel_id):
        """移除動態語音"""
        stmt = delete(DynamicChannel).where(DynamicChannel.channel_id == channel_id)
        self.session.exec(stmt)
        self.session.commit()

    #* notify community
    def add_notify_community(self, notify_type:NotifyCommunityType, community_id:str, community_type:CommunityType, guild_id:int, channel_id:int, role_id:int=None, message:str=None):
        """設定社群通知"""
        community = NotifyCommunity(notify_type=notify_type, community_id=community_id, community_type=community_type, guild_id=guild_id, channel_id=channel_id, role_id=role_id, message=message)
        self.session.merge(community)
        self.session.commit()

    def remove_notify_community(self,notify_type:NotifyCommunityType, community_id:str, guild_id:int, community_type:CommunityType=None):
        """移除社群通知，若提供community_type則同時判斷移除社群"""
        # TODO: 在type建表取代 community_type
        statement = delete(NotifyCommunity).where(
            NotifyCommunity.notify_type == notify_type,
            or_(
                NotifyCommunity.community_id == community_id,
                NotifyCommunity.display_name == community_id
            ),
            NotifyCommunity.guild_id == guild_id
        )
        self.session.exec(statement)
        self.session.commit()
        if community_type is not None:
            self.remove_community(community_type, community_id)

    def get_notify_community(self, notify_type:NotifyCommunityType):
        """取得社群通知（依據社群）"""
        statement = select(NotifyCommunity).where(NotifyCommunity.notify_type == notify_type)
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
    def add_poll(self,title:str,created_user:int,created_at:datetime,message_id,guild_id,ban_alternate_account_voting=False,show_name=False,check_results_in_advance=True,results_only_initiator=False,number_of_user_votes=1):
        poll = Poll(title=title,created_user=created_user,created_at=created_at,is_on=True,message_id=message_id,guild_id=guild_id,ban_alternate_account_voting=ban_alternate_account_voting,show_name=show_name,check_results_in_advance=check_results_in_advance,results_only_initiator=results_only_initiator,number_of_user_votes=number_of_user_votes)
        self.session.add(poll)
        self.session.commit()
        return poll.poll_id
    
    def remove_poll(self,poll_id:int):
        self.session.exec(delete(Poll).where(Poll.poll_id == poll_id))
        self.session.exec(delete(UserPoll).where(Poll.poll_id == poll_id))
        self.session.exec(delete(PollOption).where(Poll.poll_id == poll_id))
        self.session.commit()

    def get_poll(self,poll_id:int):
        stmt = select(Poll).where(Poll.poll_id == poll_id)
        result = self.session.exec(stmt).one_or_none()
        return result
    
    def update_poll(self,poll:Poll):
        self.session.merge(poll)
        self.session.commit()

    def get_all_active_polls(self):
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
    
    def add_poll_role(self,poll_id:int,role_id:int,role_type:int,role_magnification:int=1):
        """role_type 1:只有此身分組可投票 2:倍率 """
        pollrole = PollRole(poll_id=poll_id,role_id=role_id,role_type=role_type,role_magnification=role_magnification)
        self.session.merge(pollrole)
        self.session.commit()
    
    def get_poll_role(self,poll_id:int,role_type:int=None):
        if role_type:
            stmt = select(PollRole).where(PollRole.poll_id == poll_id, PollRole.role_type == role_type)
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
    def get_test(self):
        result = self.alsession.query(Student).all()
        return result

    def add_test(self, student:Student):
        self.alsession.add(Student)
        self.alsession.commit()
        self.alsession.merge()

    def remove_test(self, student_id:int):
        stmt = delete(Student).where(Student.id == student_id)
        self.alsession.execute(stmt)
        self.alsession.commit()

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
    
    # def add_data(self,table:str,*value,db="database"):
    #     self.cursor.execute(f"USE `{db}`;")
    #     self.cursor.execute(f"INSERT INTO `{table}` VALUES(%s)",value)
    #     self.connection.commit()

    # def replace_data(self,table:str,*value,db="database"):
    #     self.cursor.execute(f"USE `{db}`;")
    #     self.cursor.execute(f"REPLACE INTO `{table}` VALUES(%s)",value)
    #     self.connection.commit()

    # def get_data(self,table:str):
    #     db = "database"
    #     self.cursor.execute(f"USE `{db}`;")
    #     self.cursor.execute(f'SELECT * FROM `{table}` WHERE id = %s;',("1",))
        
    #     records = self.cursor.fetchall()
    #     for r in records:
    #          print(r)
    
    # def remove_data(self,table:str,*value):
    #     db = "database"
    #     self.cursor.execute(f"USE `{db}`;")
    #     #self.cursor.execute(f'DELETE FROM `{table}` WHERE `id` = %s;',("3",))
    #     self.cursor.execute(f'DELETE FROM `{table}` WHERE `id` = %s;',value)
    #     self.connection.commit()
    
class MySQLHoYoLabSystem(MySQLBaseModel):
    def set_hoyo_cookies(self,discord_id:int,cookies:dict):
        cookies = json.dumps(cookies)
        self.cursor.execute(f"USE `database`;")
        self.cursor.execute(f"INSERT INTO `game_hoyo_cookies` VALUES(%s,%s) ON DUPLICATE KEY UPDATE `discord_id` = %s, `hoyolab_cookies` = %s;",(discord_id,cookies,discord_id,cookies))
        self.connection.commit()

    def remove_hoyo_cookies(self,discord_id:int):
        self.cursor.execute(f"USE `database`;")
        self.cursor.execute(f"DELETE FROM `game_hoyo_cookies` WHERE discord_id = {discord_id}")
        self.connection.commit()

    def get_hoyo_reward(self):
        self.cursor.execute(f"USE `database`;")
        #self.cursor.execute(f'SELECT * FROM `game_hoyo_reward` LEFT JOIN `game_hoyo_cookies` ON game_hoyo_reward.discord_id = game_hoyo_cookies.discord_id WHERE game_hoyo_reward.discord_id IS NOT NULL;')
        self.cursor.execute(f'SELECT * FROM `game_hoyo_reward`;')
        records = self.cursor.fetchall()
        return records
    
    def add_hoyo_reward(self,discord_id:int,game:str,channel_id:str,need_mention:bool):
        self.cursor.execute(f"USE `database`;")
        self.cursor.execute(f"INSERT INTO `game_hoyo_reward` VALUES(%s,%s,%s,%s) ON DUPLICATE KEY UPDATE `channel_id` = {channel_id}, `need_mention` = {need_mention}",(discord_id,game,channel_id,need_mention))
        self.connection.commit()

    def remove_hoyo_reward(self,discord_id:int):
        self.cursor.execute(f"USE `database`;")
        self.cursor.execute(f"DELETE FROM `game_hoyo_reward` WHERE discord_id = {discord_id}")
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

class MySQLRPGSystem(MySQLBaseModel):
    
    def get_rpguser(self,discord_id:int,full=False,user_dc:discord.User=None,):
        """取得RPG用戶
        :param full: 是否合併其他表取得完整資料
        """
        self.cursor.execute(f"USE `stardb_user`;")
        if full:
            #self.cursor.execute(f'SELECT * FROM `rpg_user` LEFT JOIN `user_point`ON `rpg_user`.discord_id = `user_point`.discord_id WHERE rpg_user.discord_id = %s;',(discord_id,))
            self.cursor.execute(f'SELECT * FROM `rpg_user` LEFT JOIN `user_point` ON `rpg_user`.discord_id = `user_point`.discord_id LEFT JOIN `stardb_idbase`.`rpg_career` ON `rpg_user`.career_id = `rpg_career`.career_id WHERE rpg_user.discord_id = %s;',(discord_id,))
        else:
            self.cursor.execute(f'SELECT * FROM `rpg_user` LEFT JOIN `user_point` ON `rpg_user`.discord_id = `user_point`.discord_id WHERE rpg_user.discord_id = %s;',(discord_id,))
            
        records = self.cursor.fetchall()
        if records:
            return RPGUser(records[0],self,user_dc=user_dc)
        else:
            self.cursor.execute(f'INSERT INTO `rpg_user` SET `discord_id` = %s;',(discord_id,))
            self.connection.commit()
            self.cursor.execute(f'SELECT * FROM `rpg_user` LEFT JOIN `user_point`ON `rpg_user`.discord_id = `user_point`.discord_id WHERE rpg_user.discord_id = %s;',(discord_id,))
            return RPGUser(self.cursor.fetchall()[0],self,user_dc=user_dc)

    def get_monster(self,monster_id:str):
        """取得怪物"""
        self.cursor.execute(f'SELECT * FROM `stardb_idbase`.`rpg_monster` WHERE `monster_id` = %s;',(monster_id,))
        records = self.cursor.fetchall()
        if records:
            return Monster(records[0])
        else:
            raise ValueError('monster_id not found.')
        
    def get_monster_loot(self,monster_id:str):
        self.cursor.execute(f'SELECT * FROM `stardb_idbase`.`rpg_monster_loot_equipment` LEFT JOIN `stardb_idbase`.`rpg_equipment` ON `rpg_monster_loot_equipment`.equipment_id = `rpg_equipment`.equipment_id WHERE `monster_id` = %s;',(monster_id,))
        records = self.cursor.fetchall()
        if records:
            return MonsterLootList(records)

    def set_rpguser(self,discord_id:int):
        self.cursor.execute(f"USE `stardb_user`;")
        self.cursor.execute(f"INSERT INTO `rpg_user` VALUES(%s);",(discord_id,))
        self.connection.commit()
    
    def update_rpguser_attribute(self,discord_id:int,maxhp=0,atk=0,df=0,hrt=0,dex=0):
        self.cursor.execute(f'UPDATE `stardb_user`.`rpg_user` SET `user_hp` = CASE WHEN `user_maxhp` + {maxhp} < `user_hp` THEN `user_maxhp` ELSE `user_hp` END, `user_maxhp` = `user_maxhp` + {maxhp}, `user_atk` = `user_atk` + {atk}, `user_def` = `user_def` + {df}, `user_hrt` = `user_hrt` + {hrt}, `user_dex` = `user_dex` + {dex} WHERE `discord_id` = {discord_id}')
        self.connection.commit()

    def get_activities(self,discord_id:int):
        records = self.get_userdata(discord_id,"rpg_activities")
        return records or {}

    def get_bag(self,discord_id:int,item_uid:int=None,with_name=False):
        self.cursor.execute(f"USE `stardb_user`;")
        if with_name:
            self.cursor.execute(f"SELECT `rpg_user_bag`.item_uid,item_name,amount,item_category_id,item_id FROM `stardb_user`.`rpg_user_bag` LEFT JOIN `stardb_idbase`.`rpg_item` ON `rpg_user_bag`.item_uid = `rpg_item`.item_uid WHERE discord_id = {discord_id};")
        elif item_uid:
            self.cursor.execute(f"SELECT * FROM `rpg_user_bag` WHERE discord_id = {discord_id} AND item_uid = {item_uid};")
        else:
            self.cursor.execute(f"SELECT item_uid,amount FROM `rpg_user_bag` WHERE discord_id = {discord_id};")
        records = self.cursor.fetchall()
        return records or []
    
    def get_bag_desplay(self,discord_id:int):
        self.cursor.execute(f"SELECT * FROM `stardb_user`.`rpg_user_bag` LEFT JOIN `stardb_idbase`.`rpg_item` ON `rpg_user_bag`.item_uid = `rpg_item`.item_uid WHERE discord_id = {discord_id};")
        #self.cursor.execute(f"SELECT rpg_item.item_id,name,amount FROM `database`.`rpg_user_bag`,`stardb_idbase`.`rpg_item` WHERE discord_id = {discord_id};")
        records = self.cursor.fetchall()
        return records

    def update_bag(self,discord_id:int,item_uid:int,amount:int):
        self.cursor.execute(f"INSERT INTO `stardb_user`.`rpg_user_bag` SET discord_id = {discord_id}, item_uid = {item_uid}, amount = {amount} ON DUPLICATE KEY UPDATE amount = amount + {amount};")
        self.connection.commit()

    def remove_bag(self,discord_id:int,item_uid:int,amount:int):
        r = self.get_bag(discord_id,item_uid)
        if r[0]['amount'] < amount:
            raise ValueError('此物品數量不足')
        
        self.cursor.execute(f"USE `stardb_user`;")
        if r[0]['amount'] == amount:
            self.cursor.execute(f"DELETE FROM `rpg_user_bag` WHERE `discord_id` = %s AND `item_uid` = %s;",(discord_id,item_uid))
        else:
            self.cursor.execute(f'UPDATE `rpg_user_bag` SET amount = amount - {amount} WHERE `discord_id` = {discord_id} AND `item_uid` = {item_uid}')
        self.connection.commit()

    def get_work(self,discord_id:int):
        self.cursor.execute(f"USE `stardb_user`;")
        #self.cursor.execute(f"SELECT * FROM `rpg_user` LEFT JOIN `stardb_idbase`.`rpg_career` ON `rpg_user`.career_id = `rpg_career`.career_id LEFT JOIN `stardb_idbase`.`rpg_item` ON `rpg_career`.reward_item_id = `rpg_item`.item_id WHERE `discord_id` = {discord_id} AND `last_work` > NOW() - INTERVAL 12 HOUR;")
        self.cursor.execute(f"SELECT * FROM `rpg_user` LEFT JOIN `stardb_idbase`.`rpg_career` ON `rpg_user`.career_id = `rpg_career`.career_id LEFT JOIN `stardb_idbase`.`rpg_item` ON `rpg_career`.reward_item_uid = `rpg_item`.item_uid WHERE `discord_id` = {discord_id};")
        records = self.cursor.fetchall()
        if records:
            return records[0]
    
    def refresh_work(self,discord_id:int):
        self.cursor.execute(f'UPDATE `rpg_user` SET `last_work` = NOW() WHERE `discord_id` = {discord_id};')
        self.connection.commit()

    def set_rpguser_data(self,discord_id:int,column:str,value):
        """設定或更新RPG用戶資料"""
        self.cursor.execute(f"USE `stardb_user`;")
        self.cursor.execute(f"INSERT INTO `rpg_user` SET discord_id = {discord_id}, {column} = {value} ON DUPLICATE KEY UPDATE discord_id = {discord_id}, {column} = {value};")
        self.connection.commit()

    def get_rpg_shop_list(self):
        self.cursor.execute(f"USE `database`;")
        self.cursor.execute(f"SELECT * FROM `rpg_shop` LEFT JOIN `stardb_idbase`.`rpg_item` ON `rpg_shop`.item_uid = `rpg_item`.item_uid;")
        records = self.cursor.fetchall()
        return records
    
    def get_rpg_shop_item(self,shop_item_id:int):
        self.cursor.execute(f"SELECT * FROM `database`.`rpg_shop` LEFT JOIN `stardb_idbase`.`rpg_item` ON `rpg_shop`.item_uid = `rpg_item`.item_uid WHERE `shop_item_id` = {shop_item_id};")
        record = self.cursor.fetchall()
        if record:
            return ShopItem(record[0])
        
    def update_rpg_shop_inventory(self,shop_item_id:int,item_inventory_add:int):
        self.cursor.execute(f"UPDATE `database`.`rpg_shop` SET `item_inventory` = item_inventory + {item_inventory_add} WHERE `shop_item_id` = {shop_item_id};")
        self.cursor.execute(f"UPDATE `database`.`rpg_shop` SET `item_price` = item_inital_price * pow(0.97,item_inventory - item_inital_inventory) WHERE `shop_item_id` = {shop_item_id};")
        self.connection.commit()

    def rpg_shop_daily(self):
        self.cursor.execute(f"UPDATE `database`.`rpg_shop` SET `item_inventory` = item_inventory - item_inital_inventory * (item_inventory / item_inital_inventory * FLOOR(RAND()*76+25) / 100 ) WHERE `item_mode` = 1;")
        self.cursor.execute(f"UPDATE `database`.`rpg_shop` SET `item_inventory` = item_inital_inventory WHERE item_inventory <= item_inital_inventory AND `item_mode` = 1;")
        self.cursor.execute(f"UPDATE `database`.`rpg_shop` SET `item_price` =  item_inital_price * pow(0.97,item_inventory - item_inital_inventory) WHERE `item_mode` = 1;")
        self.connection.commit()
        
    def get_rpgequipment_ingame(self,equipment_uid):
        self.cursor.execute(f"SELECT * FROM database.rpg_equipment_ingame LEFT JOIN `stardb_idbase`.`rpg_equipment` ON `rpg_equipment_ingame`.equipment_id = `rpg_equipment`.equipment_id LEFT JOIN `stardb_idbase`.`rpg_item` ON `rpg_equipment`.item_id = `rpg_item`.item_id WHERE `equipment_uid` = {equipment_uid};")
        record = self.cursor.fetchall()
        if record:
            return RPGEquipment(record[0])
        
    def add_equipment_ingame(self, equipment_id, equipment_customized_name=None, equipment_maxhp=None, equipment_atk=None, equipment_def=None, equipment_hrt=None, equipment_dex=None):
        self.cursor.execute(f"INSERT INTO `database`.`rpg_equipment_ingame` VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);",(None,equipment_id,equipment_customized_name,None,None,equipment_maxhp,equipment_atk,equipment_def,equipment_hrt,equipment_dex))
        self.connection.commit()
        return self.cursor.lastrowid

    def get_rpgplayer_equipment(self,discord_id,equipment_uid=None,equipment_id=None,slot_id=None):
        """查詢現有裝備\n
        以下三者則一提供，都不提供則查詢玩家所有裝備
        :param equipment_uid: 查詢玩家是否擁有指定裝備
        :param equipment_id: 查詢玩家同類型裝備，同時傳入slot_id=0則查詢玩家未穿戴同類型裝備
        :param slot_id: 查詢玩家所有穿戴或未穿戴裝備 -1:穿戴 0:未穿戴 其他:指定欄位穿戴
        """
        if equipment_uid:
            self.cursor.execute(f"SELECT * FROM `database`.`rpg_equipment_ingame` LEFT JOIN `stardb_idbase`.`rpg_equipment` ON `rpg_equipment_ingame`.equipment_id = `rpg_equipment`.equipment_id LEFT JOIN `stardb_idbase`.`rpg_item` ON `rpg_equipment`.item_id = `rpg_item`.item_id WHERE `equipment_uid` = {equipment_uid} AND `discord_id` = {discord_id};")
            record = self.cursor.fetchall()
            if record:
                return RPGEquipment(record[0])
        elif equipment_id:
            if slot_id == 0:
                WHERE = f"`rpg_equipment_ingame`.equipment_id = {equipment_id} AND `discord_id` = {discord_id} AND `slot_id` IS NULL"
            else:
                WHERE = f"`rpg_equipment_ingame`.equipment_id = {equipment_id} AND `discord_id` = {discord_id}"
            self.cursor.execute(f"SELECT * FROM `database`.`rpg_equipment_ingame` LEFT JOIN `stardb_idbase`.`rpg_equipment` ON `rpg_equipment_ingame`.equipment_id = `rpg_equipment`.equipment_id LEFT JOIN `stardb_idbase`.`rpg_item` ON `rpg_equipment`.item_id = `rpg_item`.item_id WHERE {WHERE};")
            record = self.cursor.fetchall()
            if record:
                return [ RPGEquipment(i) for i in record ] 
            
        elif slot_id is not None:
            if slot_id == -1:
                WHERE = f"`discord_id` = {discord_id} AND `slot_id` IS NOT NULL"
            elif slot_id == 0:
                WHERE = f"`discord_id` = {discord_id} AND `slot_id` IS NULL"
            else:
                WHERE = f"`discord_id` = {discord_id} AND `slot_id` = {slot_id}"
            self.cursor.execute(f"SELECT * FROM `database`.`rpg_equipment_ingame` LEFT JOIN `stardb_idbase`.`rpg_equipment` ON `rpg_equipment_ingame`.equipment_id = `rpg_equipment`.equipment_id LEFT JOIN `stardb_idbase`.`rpg_item` ON `rpg_equipment`.item_id = `rpg_item`.item_id WHERE {WHERE};")
            record = self.cursor.fetchall()
            if record:
                return [ RPGEquipment(i) for i in record ]

        else:
            self.cursor.execute(f"SELECT * FROM `database`.`rpg_equipment_ingame` LEFT JOIN `stardb_idbase`.`rpg_equipment` ON `rpg_equipment_ingame`.equipment_id = `rpg_equipment`.equipment_id LEFT JOIN `stardb_idbase`.`rpg_item` ON `rpg_equipment`.item_id = `rpg_item`.item_id WHERE `discord_id` = {discord_id} AND `item_category_id` = 2;")
            record = self.cursor.fetchall()
            if record:
                return [ RPGEquipment(i) for i in record ]
            else:
                return []

    def set_rpgplayer_equipment(self,discord_id,equipment_uid):
        self.cursor.execute(f"UPDATE `database`.`rpg_equipment_ingame` SET `discord_id` = %s WHERE `equipment_uid` = %s;",(discord_id,equipment_uid))
        self.connection.commit()
    
    def remove_rpgplayer_equipment(self,discord_id,equipment_uid):
        self.cursor.execute(f"DELETE FROM `database`.`rpg_equipment_ingame` WHERE `discord_id` = %s AND `equipment_uid` = %s;",(discord_id,equipment_uid))
        self.connection.commit()

    def update_rpgplayer_equipment(self,equipment_uid,colum,value):
        self.cursor.execute(f"UPDATE `database`.`rpg_equipment_ingame` SET `{colum}` = {value} WHERE `equipment_uid` = {equipment_uid};")
        self.connection.commit()

    def sell_rpgplayer_equipment(self,discord_id,equipment_uid=None,equipment_id=None):
        """售出裝備
        :param equipment_uid: 售出指定裝備
        :param equipment_id: 售出同類型裝備，並回傳總價格與裝備uid列表
        """
        if equipment_uid:
            self.cursor.execute(f"DELETE FROM `database`.`rpg_equipment_ingame` WHERE `discord_id` = %s AND `equipment_uid` = %s AND `equipment_inmarket` != 1;",(discord_id,equipment_uid))
            self.connection.commit()
        elif equipment_id:
            self.cursor.execute(f"SELECT `equipment_uid` FROM `database`.`rpg_equipment_ingame` LEFT JOIN `stardb_idbase`.`rpg_equipment` ON `rpg_equipment_ingame`.equipment_id = `rpg_equipment`.equipment_id WHERE `rpg_equipment_ingame`.`equipment_id` = {equipment_id} AND `discord_id` = {discord_id} AND `slot_id` IS NULL AND `equipment_inmarket` != 1;")
            equipment_uids = [row["equipment_uid"] for row in self.cursor.fetchall()]
            price = 0
            if equipment_uids:
                self.cursor.execute(f"SELECT SUM(`rpg_equipment`.equipment_price) as price FROM `database`.`rpg_equipment_ingame` LEFT JOIN `stardb_idbase`.`rpg_equipment` ON `rpg_equipment_ingame`.equipment_id = `rpg_equipment`.equipment_id WHERE `rpg_equipment_ingame`.`equipment_id` = {equipment_id} AND `discord_id` = {discord_id} AND `slot_id` IS NULL AND `equipment_inmarket` != 1;")
                record = self.cursor.fetchall() 
                price = record[0]["price"]
                
                uid_list = ','.join(map(str, equipment_uids))
                self.cursor.execute(f"DELETE FROM `database`.`rpg_equipment_ingame` WHERE `equipment_uid` IN ({uid_list});")
                #self.connection.commit()
                print(equipment_uids)
            
            return (price, equipment_uids)

    def update_rpgplayer_equipment_warning(self,discord_id,equipment_uid,slot_id=None):
        slot = EquipmentSolt(slot_id) if slot_id else None

        item = self.get_rpgplayer_equipment(discord_id,equipment_uid)
        if slot_id:
            #穿上裝備
            self.cursor.execute(f"UPDATE `database`.`rpg_equipment_ingame` SET `slot_id` = %s WHERE `equipment_uid` = %s AND `equipment_inmarket` != 1;",(slot.value,equipment_uid))
            self.update_rpguser_attribute(discord_id,item.maxhp,item.atk,item.df,item.hrt,item.dex)
        else:
            #脫掉裝備
            self.cursor.execute(f"UPDATE `database`.`rpg_equipment_ingame` SET `slot_id` = %s WHERE `equipment_uid` = %s AND `equipment_inmarket` != 1;",(None,equipment_uid))
            self.update_rpguser_attribute(discord_id,-item.maxhp,-item.atk,-item.df,-item.hrt,-item.dex)
        self.connection.commit()
        
    def get_item_market_item(self,discord_id,item_uid):
        self.cursor.execute(f"SELECT * FROM `database`.`rpg_item_market` AS rim LEFT JOIN `stardb_idbase`.`rpg_item` AS ri ON ri.item_uid = rim.item_uid WHERE `discord_id` = {discord_id} AND rim.`item_uid` = {item_uid};")
        record = self.cursor.fetchall()
        if record:
            return RPGMarketItem(record[0])
        
    def add_item_market_item(self,discord_id, item_uid, amount, per_price):
        self.cursor.execute(f"INSERT INTO `database`.`rpg_item_market` VALUES(%s,%s,%s,%s);",(discord_id,item_uid,amount,per_price))
        self.connection.commit()

    def update_item_market_item(self,discord_id, item_uid, amount):
        self.cursor.execute(f"UPDATE `database`.`rpg_item_market` SET `amount` = amount - {amount} WHERE `discord_id` = {discord_id} AND `item_uid` = {item_uid};")
        self.connection.commit()

    def remove_item_market_item(self,discord_id, item_uid):
        self.cursor.execute(f"DELETE FROM `database`.`rpg_item_market` WHERE `discord_id` = {discord_id} AND `item_uid` = {item_uid};")
        self.connection.commit()
    
    def get_item_market_list(self,discord_id):
        self.cursor.execute(f"SELECT * FROM `database`.`rpg_item_market` AS rim LEFT JOIN `stardb_idbase`.`rpg_item` AS ri ON rim.item_uid = ri.item_uid WHERE `discord_id` = {discord_id};")
        record = self.cursor.fetchall()
        if record:
            return [RPGMarketItem(i) for i in record]
        
    def get_city(self,city_id,with_introduce=False):
        self.cursor.execute(f"SELECT * FROM `stardb_idbase`.`rpg_cities` LEFT JOIN `database`.`rpg_cities_statue` ON `rpg_cities_statue`.city_id = `rpg_cities`.city_id WHERE `rpg_cities`.`city_id` = {city_id};")
        record = self.cursor.fetchall()
        if record:
            return RPGCity(record[0])
        
    def get_city_battle(self,city_id):
        self.cursor.execute(f"SELECT * FROM `database`.`rpg_city_battle` LEFT JOIN `stardb_idbase`.`rpg_cities` ON `rpg_city_battle`.city_id = `rpg_cities`.city_id WHERE `rpg_cities`.`city_id` = {city_id};")
        record = self.cursor.fetchall()
        # if record:
        #     return CityBattle(record,sqldb=self)
        
    def get_all_city_battle(self):
        self.cursor.execute(f"SELECT DISTINCT `rpg_cities`.`city_id` FROM `database`.`rpg_city_battle` LEFT JOIN `stardb_idbase`.`rpg_cities` ON `rpg_city_battle`.city_id = `rpg_cities`.city_id;")
        record = self.cursor.fetchall()
        if record:
            city_id_list = [i["city_id"] for i in record]
            city_battle_list = [self.get_city_battle(city_id) for city_id in city_id_list]
            return city_battle_list
        
        
    def add_city_battle(self,city_id,discord_id,in_city_statue):
        self.cursor.execute(f"INSERT INTO `database`.`rpg_city_battle` VALUES(%s,%s,%s) ON DUPLICATE KEY UPDATE `in_city_statue` = {in_city_statue};",(city_id,discord_id,in_city_statue))
        self.connection.commit()

    def remove_city_battle(self,city_id,discord_id):
        self.cursor.execute(f"DELETE FROM `database`.`rpg_city_battle` WHERE `city_id` = {city_id} AND `discord_id` = {discord_id};")
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
    MySQLHoYoLabSystem,
    MySQLBetSystem,
    MySQLRPGSystem,
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