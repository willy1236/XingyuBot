import json,os,mysql.connector,discord
from BotLib.funtions import find
from pydantic import BaseModel


class Database():
    pass

class JsonDatabase(Database):
    def __init__(self):
        """
        CWB = 中央氣象局\n
        TRN = tracker.gg
        """
        location = "database"
        data_location = "data"
        self.__dict = {
            'jdict': f'{data_location}/dict.json',
            'jdata': f'{location}/setting.json',
            'cdata': f'{location}/channel_settings.json',
            'picdata': f'{data_location}/bot_settings/picture.json',
            'udata': f'{location}/user_settings/basic.json',
            'jpt': f'{location}/user_settings/point.json',
            'jloot': f'{location}/lottery.json',
            'bet_data': f'{location}/bet.json',
            'gdata': f'{location}/gamer_data.json',
            'jdsign': f'{location}/sign_day.json',
            'jwsign': f'{location}/sign_week.json',
            'jevent': f'{location}/bot_settings/event.json',
            'rsdata': f'{location}/role_save.json',
            'jpet': f'{location}/user_settings/pet.json',
            'jbag': f'{location}/user_settings/bag.json',
            'cache': f'{location}/cache.json',
            'monster_basic': f'{data_location}/RPG_settings/monster_basic.json',
            'jRcoin': f'{location}/user_settings/rcoin.json',
            'jhoyo': f'{location}/game_settings/hoyo.json',
            'jtwitch': f'{location}/community_settings/twitch.json',
        }
        self.jdict = json.load(open(self.__dict['jdict'],mode='r',encoding='utf8'))
        self.jdata = json.load(open(self.__dict['jdata'],mode='r',encoding='utf8'))
        self.cdata = json.load(open(self.__dict['cdata'],mode='r',encoding='utf8'))
        self.picdata = json.load(open(self.__dict['picdata'],mode='r',encoding='utf8'))
        self.udata = json.load(open(self.__dict['udata'],'r',encoding='utf8'))
        self.jpt = json.load(open(self.__dict['jpt'],mode='r',encoding='utf8'))
        self.jloot = json.load(open(self.__dict['jloot'],mode='r',encoding='utf8'))
        self.bet_data = json.load(open(self.__dict['bet_data'],mode='r',encoding='utf8'))
        self.gdata = json.load(open(self.__dict['gdata'],'r',encoding='utf8'))
        self.jdsign = json.load(open(self.__dict['jdsign'],mode='r',encoding='utf8'))
        self.jwsign = json.load(open(self.__dict['jwsign'],mode='r',encoding='utf8'))
        self.jevent = json.load(open(self.__dict['jevent'],mode='r',encoding='utf8'))
        self.rsdata = json.load(open(self.__dict['rsdata'],mode='r',encoding='utf8'))
        self.jpet = json.load(open(self.__dict['jpet'],mode='r',encoding='utf8'))
        self.jbag = json.load(open(self.__dict['jbag'],mode='r',encoding='utf8'))
        self.cache = json.load(open(self.__dict['cache'],mode='r',encoding='utf8'))
        self.monster_basic = json.load(open(self.__dict['monster_basic'],mode='r',encoding='utf8'))
        self.jRcoin = json.load(open(self.__dict['jRcoin'],mode='r',encoding='utf8'))
        self.jhoyo = json.load(open(self.__dict['jhoyo'],mode='r',encoding='utf8'))
        self.jtwitch = json.load(open(self.__dict['jtwitch'],mode='r',encoding='utf8'))

        try:
            self.tokens = json.load(open(f'{location}/token_settings.json',mode='r',encoding='utf8'))
        except:
            self.tokens = os.environ

    def write(self,file:str,data:dict):
        try:
            location = self.__dict[file]
            with open(file=location,mode='w',encoding='utf8') as jfile:
                json.dump(data,jfile,indent=4)
        except:
            raise KeyError("此項目沒有在資料庫中")

    def get_token(self,webname:str):
        """獲取相關api的tokens\n
        支援CWB_API,osu(id,secret),TRN,apex,steam,twitch(id,secret),youtube
        """
        dict = {
            "CWB_API":'CWB_API',
            'osu':'osu',
            'TRN':'TRN_API',
            'apex':'apex_status_API',
            'steam':'steam_api',
            'twitch':'twitch',
            'youtube':'youtube_api'
            }
        if webname in dict:
            if webname == 'osu':
                return (self.tokens['osu_API_id'],self.tokens['osu_API_secret'])
            if webname == 'twitch':
                return (self.tokens['twitch_api_id'],self.tokens['twitch_api_secret'])
            else:
                name = dict[webname]
                return self.tokens[name]
        else:
            raise ValueError('無此API token')

    @staticmethod
    async def get_gamedata(user_id:str, game:str, ctx:discord.ApplicationContext=None):
        """查詢資料庫中的玩家資訊，若輸入dc用戶則需傳入ctx\n
        dcuser and in database -> 資料庫資料\n
        dcuser and not in database -> None\n
        not dcuser -> user_id(原資料輸出)
        """
        gdata = JsonDatabase().gdata
        
        if ctx:
            dcuser = await find.user2(ctx,user_id)
            if dcuser:
                user_id = str(dcuser.id)
            else:
                return user_id
        else:
            user_id = str(user_id)

        try:
            data = gdata[str(user_id)][game]
            if game in ['steam']:
                data = data['id']
            return data
        except:
            return None

        
            
class MySQLDatabase(Database):
    def __init__(self,**settings):
        '''MySQL 資料庫連接\n
        settings = {"host": "","port": ,"user": "","password": "","db": "","charset": ""}
        '''
        #建立連線
        self.connection = mysql.connector.connect(**settings)
        self.cursor = self.connection.cursor(dictionary=True)

    def add_data(self,table:str,*value,db="database"):
        self.cursor.execute(f"USE `{db}`;")
        self.cursor.execute(f"INSERT INTO `{table}` VALUES(%s)",value)
        self.connection.commit()

    def replace_data(self,table:str,*value,db="database"):
        self.cursor.execute(f"USE `{db}`;")
        self.cursor.execute(f"REPLACE INTO `{table}` VALUES(%s)",value)
        self.connection.commit()

    def get_data(self,table:str):
        db = "database"
        self.cursor.execute(f"USE `{db}`;")
        self.cursor.execute(f'SELECT * FROM `{table}` WHERE id = %s;',("1",))
        #self.cursor.execute('SELECT * FROM `user_data`;')
        
        records = self.cursor.fetchall()
        for r in records:
             print(r)
    
    def remove_data(self,table:str,*value):
        db = "database"
        self.cursor.execute(f"USE `{db}`;")
        #self.cursor.execute(f'DELETE FROM `{table}` WHERE `id` = %s;',("3",))
        self.cursor.execute(f'DELETE FROM `{table}` WHERE `id` = %s;',value)
        self.connection.commit()


    def set_user(self,id:str,name:str=None):
        self.cursor.execute(f"USE `database`;")
        self.cursor.execute(f"INSERT INTO `user_data` VALUES(%s,%s);",(id,name))
        self.connection.commit()

    def get_user(self,id:str):
        db = "database"
        self.cursor.execute(f"USE `{db}`;")
        self.cursor.execute('SELECT * FROM `user_data` WHERE id = %s;',(str(id),))
        records = self.cursor.fetchone()
        return records

    def remove_user(self,id:str):
        db = "database"
        self.cursor.execute(f"USE `{db}`;")
        self.cursor.execute("DELETE FROM `user_data` WHERE `id` = %s;",(str(id),))
        self.connection.commit()
    
    def set_game_data(self,user_id:str,game:str,player_name:str=None,player_id:str=None):
        self.cursor.execute(f"USE `database`;")
        self.cursor.execute(f"REPLACE INTO `game_data` VALUES(%s,%s,%s,%s);",(user_id,game,player_name,player_id))
        self.connection.commit()

    def remove_game_data(self,user_id:str,game:str):
        self.cursor.execute(f"USE `database`;")
        self.cursor.execute(f"DELETE FROM `game_data` WHERE `id` = %s AND `game` = %s;",(user_id,game))
        self.connection.commit()

    def get_game_data(self,user_id:str,game:str=None):
        self.cursor.execute(f"USE `database`;")
        if game:
            self.cursor.execute(f"SELECT * FROM `game_data` WHERE `id` = %s AND `game` = %s;",(user_id,game))
        else:
            self.cursor.execute(f"SELECT * FROM `game_data` WHERE `id` = %s;",(user_id,))
        records = self.cursor.fetchall()
        return records

    def get_role_save(self,id:str):
        self.cursor.execute(f"USE `database`;")
        self.cursor.execute(f'SELECT * FROM `role_save` WHERE user_id = %s;',(id,))
        records = self.cursor.fetchall()
        return records

    def get_role_save_count(self,id:str):
        self.cursor.execute(f"USE `database`;")
        self.cursor.execute(f'SELECT COUNT(user_id) FROM `role_save` WHERE user_id = %s;',(id,))
        records = self.cursor.fetchall()
        return records

    def add_role_save(self,user_id:str,role_id:str,role_name:str,time:str):
        self.cursor.execute(f"USE `database`;")
        self.cursor.execute(f"INSERT INTO `role_save` VALUES(%s,%s,%s,%s)",(user_id,role_id,role_name,time))
        self.connection.commit()

class GameDatabase(Database):
    pass