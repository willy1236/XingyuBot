import json,os,mysql.connector

from discord.ext import commands

class Counter(dict):
    def __missing__(self,key):
        return 0

async def find_user(ctx,arg:str):
        try:
            user = await commands.UserConverter().convert(ctx,str(arg))
        except commands.UserNotFound:
            user = None
        return user

class Database:
    def __init__(self):
        """
        CWB = 中央氣象局\n
        TRN = tracker.gg
        """
        location = "database"
        self.__dict = {
            'jdata': f'{location}/setting.json',
            'cdata': f'{location}/channel_settings.json',
            'picdata': f'{location}/bot_settings/picture.json',
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
            'monster_basic': f'{location}/RPG_settings/monster_basic.json',
            'jRcoin': f'{location}/user_settings/rcoin.json',
        }
        self.jdata = json.load(open(self.__dict['jdata'],mode='r',encoding='utf8'))
        self.cdata = json.load(open(self.__dict['cdata'],mode='r',encoding='utf8'))
        self.picdata = json.load(open(self.__dict['picdata'],mode='r',encoding='utf8'))
        self.udata = json.load(open(self.__dict['udata'],'r',encoding='utf8'))
        self.jpt = json.load(open(self.__dict['jpt'],mode='r',encoding='utf8'))
        self.jloot = Counter(json.load(open(self.__dict['jloot'],mode='r',encoding='utf8')))
        self.bet_data = Counter(json.load(open(self.__dict['bet_data'],mode='r',encoding='utf8')))
        self.gdata = json.load(open(self.__dict['gdata'],'r',encoding='utf8'))
        self.jdsign = json.load(open(self.__dict['jdsign'],mode='r',encoding='utf8'))
        self.jwsign = Counter(json.load(open(self.__dict['jwsign'],mode='r',encoding='utf8')))
        self.jevent = Counter(json.load(open(self.__dict['jevent'],mode='r',encoding='utf8')))
        self.rsdata = Counter(json.load(open(self.__dict['rsdata'],mode='r',encoding='utf8')))
        self.jpet = json.load(open(self.__dict['jpet'],mode='r',encoding='utf8'))
        self.jbag = json.load(open(self.__dict['jbag'],mode='r',encoding='utf8'))
        self.cache = json.load(open(self.__dict['cache'],mode='r',encoding='utf8'))
        self.monster_basic = json.load(open(self.__dict['monster_basic'],mode='r',encoding='utf8'))
        self.jRcoin = json.load(open(self.__dict['jRcoin'],mode='r',encoding='utf8'))

        try:
            self.tokens = json.load(open(f'{location}/token_settings.json',mode='r',encoding='utf8'))
        except:
            self.tokens = os.environ

        self.CWB_API = self.tokens['CWB_API']
        self.osu_API_id = self.tokens['osu_API_id']
        self.osu_API_secret = self.tokens['osu_API_secret']
        self.TRN_API = self.tokens['TRN_API']
        self.apex_status_API = self.tokens['apex_status_API']
        self.steam_api = self.tokens['steam_api']

    def write(self,file:str,data:dict):
        try:
            location = self.__dict[file]
            with open(file=location,mode='w',encoding='utf8') as jfile:
                json.dump(data,jfile,indent=4)
        except:
            raise KeyError("此項目沒有在資料庫中")

    def get_token(self,webname:str):
        """獲取相關api的tokens\n
        支援CWB_API,osu(id,secret),TRN,apex,steam,twitch(id,secret)
        """
        dict = {
            "CWB_API":'CWB_API',
            'osu':'osu',
            'TRN':'TRN_API',
            'apex':'apex_status_API',
            'steam':'steam_api',
            'twitch':'twitch'
            }
        if webname in dict:
            if webname == 'osu':
                return (self.tokens['osu_API_id'],self.tokens['osu_API_secret'])
            if webname == 'twitch':
                return (self.tokens['twitch_api_id'],self.tokens['twitch_api_secret'])
            else:
                name = dict[webname]
                return self.tokens[name]
    
    def get_data(self,data_file):
        pass

    @staticmethod
    async def get_gamedata(user_id:str, game:str, ctx:commands.context=None):
        """查詢資料庫中的玩家資訊，若輸入dc用戶則需傳入ctx\n
        dcuser and in database -> 資料庫資料\n
        dcuser and not in database -> None\n
        not dcuser -> user_id(原資料輸出)
        """
        gdata = Database().gdata
        
        if ctx:
            dcuser = await find_user(ctx,user_id)
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

class GameDatabase():
    pass

class SQLDatabase():
    def __init__(self,**settings):
        '''MySQL 資料庫連接\n
        settings = {"host": "","port": ,"user": "","password": "","db": "","charset": ""}
        '''
        #建立連線
        self.connection = mysql.connector.connect(**settings)
        self.cursor = self.connection.cursor(dictionary=True)
    
    def user_setup(self,id:str,name:str='NULL'):
        db = "database"
        self.cursor.execute(f"USE `{db}`;")
        self.cursor.execute(f"INSERT INTO `user_data` VALUES({str(id)},{name})")
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

    def add_data(self,table:str,value:tuple,db="database"):
        self.cursor.execute(f"USE `{db}`;")
        self.cursor.execute(f"INSERT INTO `{table}` VALUES(%s)",value)
        self.connection.commit()

    def get_data(self):
        db = "database"
        self.cursor.execute(f"USE `{db}`;")
        self.cursor.execute('SELECT * FROM `user_data` WHERE id = %s;',("1",))
        #self.cursor.execute('SELECT * FROM `user_data`;')
        
        records = self.cursor.fetchall()
        for r in records:
             print(r)
    
    def remove_data(self):
        db = "database"
        self.cursor.execute(f"USE `{db}`;")
        self.cursor.execute('DELETE FROM `user_data` WHERE `id` = %s;',("3",))
        self.connection.commit()