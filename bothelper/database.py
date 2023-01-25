# import mysql.connector,datetime
# from pydantic import BaseModel
# from mysql.connector.errors import Error as sqlerror
# from bothelper.interface.user import User
       
# class MySQLDatabase():
#     def __init__(self,**settings):
#         '''MySQL 資料庫連接\n
#         settings = {"host": "","port": ,"user": "","password": "","db": "","charset": ""}
#         '''
#         #建立連線
#         self.connection = mysql.connector.connect(**settings)
#         self.cursor = self.connection.cursor(dictionary=True)
#         self.connection.get_server_info()

#     def add_data(self,table:str,*value,db="database"):
#         self.cursor.execute(f"USE `{db}`;")
#         self.cursor.execute(f"INSERT INTO `{table}` VALUES(%s)",value)
#         self.connection.commit()

#     def replace_data(self,table:str,*value,db="database"):
#         self.cursor.execute(f"USE `{db}`;")
#         self.cursor.execute(f"REPLACE INTO `{table}` VALUES(%s)",value)
#         self.connection.commit()

#     def get_data(self,table:str):
#         db = "database"
#         self.cursor.execute(f"USE `{db}`;")
#         self.cursor.execute(f'SELECT * FROM `{table}` WHERE id = %s;',("1",))
#         #self.cursor.execute('SELECT * FROM `user_data`;')
        
#         records = self.cursor.fetchall()
#         for r in records:
#              print(r)
    
#     def remove_data(self,table:str,*value):
#         db = "database"
#         self.cursor.execute(f"USE `{db}`;")
#         #self.cursor.execute(f'DELETE FROM `{table}` WHERE `id` = %s;',("3",))
#         self.cursor.execute(f'DELETE FROM `{table}` WHERE `id` = %s;',value)
#         self.connection.commit()

#     def truncate_table(self,table:str):
#         self.cursor.execute(f"USE `database`;")
#         self.cursor.execute(f"TRUNCATE TABLE `{table}`;")



#     def update_userdata(self,user_id:str,table:str,column:str,value):
#         self.cursor.execute(f"USE `database`;")
#         self.cursor.execute(f"INSERT INTO `{table}` SET user_id = {user_id}, {column} = {value} ON DUPLICATE KEY UPDATE user_id = {user_id}, {column} = {value};")
#         self.connection.commit()

#     def get_userdata(self,user_id:str,table:str='user_data'):
#         self.cursor.execute(f"USE `database`;")
#         self.cursor.execute(f'SELECT * FROM `{table}` WHERE user_id = %s;',(str(user_id),))
#         records = self.cursor.fetchone()
#         return records

#     def get_user(self,user_id:str):
#         self.cursor.execute(f"USE `database`;")
#         self.cursor.execute(f'SELECT * FROM `user_data`,`user_point` WHERE user_data.user_id = %s;',(str(user_id),))
#         record = self.cursor.fetchone()
#         return User(self,record)

#     def set_user(self,id:str,name:str=None):
#         self.cursor.execute(f"USE `database`;")
#         self.cursor.execute(f"INSERT INTO `user_data` VALUES(%s,%s);",(id,name))
#         self.connection.commit()

#     def remove_user(self,id:str):
#         self.cursor.execute(f"USE `database`;")
#         self.cursor.execute("DELETE FROM `user_data` WHERE `id` = %s;",(str(id),))
#         self.connection.commit()
    
#     def set_game_data(self,user_id:str,game:str,player_name:str=None,player_id:str=None):
#         self.cursor.execute(f"USE `database`;")
#         self.cursor.execute(f"REPLACE INTO `game_data` VALUES(%s,%s,%s,%s);",(user_id,game,player_name,player_id))
#         self.connection.commit()

#     def remove_game_data(self,user_id:str,game:str):
#         self.cursor.execute(f"USE `database`;")
#         self.cursor.execute(f"DELETE FROM `game_data` WHERE `id` = %s AND `game` = %s;",(user_id,game))
#         self.connection.commit()

#     def get_game_data(self,user_id:str,game:str=None):
#         self.cursor.execute(f"USE `database`;")
#         if game:
#             self.cursor.execute(f"SELECT * FROM `game_data` WHERE `id` = %s AND `game` = %s;",(user_id,game))
#         else:
#             self.cursor.execute(f"SELECT * FROM `game_data` WHERE `id` = %s;",(user_id,))
#         records = self.cursor.fetchall()
#         return records

#     def get_role_save(self,id:str):
#         self.cursor.execute(f"USE `database`;")
#         self.cursor.execute(f'SELECT * FROM `role_save` WHERE user_id = %s ORDER BY `time` DESC;',(id,))
#         records = self.cursor.fetchall()
#         return records

#     def get_role_save_count(self,user_id:str):
#         self.cursor.execute(f"USE `database`;")
#         self.cursor.execute(f'SELECT COUNT(user_id) FROM `role_save` WHERE user_id = %s;',(user_id,))
#         records = self.cursor.fetchall()
#         return records

#     def add_role_save(self,user_id:str,role_id:str,role_name:str,time:str):
#         self.cursor.execute(f"USE `database`;")
#         self.cursor.execute(f"INSERT INTO `role_save` VALUES(%s,%s,%s,%s)",(user_id,role_id,role_name,time))
#         self.connection.commit()

#     def get_point(self,user_id:str):
#         self.cursor.execute(f"USE `database`;")
#         self.cursor.execute(f'SELECT * FROM `user_point` WHERE user_id = %s;',(user_id,))
#         records = self.cursor.fetchone()
#         return records

#     def getif_point(self,user_id:str,point:int):
#         self.cursor.execute(f"USE `database`;")
#         self.cursor.execute(f'SELECT `user_id` FROM `user_point` WHERE user_id = %s AND point >= %s;',(user_id,point))
#         records = self.cursor.fetchone()
#         return records

#     def give_point(self,giver_id:str,given_id:str,amount:int):
#         self.cursor.execute(f"USE `database`;")
#         self.cursor.execute(f'SELECT * FROM `user_point` WHERE user_id = %s AND point >= %s;',(giver_id,amount))
#         records = self.cursor.fetchone()
#         if records:
#             self.cursor.execute(f"UPDATE `user_point` SET point = point - %s WHERE user_id = %s;",(amount,giver_id))
#             self.cursor.execute(f"INSERT INTO `user_point` SET user_id = %s, point = %s ON DUPLICATE KEY UPDATE user_id = %s, point = point + %s",(given_id,amount,given_id,amount))
#             self.connection.commit()
#             #self.cursor.execute(f"UPDATE `user_point` SET `point` = REPLACE(`欄位名`, '要被取代的欄位值', '取代後的欄位值') WHERE `欄位名` LIKE '%欄位值%';",(giver_id,amount))
#             return 0
#         else:
#             return 1

#     def update_point(self,mod,user_id:str,amount:int):
#         self.cursor.execute(f"USE `database`;")
#         if mod == 'set':
#             self.cursor.execute(f"REPLACE INTO `game_data`(user_id,point) VALUES(%s,%s);",(user_id,amount))
#         elif mod == 'add':
#             self.cursor.execute(f"UPDATE `user_point` SET point = point + %s WHERE user_id = %s;",(amount,user_id))
#         self.connection.commit()
    
#     def user_sign(self,user_id:str):
#         try:
#             time = datetime.datetime.now()
#             self.cursor.execute(f"USE `database`;")
#             self.cursor.execute(f"INSERT INTO `user_sign` VALUES(%s,%s)",(user_id,time))
#             self.connection.commit()
#         except sqlerror as e:
#             if e.errno == 1062:
#                 return 1
#             else:
#                 raise

#     def sign_add_coin(self,user_id:str,point:int,Rcoin:int):
#         self.cursor.execute(f"USE `database`;")
#         self.cursor.execute(f"INSERT INTO `user_point` SET user_id = %s, point = %s,rcoin = %s ON DUPLICATE KEY UPDATE user_id = %s, point = point + %s,rcoin = %s",(user_id,point,Rcoin,user_id,point,Rcoin))
#         self.connection.commit()

#     def set_hoyo_cookies(self,user_id:str,ltuid:str,ltoken:str):
#         self.cursor.execute(f"USE `database`;")
#         self.cursor.execute(f"INSERT INTO `game_hoyo_cookies` SET user_id = {user_id}, ltuid = {ltuid}, ltoken = {ltoken} ON DUPLICATE KEY UPDATE user_id = {user_id}, ltuid = {ltuid}, ltoken = {ltoken}")
#         self.connection.commit()

#     def set_notice_channel(self,guild_id:int,notice_type:str,channel_id:int,role_id:int=None):    
#         self.cursor.execute(f"USE `database`;")
#         self.cursor.execute(f"INSERT INTO `notice_channel` VALUES(%s,%s,%s,%s) ON DUPLICATE KEY UPDATE `guild_id` = %s, `notice_type` = %s, `channel_id` = %s, `role_id` = %s",(guild_id,notice_type,channel_id,role_id,guild_id,notice_type,channel_id,role_id))
#         self.connection.commit()

#     def remove_notice_channel(self,guild_id:int,notice_type:str):
#         self.cursor.execute(f"USE `database`;")
#         self.cursor.execute(f'DELETE FROM `notice_channel` WHERE `guild_id` = %s AND `notice_type` = %s;',(guild_id,notice_type))
#         self.connection.commit()

#     def get_notice_channel(self,notice_type:str):
#         self.cursor.execute(f"USE `database`;")
#         self.cursor.execute(f'SELECT * FROM `notice_channel` WHERE notice_type = %s;',(notice_type,))
#         records = self.cursor.fetchall()
#         return records

#     def set_notice_community(self,notice_type:str,notice_name:str,guild_id:int,channel_id:int,role_id:int=None):
#         self.cursor.execute(f"USE `database`;")
#         self.cursor.execute(f"INSERT INTO `notice_community` VALUES(%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE `notice_type` = %s, `notice_name` = %s, `guild_id` = %s, `channel_id` = %s, `role_id` = %s",(notice_type,notice_name,guild_id,channel_id,role_id,notice_type,notice_name,guild_id,channel_id,role_id))
#         self.connection.commit()

#     def remove_notice_community(self,notice_type:str,notice_name:str,guild_id:int):
#         self.cursor.execute(f"USE `database`;")
#         self.cursor.execute(f'DELETE FROM `notice_community` WHERE `notice_type` = %s AND `notice_name` = %s AND `guild_id` = %s;',(notice_type,notice_name,guild_id))
#         self.connection.commit()

#     def get_notice_community(self,notice_type:str):
#         self.cursor.execute(f"USE `database`;")
#         self.cursor.execute(f'SELECT * FROM `notice_community` WHERE `notice_type` = %s;',(notice_type,))
#         records = self.cursor.fetchall()
#         return records
    
#     def get_notice_community_guild(self,notice_type:str,notice_name:str):
#         self.cursor.execute(f"USE `database`;")
#         self.cursor.execute(f'SELECT `guild_id`,`channel_id`,`role_id` FROM `notice_community` WHERE `notice_type` = %s AND `notice_name` = %s;',(notice_type,notice_name))
#         records = self.cursor.fetchall()
#         dict = {}
#         for i in records:
#             dict[i['guild_id']] = [i['channel_id'],i['role_id']]
#         return dict

#     def get_notice_community_userlist(self,notice_type:str):
#         self.cursor.execute(f"USE `database`;")
#         self.cursor.execute(f'SELECT DISTINCT `notice_name` FROM `notice_community` WHERE `notice_type` = %s;',(notice_type,))
#         records = self.cursor.fetchall()
#         list = []
#         for i in records:
#             list.append(i.values())
#         return list

#     def get_bet_data(self,bet_id:int):
#         self.cursor.execute(f"USE `database`;")
#         self.cursor.execute(f'SELECT `bet_id`,`IsOn` FROM `bet_data` WHERE `bet_id` = %s;',(bet_id,))
#         records = self.cursor.fetchone()
#         return records

#     def place_bet(self,bet_id:int,choice:str,money:int):
#         self.cursor.execute(f"USE `database`;")
#         self.cursor.execute(f'INSERT INTO `user_bet` VALUES(%s,%s,%s);',(bet_id,choice,money))
#         self.connection.commit()

#     def create_bet(self,bet_id:int,title:str,pink:str,blue:str):
#         self.cursor.execute(f"USE `database`;")
#         self.cursor.execute(f'INSERT INTO `bet_data` VALUES(%s,%s,%s,%s,%s);',(bet_id,title,pink,blue,True))
#         self.connection.commit()

#     def update_bet(self,bet_id:int):
#         self.cursor.execute(f"USE `database`;")
#         self.cursor.execute(f"UPDATE `bet_data` SET IsOn = %s WHERE bet_id = %s;",(False,bet_id))
#         self.connection.commit()

#     def get_bet_total(self,bet_id:int):
#         self.cursor.execute(f"USE `database`;")
#         self.cursor.execute(f'SELECT SUM(money) FROM `user_bet` WHERE `bet_id` = %s AND `choice` = %s;',(bet_id,'pink'))
#         total_pink = self.cursor.fetchone()
#         self.cursor.execute(f'SELECT SUM(money) FROM `user_bet` WHERE `bet_id` = %s AND `choice` = %s;',(bet_id,'blue'))
#         total_blue = self.cursor.fetchone()
#         return [int(total_pink['SUM(money)'] or 0),int(total_blue['SUM(money)'] or 0)]

#     def get_bet_winner(self,bet_id:int,winner:str):
#         self.cursor.execute(f"USE `database`;")
#         self.cursor.execute(f'SELECT * FROM `user_bet` WHERE `bet_id` = %s AND `choice` = %s;',(bet_id,winner))
#         records = self.cursor.fetchall()
#         return records

#     def remove_bet(self,bet_id:int):
#         self.cursor.execute(f"USE `database`;")
#         self.cursor.execute(f'DELETE FROM `user_bet` WHERE `bet_id` = %s;',(bet_id,))
#         self.cursor.execute(f'DELETE FROM `bet_data` WHERE `bet_id` = %s;',(bet_id,))
#         self.connection.commit()