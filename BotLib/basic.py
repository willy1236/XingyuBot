import json

class Counter(dict):
    def __missing__(self,key):
        return 0

class Database:
    def __init__(self):
        self.dict = {'jdata':'setting.json',
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
                'rsdata':'database/role_save.json'}
        self.jdata = json.load(open(self.dict['jdata'],mode='r',encoding='utf8'))
        self.cdata = json.load(open(self.dict['cdata'],mode='r',encoding='utf8'))
        self.picdata = json.load(open(self.dict['picdata'],mode='r',encoding='utf8'))
        self.udata = json.load(open(self.dict['udata'],'r',encoding='utf8'))
        self.jpt = Counter(json.load(open(self.dict['jpt'],mode='r',encoding='utf8')))
        self.jloot = Counter(json.load(open(self.dict['jloot'],mode='r',encoding='utf8')))
        self.bet_data = Counter(json.load(open(self.dict['bet_data'],mode='r',encoding='utf8')))
        self.gdata = json.load(open(self.dict['gdata'],'r',encoding='utf8'))
        self.jdsign = json.load(open(self.dict['jdsign'],mode='r',encoding='utf8'))
        self.jwsign = Counter(json.load(open(self.dict['jwsign'],mode='r',encoding='utf8')))
        self.jevent = Counter(json.load(open(self.dict['jevent'],mode='r',encoding='utf8')))
        self.redata = Counter(json.load(open(self.dict['rsdata'],mode='r',encoding='utf8')))
        
    def write(self,file:str,data:dict):
        location = self.dict[file]
        with open(file=location,mode='w',encoding='utf8') as jfile:
            json.dump(data,jfile,indent=4)
