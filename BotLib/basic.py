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
                'jpt':'database/point.json'}
        self.jdata = json.load(open('setting.json',mode='r',encoding='utf8'))
        self.cdata = json.load(open('database/channel_settings.json',mode='r',encoding='utf8'))
        self.picdata = json.load(open('database/picture.json',mode='r',encoding='utf8'))
        self.udata = json.load(open('database/user_settings/basic.json','r',encoding='utf8'))
        self.jpt = Counter(json.load(open('database/point.json',mode='r',encoding='utf8')))

    def write(self,file,data):
        location = self.dict[file]
        with open(file=location,mode='w',encoding='utf8') as jfile:
            json.dump(data,jfile,indent=4)
