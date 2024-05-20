from datetime import datetime,date,time,timedelta
from typing import Dict, List, Set, Tuple

import discord
import mysql.connector
from mysql.connector.errors import Error as sqlerror

from starcord.models.model import GameInfoPage
from starcord.types import DBGame, Coins, Position, CommunityType
from starcord.models.user import *
from starcord.models.model import *
from starcord.models.rpg import *
from starcord.errors import *

def create_id():
    return 'SELECT idNumber FROM ( SELECT CONCAT("U", LPAD(FLOOR(RAND()*10000000), 7, 0)) as idNumber) AS generated_ids WHERE NOT EXISTS ( SELECT 1 FROM stardb_user.user_data WHERE user_id = generated_ids.idNumber);'

class MySQLBaseModel(object):
    """MySQL資料庫基本模型"""
    def __init__(self,mysql_settings:dict):
        '''MySQL 資料庫連接\n
        settings = {"host": "","port": ,"user": "","password": "","db": "","charset": ""}
        '''
        
        #建立連線
        self.connection = mysql.connector.connect(**mysql_settings)
        self.cursor = self.connection.cursor(dictionary=True)
        self.connection.get_server_info()

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

class MySQLUserSystem(MySQLBaseModel):
    """用戶資料系統"""
    def create_user(self,discord_id:int=None):
        self.cursor.execute(f"USE `stardb_user`;")
        error = True

        while error:
            try:
                user_id = create_id()
                if discord_id:
                    operation = f"INSERT INTO `user_data` SET user_id = ({user_id}), discord_id = {discord_id};"
                else:
                    operation = f"INSERT INTO `user_data` SET user_id = ({user_id});"
                self.cursor.execute(operation)
                error = False
            except sqlerror as e:
                if e.errno == 1062:
                    pass
                else:
                    raise
        
        return self.get_user(user_id)
    
    def create_discord_user(self,discord_id:int):
        self.cursor.execute(f"USE `stardb_user`;")
        self.cursor.execute(f"INSERT INTO `user_data` SET discord_id = {discord_id};")
        self.cursor.execute(f"INSERT INTO `user_discord` SET discord_id = {discord_id};")
        self.cursor.execute(f"INSERT INTO `user_point` SET discord_id = {discord_id};")
        self.connection.commit()
        self.cursor.execute(f'SELECT * FROM `user_discord` WHERE `discord_id` = %s;',(discord_id,))
        record = self.cursor.fetchall()
        if record:
            return PartialUser(record[0])

    def get_user(self,user_id:str):
        """取得基本用戶"""
        self.cursor.execute(f'SELECT * FROM `user_data` WHERE `user_id` = %s;',(user_id,))
        record = self.cursor.fetchall()
        if record:
            return StarUser(record[0])

    def get_dcuser(self,discord_id:int,full=False,user_dc:discord.User=None):
        """取得discord用戶"""
        self.cursor.execute(f"USE `stardb_user`;")
        if full:
            self.cursor.execute(f'''
                                SELECT * FROM `user_discord`
                                LEFT JOIN `user_point` ON `user_discord`.`discord_id` = `user_point`.`discord_id`
                                LEFT JOIN `user_account` ON `user_discord`.`discord_id` = `user_account`.`alternate_account`
                                LEFT JOIN `stardb_idbase`.`discord_registrations` ON `user_discord`.`discord_registration` = `discord_registrations`.`registrations_id`
                                WHERE `user_discord`.`discord_id` = %s;
                                ''',(discord_id,))
        else:
            self.cursor.execute(f'SELECT * FROM `user_discord` WHERE `discord_id` = %s;',(discord_id,))
        record = self.cursor.fetchall()
        if record:
            return DiscordUser(record[0],self,user_dc)
    
    def get_partial_dcuser(self,discord_id:int,column:str):
        self.cursor.execute(f"USE `stardb_user`;")
        self.cursor.execute(f'SELECT `discord_id`,`{column}` FROM `user_discord` WHERE `discord_id` = %s;',(discord_id,))
        record = self.cursor.fetchall()
        if record:
            return PartialUser(record[0],self)
        else:
            return PartialUser(self.create_discord_user(discord_id),self)

    def get_main_account(self,alternate_account):
        self.cursor.execute(f"USE `stardb_user`;")
        self.cursor.execute(f'SELECT * FROM `user_account` WHERE `alternate_account` = %s;',(alternate_account,))
        record = self.cursor.fetchall()
        if record:
            return record[0]
        
    def get_alternate_account(self,discord_id):
        self.cursor.execute(f"USE `stardb_user`;")
        self.cursor.execute(f'SELECT * FROM `user_account` WHERE `main_account` = %s;',(discord_id,))
        return self.cursor.fetchall()
    
    def set_sharefolder_data(self,discord_id:int,emailAddress=None,drive_share_id=None):
        self.cursor.execute(f"USE `stardb_user`;")
        self.cursor.execute(f"INSERT INTO `user_data` SET `discord_id` = %s, `email` = %s, `drive_share_id` = %s ON DUPLICATE KEY UPDATE `email` = %s, `drive_share_id` = %s;",(discord_id,emailAddress,drive_share_id,emailAddress,drive_share_id))
        self.connection.commit()

    def remove_sharefolder_data(self,discord_id:int):
        self.cursor.execute(f"USE `stardb_user`;")
        self.cursor.execute(f"UPDATE `user_data` SET `email` = NULL, `drive_share_id` = NULL WHERE `discord_id` = %s;",(discord_id,))
        self.connection.commit()

class MySQLNotifySystem(MySQLBaseModel):
    def set_notify_channel(self,guild_id:int,notify_type:str,channel_id:int,role_id:int=None):
        """設定自動通知頻道"""
        self.cursor.execute(f"USE `database`;")
        self.cursor.execute(f"INSERT INTO `notify_channel` VALUES(%s,%s,%s,%s) ON DUPLICATE KEY UPDATE `guild_id` = %s, `notify_type` = %s, `channel_id` = %s, `role_id` = %s",(guild_id,notify_type,channel_id,role_id,guild_id,notify_type,channel_id,role_id))
        self.connection.commit()

    def remove_notify_channel(self,guild_id:int,notify_type:str):
        """移除自動通知頻道"""
        self.cursor.execute(f"USE `database`;")
        self.cursor.execute(f'DELETE FROM `notify_channel` WHERE `guild_id` = %s AND `notify_type` = %s;',(guild_id,notify_type))
        self.connection.commit()

    def get_notify_channel_by_type(self,notify_type:str):
        """取得自動通知頻道（依據通知種類）"""
        self.cursor.execute(f"USE `database`;")
        self.cursor.execute(f'SELECT * FROM `notify_channel` WHERE notify_type = %s;',(notify_type,))
        return self.cursor.fetchall()

    def get_notify_channel(self,guild_id:str,notify_type:str):
        """取得自動通知頻道"""
        self.cursor.execute(f"USE `database`;")
        self.cursor.execute(f'SELECT * FROM `notify_channel` WHERE guild_id = %s AND notify_type = %s;',(guild_id,notify_type))
        records = self.cursor.fetchall()
        if records:
            return records[0]
    
    def get_all_notify_channel(self,guild_id:str):
        """取得伺服器的所有自動通知頻道"""
        self.cursor.execute(f"USE `database`;")
        self.cursor.execute(f'SELECT * FROM `notify_channel` WHERE guild_id = %s;',(guild_id,))
        return self.cursor.fetchall()
    
    def set_dynamic_voice(self,channel_id,discord_id,guild_id,created_at=None):
        """設定動態語音"""
        self.cursor.execute(f"USE `database`;")
        self.cursor.execute(f"INSERT INTO `dynamic_channel` VALUES(%s,%s,%s,%s)",(channel_id,discord_id,guild_id,created_at))
        self.connection.commit()

    def remove_dynamic_voice(self,channel_id):
        """移除動態語音"""
        self.cursor.execute(f"USE `database`;")
        self.cursor.execute(f"DELETE FROM `dynamic_channel` WHERE `channel_id` = %s",(channel_id,))
        self.connection.commit()

    def get_all_dynamic_voice(self):
        """取得目前所有的動態語音"""
        self.cursor.execute(f"USE `database`;")
        self.cursor.execute(f'SELECT `channel_id` FROM `dynamic_channel`;')
        records = self.cursor.fetchall()
        list = []
        for data in records:
            list.append(data['channel_id'])
        return list

    def set_notify_community(self,notify_type:str,notify_name:str,guild_id:int,channel_id:int,role_id:int=None,display_name:str=None):
        """設定社群通知"""
        self.cursor.execute(f"USE `database`;")
        self.cursor.execute(f"INSERT INTO `notify_community` VALUES(%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE `notify_type` = %s, `notify_name` = %s, `guild_id` = %s, `channel_id` = %s, `role_id` = %s, `display_name` = %s",(notify_type,notify_name,display_name,guild_id,channel_id,role_id,notify_type,notify_name,guild_id,channel_id,role_id,display_name))
        self.connection.commit()

    def remove_notify_community(self,notify_type:str,notify_name:str,guild_id:int):
        """移除社群通知"""
        self.cursor.execute(f"USE `database`;")
        self.cursor.execute(f'DELETE FROM `notify_community` WHERE `notify_type` = %s AND `notify_name` = %s AND `guild_id` = %s;',(notify_type,notify_name,guild_id))
        self.connection.commit()

    def get_notify_community(self,notify_type:str):
        """取得社群通知（依據社群）"""
        self.cursor.execute(f"USE `database`;")
        self.cursor.execute(f'SELECT * FROM `notify_community` WHERE `notify_type` = %s;',(notify_type,))
        return self.cursor.fetchall()
    
    def get_notify_community_guild(self,notify_type:str,notify_name:str) -> dict[str, list[int]]:
        """取得指定社群的所有通知"""
        self.cursor.execute(f"USE `database`;")
        self.cursor.execute(f'SELECT `guild_id`,`channel_id`,`role_id` FROM `notify_community` WHERE `notify_type` = %s AND `notify_name` = %s;',(notify_type,notify_name))
        records = self.cursor.fetchall()
        dict = {}
        for i in records:
            dict[i['guild_id']] = [i['channel_id'],i['role_id']]
        return dict

    def get_notify_community_user(self,notify_type:str,notify_name:str,guild_id:int):
        """取得伺服器內的指定社群通知"""
        self.cursor.execute(f"USE `database`;")
        self.cursor.execute(f'SELECT `channel_id`,`role_id` FROM `notify_community` WHERE `notify_type` = %s AND `notify_name` = %s AND `guild_id` = %s;',(notify_type,notify_name,guild_id))
        return self.cursor.fetchall()

    def get_notify_community_userlist(self,notify_type:str):
        """取得指定類型的社群通知清單"""
        self.cursor.execute(f"USE `database`;")
        self.cursor.execute(f'SELECT DISTINCT `notify_name` FROM `notify_community` WHERE `notify_type` = %s;',(notify_type,))
        records = self.cursor.fetchall()
        list = []
        for i in records:
            list.append(i.get('notify_name'))
        return list

    def get_notify_community_list(self,notify_type:str,guild_id:int):
        """取得伺服器內指定種類的所有通知"""
        self.cursor.execute(f"USE `database`;")
        self.cursor.execute(f'SELECT * FROM `notify_community` WHERE `notify_type` = %s AND `guild_id` = %s;',(notify_type,guild_id))
        return self.cursor.fetchall()

class MySQLGameSystem(MySQLBaseModel):
    """遊戲資料系統"""
    def set_game_data(self,discord_id:int,game:DBGame,player_name:str=None,player_id:str=None,account_id:str=None,other_id:str=None):
        """設定遊戲資料"""
        game = DBGame(game)
        self.cursor.execute(f"USE `stardb_user`;")
        self.cursor.execute(f"REPLACE INTO `game_data` VALUES(%s,%s,%s,%s,%s,%s);",(discord_id,game.value,player_name,player_id,account_id,other_id))
        self.connection.commit()

    def remove_game_data(self,discord_id:int,game:DBGame):
        """移除遊戲資料"""
        game = DBGame(game)
        self.cursor.execute(f"USE `stardb_user`;")
        self.cursor.execute(f"DELETE FROM `game_data` WHERE `discord_id` = %s AND `game` = %s;",(discord_id,game.value))
        self.connection.commit()

    def get_game_data(self,discord_id:int,game:DBGame=None) -> dict | GameInfoPage:
        """獲取遊戲資料"""
        self.cursor.execute(f"USE `stardb_user`;")
        if game:
            game = DBGame(game)
            self.cursor.execute(f"SELECT * FROM `game_data` WHERE `discord_id` = %s AND `game` = %s;",(discord_id,game.value))
            records = self.cursor.fetchall()
            if records:
                records = records[0]
        else:
            self.cursor.execute(f"SELECT * FROM `game_data` WHERE `discord_id` = %s;",(discord_id,))
            records = self.cursor.fetchall()
            if records:
                records = GameInfoPage(records)
        return records

class MySQLRoleSaveSystem(MySQLBaseModel):
    def get_role_save(self,discord_id:int):
        self.cursor.execute(f"USE `stardb_user`;")
        self.cursor.execute(f'SELECT * FROM `role_save` WHERE discord_id = %s ORDER BY `time`,`role_id` DESC;',(discord_id,))
        records = self.cursor.fetchall()
        return records

    def get_role_save_count(self,discord_id:int) -> int | None:
        self.cursor.execute(f"USE `stardb_user`;")
        self.cursor.execute(f'SELECT COUNT(*) FROM `role_save` WHERE discord_id = %s;',(discord_id,))
        records = self.cursor.fetchall()
        if records:
            return records[0]['COUNT(*)']
        
    def get_role_save_count_list(self) -> dict[str,int]:
        self.cursor.execute(f"USE `stardb_user`;")
        self.cursor.execute(f'SELECT discord_id,COUNT(*) as count FROM `role_save` GROUP BY `discord_id` ORDER BY `count` ASC;')
        records = self.cursor.fetchall()
        if records:
            dict = {}
            for data in records:
                dict[data['discord_id']] = data['count']
            return dict

    def add_role_save(self,discord_id:int,role:discord.Role):
        self.cursor.execute(f"USE `stardb_user`;")
        self.cursor.execute(f"INSERT INTO `role_save` VALUES(%s,%s,%s,%s)",(discord_id,role.id,role.name,role.created_at.date()))
        self.connection.commit()

class MySQLCurrencySystem(MySQLBaseModel):
    def get_coin(self,discord_id:int,coin:Coins=Coins.SCOIN) -> int:
        """取得用戶擁有的貨幣數"""
        records = self.get_userdata(discord_id,"user_point")
        if records:
            coin = Coins(coin)
            return records.get(coin.value,0)

    def getif_coin(self,discord_id:int,amount:int,coin=Coins.SCOIN) -> int | None:
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

    def update_coins(self,discord_id:str,mod,coin_type:Coins,amount:int):
        """更改用戶的點數數量"""
        coin_type = Coins(coin_type)
        self.cursor.execute(f"USE `stardb_user`;")
        if mod == 'set':
            self.cursor.execute(f"REPLACE INTO `user_point`(discord_id,{coin_type.value}) VALUES(%s,%s);",(discord_id,amount))
        elif mod == 'add':
            self.cursor.execute(f"UPDATE `user_point` SET {coin_type.value} = CASE WHEN `{coin_type.value}` IS NULL THEN {amount} ELSE {coin_type.value} + {amount} END WHERE discord_id = %s;",(discord_id,))
        else:
            raise ValueError("mod must be 'set' or 'add'")
        self.connection.commit()

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

class MySQLHoYoLabSystem(MySQLBaseModel):
    def set_hoyo_cookies(self,discord_id:int,ltuid:str,ltoken:str,cookie_token:str):
        self.cursor.execute(f"USE `database`;")
        self.cursor.execute(f"INSERT INTO `game_hoyo_cookies` VALUES(%s,%s,%s,%s) ON DUPLICATE KEY UPDATE `discord_id` = %s, `ltuid` = %s, `ltoken` = %s, `cookie_token` = %s",(discord_id,ltuid,ltoken,cookie_token,discord_id,ltuid,ltoken,cookie_token))
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

class MySQLPetSystem(MySQLBaseModel):
    def get_pet(self,discord_id:int):
        """取得寵物"""
        records = self.get_userdata(discord_id,"user_pet")
        if records:
            return Pet(records)

    def create_user_pet(self,discord_id:int,pet_species:str,pet_name:str):
        try:
            self.cursor.execute(f"USE `stardb_user`;")
            self.cursor.execute(f'INSERT INTO `user_pet` VALUES(%s,%s,%s,%s);',(discord_id,pet_species,pet_name,20))
            self.connection.commit()
        except sqlerror as e:
            if e.errno == 1062:
                return '你已經擁有寵物了'
            else:
                raise

    def delete_user_pet(self,discord_id:int):
        self.remove_userdata(discord_id,"user_pet")

class MySQLRPGSystem(MySQLBaseModel):
    def get_star_uid_inrpg(self,star_uid:str):
        if star_uid.startswith("IT"):
            self.cursor.execute(f'SELECT * FROM `stardb_idbase`.`rpg_item` AS ri WHERE `star_uid` = {star_uid};')
            records = self.cursor.fetchall()
            if records:
                return RPGItem(records[0])
        elif star_uid.startswith("EQU"):
            self.cursor.execute(f'SELECT * FROM `database`.`rpg_equipment_ingame` AS rei LEFT JOIN `stardb_idbase`.`rpg_equipment` AS re ON rei.equipment_id = re.equipment_id WHERE `star_uid` = %s;',(star_uid,))
            records = self.cursor.fetchall()
            if records:
                return RPGEquipment(records[0])
        
    
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

    def getif_bag(self,discord_id:int,item_uid:int,amount:int):
        self.cursor.execute(f"SELECT * FROM `stardb_user`.`rpg_user_bag` LEFT JOIN `stardb_idbase`.`rpg_item` ON `rpg_user_bag`.item_uid = `rpg_item`.item_uid WHERE discord_id = {discord_id} AND `rpg_user_bag`.item_uid = {item_uid} AND amount >= {amount};")
        records = self.cursor.fetchall()
        if records:
            return RPGItem(records[0])

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

    def get_rpgitem(self,item_uid):
        self.cursor.execute(f"SELECT * FROM `stardb_idbase`.`rpg_item` WHERE `item_uid` = {item_uid};")
        record = self.cursor.fetchall()
        if record:
            return RPGItem(record[0])
        
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
        

    def get_equipmentbag_desplay(self,discord_id):
        self.cursor.execute(f"SELECT * FROM `database`.`rpg_equipment_ingame` AS rei LEFT JOIN `stardb_idbase`.`rpg_equipment` AS re ON rei.equipment_id = re.equipment_id WHERE `discord_id` = {discord_id} ORDER BY re.`equipment_id`;")
        record = self.cursor.fetchall()
        if record:
            return RPGPlayerEquipmentBag(record,self)
        
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
        if record:
            return CityBattle(record,sqldb=self)
        
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

class MySQLWarningSystem(MySQLBaseModel):
    def add_warning(self,discord_id:int,moderate_type:str,moderate_user:int,create_guild:int,create_time:datetime,reason:str=None,last_time:str=None,guild_only=True) -> int:
        """給予用戶警告\n
        returns: 新增的warning_id
        """
        self.cursor.execute(f"INSERT INTO `stardb_user`.`user_moderate` VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s);",(None,discord_id,moderate_type,moderate_user,create_guild,create_time,reason,last_time,guild_only))
        self.connection.commit()
        return self.cursor.lastrowid

    def get_warning(self,warning_id:int):
        """取得警告單"""
        self.cursor.execute(f"SELECT * FROM `stardb_user`.`user_moderate` WHERE `warning_id` = {warning_id};")
        records = self.cursor.fetchall()
        if records:
            return WarningSheet(records[0],self)
    
    def get_warnings(self,discord_id:int,guild_id:int=None):
        """取得用戶的警告列表
        :param guild_id: 若給予，則同時查詢該伺服器的紀錄
        """
        if guild_id:
            self.cursor.execute(f"SELECT * FROM `stardb_user`.`user_moderate` WHERE `discord_id` = {discord_id} AND `create_guild` = {guild_id};")
        else:
            self.cursor.execute(f"SELECT * FROM `stardb_user`.`user_moderate` WHERE `discord_id` = {discord_id} AND `guild_only` = false;")
        records = self.cursor.fetchall()
        return WarningList(records,discord_id,self)
    
    def remove_warning(self,warning_id:int):
        """移除用戶警告"""
        self.cursor.execute(f"DELETE FROM `stardb_user`.`user_moderate` WHERE warning_id = {warning_id};")
        self.connection.commit()

class MySQLPollSystem(MySQLBaseModel):
    def add_poll(self,title:str,created_user:int,created_at:datetime,message_id,guild_id,ban_alternate_account_voting=False,show_name=False,check_results_in_advance=True,results_only_initiator=False,number_of_user_votes=1):
        self.cursor.execute(f"INSERT INTO `database`.`poll_data` VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);",(None,title,created_user,created_at,True,message_id,guild_id,ban_alternate_account_voting,show_name,check_results_in_advance,results_only_initiator,number_of_user_votes))
        self.connection.commit()
        return self.cursor.lastrowid
    
    def remove_poll(self,poll_id:int):
        self.cursor.execute(f"DELETE FROM `database`.`poll_data` WHERE `poll_id` = {poll_id};")
        self.cursor.execute(f"DELETE FROM `stardb_user`.`user_poll` WHERE `poll_id` = {poll_id};")
        self.cursor.execute(f"DELETE FROM `database`.`poll_options` WHERE `poll_id` = {poll_id};")
        self.connection.commit()

    def get_poll(self,poll_id:int):
        self.cursor.execute(f"SELECT * FROM `database`.`poll_data` WHERE `poll_id` = {poll_id};")
        records = self.cursor.fetchall()
        return records[0]
    
    def update_poll(self,poll_id:int,column:str,value):
        self.cursor.execute(f"UPDATE `database`.`poll_data` SET {column} = %s WHERE `poll_id` = %s;",(value,poll_id))
        self.connection.commit()

    def get_all_active_polls(self):
        self.cursor.execute(f"SELECT * FROM `database`.`poll_data` WHERE `is_on` = 1;")
        records = self.cursor.fetchall()
        return records

    def get_poll_options(self,poll_id:int):
        self.cursor.execute(f"SELECT * FROM `database`.`poll_options` WHERE `poll_id` = {poll_id};")
        records = self.cursor.fetchall()
        return records

    def add_poll_option(self,poll_id:int,options:list):
        lst = []
        count = 0
        for option in options:
            count += 1
            lst.append([poll_id, count, option])
        self.cursor.executemany(f"INSERT INTO `database`.`poll_options` VALUES(%s,%s,%s);",lst)
        self.connection.commit()

    def set_user_poll(self, poll_id: int, discord_id: int, vote_option: int = None, vote_at: datetime = None, vote_magnification: int = 1):
        """
        Sets the user's poll vote in the database.

        Args:
            poll_id (int): The ID of the poll.
            discord_id (int): The ID of the user on Discord.
            vote_option (int, optional): The option the user voted for. Defaults to None.
            vote_at (datetime, optional): The timestamp of the vote. Defaults to None.
            vote_magnification (int, optional): The magnification of the vote. Defaults to 1.

        Returns:
            int: The result of the operation. -1 if the user's vote was deleted, 1 if the user's vote was inserted or updated.
        
        Raises:
            SQLNotFoundError: If the poll with the given ID is not found in the database.
        """
        self.cursor.execute(f"SELECT * FROM `stardb_user`.`user_poll` WHERE `poll_id` = {poll_id} AND `discord_id` = {discord_id} AND `vote_option` = {vote_option};")
        dbdata = self.cursor.fetchall()
        if dbdata:
            self.cursor.execute(f"DELETE FROM `stardb_user`.`user_poll` WHERE poll_id = {poll_id} AND discord_id = {discord_id} AND vote_option = {vote_option};")
            text = -1
        else:
            self.cursor.execute(f"INSERT INTO `stardb_user`.`user_poll` VALUES(%s,%s,%s,%s,%s);",(poll_id,discord_id,vote_option,vote_at,vote_magnification))
            text = 1
        
        self.connection.commit()
        return text

    def get_user_vote_count(self,poll_id,discord_id):
        self.cursor.execute(f"SELECT count(*) FROM `stardb_user`.`user_poll` WHERE `poll_id` = {poll_id} AND `discord_id` = {discord_id};")
        dbdata = self.cursor.fetchall()
        return dbdata[0]["count(*)"] if dbdata else 0

    def add_user_poll(self,poll_id:int,discord_id:int,vote_option:int,vote_at:datetime,vote_magnification:int=1):
        self.cursor.execute(f"INSERT INTO `stardb_user`.`user_poll` VALUES(%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE `vote_option` = %s, `vote_at` = %s, `vote_magnification` = %s;",(poll_id,discord_id,vote_option,vote_at,vote_magnification,vote_option,vote_at,vote_magnification))
        self.connection.commit()
    
    def remove_user_poll(self,poll_id:int,discord_id:int):
        self.cursor.execute(f"DELETE FROM `stardb_user`.`user_poll` WHERE `poll_id` = {poll_id} AND `discord_id` = {discord_id};")
        self.connection.commit()
    
    def get_user_poll(self,poll_id:int,discord_id:int):
        self.cursor.execute(f"""
                            SELECT 
                                `user_poll`.*, `poll_options`.option_name
                            FROM
                                `stardb_user`.`user_poll`
                                    LEFT JOIN
                                `database`.`poll_options` ON `user_poll`.vote_option = `poll_options`.option_id
                                    AND `user_poll`.poll_id = `poll_options`.poll_id
                            WHERE
                                `user_poll`.poll_id = {poll_id}
                                    AND `discord_id` = {discord_id};
                            """)
        records = self.cursor.fetchall()
        return records
    
    def get_users_poll(self,poll_id:int,include_alternatives_accounts=True):
        if include_alternatives_accounts:
            self.cursor.execute(f"SELECT * FROM `stardb_user`.`user_poll` WHERE poll_id = {poll_id};")
        else:
            self.cursor.execute(f"SELECT * FROM `stardb_user`.`user_poll` LEFT JOIN `stardb_user`.`user_account` ON `user_poll`.discord_id = `user_account`.alternate_account WHERE poll_id = {poll_id} AND alternate_account IS NULL;")
        records = self.cursor.fetchall()
        return records
    
    def get_poll_vote_count(self,poll_id:int,include_alternatives_accounts=True):
        if include_alternatives_accounts:
            self.cursor.execute(f"SELECT vote_option,SUM(vote_magnification) as count FROM `stardb_user`.`user_poll` WHERE `poll_id` = {poll_id} GROUP BY vote_option;")
        else:
            self.cursor.execute(f"SELECT vote_option,SUM(vote_magnification) as count FROM `stardb_user`.`user_poll` LEFT JOIN `stardb_user`.`user_account` ON `user_poll`.discord_id = `user_account`.alternate_account WHERE poll_id = {poll_id} AND alternate_account IS NULL GROUP BY vote_option;")
        records = self.cursor.fetchall()
        dict = {}
        if records:
            for i in records:
                dict[str(i["vote_option"])] = int(i["count"])
        return dict
    
    def add_poll_role(self,poll_id:int,role_id:int,role_type:int,role_magnification:int=1):
        """role_type 1:只有此身分組可投票 2:倍率 """
        self.cursor.execute(f"INSERT INTO `database`.`poll_role` VALUES(%s,%s,%s,%s) ON DUPLICATE KEY UPDATE `role_type` = %s, `role_magnification` = %s;",(poll_id,role_id,role_type,role_magnification,role_type,role_magnification))
        self.connection.commit()
    
    def get_poll_role(self,poll_id:int,role_type:int=None):
        if role_type:
            self.cursor.execute(f"SELECT * FROM `database`.`poll_role` WHERE `poll_id` = {poll_id} AND `role_type` = {role_type};")
        else:
            self.cursor.execute(f"SELECT * FROM `database`.`poll_role` WHERE `poll_id` = {poll_id};")
        return self.cursor.fetchall()

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
                `party_data`.*, COUNT(`user_party`.party_id) AS count
            FROM
                `database`.`party_data`
                    LEFT JOIN
                `stardb_user`.`user_party` ON party_data.party_id = user_party.party_id
            GROUP BY `party_id`
            ORDER BY `party_id`;
        """)
        records = self.cursor.fetchall()
        return records
    
    def get_user_party(self,discord_id:int):
        self.cursor.execute(f"SELECT `user_party`.discord_id,`party_data`.* FROM `stardb_user`.`user_party` LEFT JOIN `database`.`party_data` ON user_party.party_id = party_data.party_id WHERE `discord_id` = {discord_id}")
        records = self.cursor.fetchall()
        return records
    
    def get_party_data(self,party_id:int):
        self.cursor.execute(f"SELECT * FROM `database`.`party_data` WHERE `party_id` = {party_id};")
        records = self.cursor.fetchall()
        if records:
            return records[0]

class MySQLRegistrationSystem(MySQLBaseModel):
    def get_resgistration_dict(self):
        self.cursor.execute(f"SELECT * FROM `stardb_idbase`.`discord_registrations`;")
        records = self.cursor.fetchall()
        if records:
            dict = {}
            for i in records:
                dict[i['guild_id']] = i['role_id']
            return dict

    def get_resgistration(self,registrations_id:int):
        self.cursor.execute(f"SELECT * FROM `stardb_idbase`.`discord_registrations` WHERE `registrations_id` = {registrations_id};")
        records = self.cursor.fetchall()
        if records:
            return records[0]
        
    def get_resgistration_by_guildid(self,guild_id:int):
        self.cursor.execute(f"SELECT * FROM `stardb_idbase`.`discord_registrations` WHERE `guild_id` = {guild_id};")
        records = self.cursor.fetchall()
        if records:
            return records[0]

class MySQLBackupSystem(MySQLBaseModel):
    def backup_role(self,role:discord.Role,description:str=None):
        self.cursor.execute(f"INSERT INTO `stardb_backup`.`roles_backup` VALUES(%s,%s,%s,%s,%s,%s,%s,%s);",(role.id,role.name,role.created_at,role.guild.id,role.colour.r,role.colour.g,role.colour.b,description))
        for member in role.members:
            self.cursor.execute(f"INSERT INTO `stardb_backup`.`role_user_backup` VALUES(%s,%s);",(role.id,member.id))
        self.connection.commit()

class MySQLTokensSystem(MySQLBaseModel):
    def set_oauth(self, user_id:int, type:CommunityType, access_token:str, refresh_token:str=None, expires_at:datetime=None):
        type = CommunityType(type)
        self.cursor.execute(f"INSERT INTO `stardb_tokens`.`oauth_token` VALUES(%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE `access_token` = %s, `refresh_token` = %s, `expires_at` = %s;",(user_id,type.value,access_token,refresh_token,expires_at,access_token,refresh_token,expires_at))
        self.connection.commit()

    def get_oauth(self, user_id:int, type:CommunityType):
        type = CommunityType(type)
        self.cursor.execute(f"SELECT * FROM `stardb_tokens`.`oauth_token` WHERE `user_id` = {user_id} AND `type` = {type.value};")
        records = self.cursor.fetchall()
        if records:
            return records[0]

class MySQLDatabase(
    MySQLUserSystem,
    MySQLNotifySystem,
    MySQLGameSystem,
    MySQLRoleSaveSystem,
    MySQLCurrencySystem,
    MySQLHoYoLabSystem,
    MySQLBetSystem,
    MySQLPetSystem,
    MySQLRPGSystem,
    MySQLWarningSystem,
    MySQLPollSystem,
    MYSQLElectionSystem,
    MySQLRegistrationSystem,
    MySQLBackupSystem,
    MySQLTokensSystem,
):
    """Mysql操作"""