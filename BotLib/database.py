import json,os

class Counter(dict):
    def __missing__(self,key):
        return 0

class Database:
    def __init__(self):
        """
        CWB = 中央氣象局\n
        TRN = tracker.gg
        """
        self.dict = {
            'jdata':'database/setting.json',
            'cdata':'database/channel_settings.json',
            'picdata':'database/picture.json',
            'udata': 'database/user_settings/basic.json',
            'jpt':'database/point.json',
            'jloot':'database/lottery.json',
            'bet_data':'database/bet.json',
            'gdata':'database/gamer_data.json',
            'jdsign':'database/sign_day.json',
            'jwsign':'database/sign_week.json',
            'jevent':'database/event.json',
            'rsdata':'database/role_save.json'
            }
        self.jdata = json.load(open(self.dict['jdata'],mode='r',encoding='utf8'))
        self.cdata = json.load(open(self.dict['cdata'],mode='r',encoding='utf8'))
        self.picdata = json.load(open(self.dict['picdata'],mode='r',encoding='utf8'))
        self.udata = json.load(open(self.dict['udata'],'r',encoding='utf8'))
        self.jpt = Counter(json.load(open(self.dict['jpt'],mode='r',encoding='utf8')))
        self.jloot = Counter(json.load(open(self.dict['jloot'],mode='r',encoding='utf8')))
        self.bet_data = Counter(json.load(open(self.dict['bet_data'],mode='r',encoding='utf8')))
        self.gdata = Counter(json.load(open(self.dict['gdata'],'r',encoding='utf8')))
        self.jdsign = json.load(open(self.dict['jdsign'],mode='r',encoding='utf8'))
        self.jwsign = Counter(json.load(open(self.dict['jwsign'],mode='r',encoding='utf8')))
        self.jevent = Counter(json.load(open(self.dict['jevent'],mode='r',encoding='utf8')))
        self.rsdata = Counter(json.load(open(self.dict['rsdata'],mode='r',encoding='utf8')))

        try:
            self.tokens = json.load(open('database/token_settings.json',mode='r',encoding='utf8'))
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
            location = self.dict[file]
            with open(file=location,mode='w',encoding='utf8') as jfile:
                json.dump(data,jfile,indent=4)
        except:
            raise KeyError("此項目沒有在資料庫中")

    @staticmethod
    def get_gamedata(user_id:str,game:str):
        gdata = Database().gdata
        try:
            data = gdata[user_id][game]
            if game in ['steam']:
                data = data['id']
            return data
        except:
            return None
