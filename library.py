import json
from discord.ext import commands

#(*args) 傳入多個參數
#(**kwargs) 傳入多個參數並轉變為dict
#'value' in dict 偵測dict內是否有value
#len(list) 查詢list內的個數

#json開啟法1
#with open('.../XXX.json','r') as f:
#    data= json.load(f)
#json開啟法2
#data = json.load(open('.../XXX.json','r'))

def is_number(n):
    try:  
        float(n)
        return True
    except ValueError:
        pass
    try:
        import unicodedata
        unicodedata.numeric(n)
        return True
    except (TypeError, ValueError):
        pass
    return False

#menber_id:要檢測pt的用戶id(int,str形式皆可)
def check_point(menber_id):
    jpt = Counter(json.load(open('point.json',mode='r',encoding='utf8')))
    #json內資料格為str形式
    pt = jpt[str(menber_id)]
    return pt

#如果讀不到資料補0避免keyerror
class Counter(dict):
    def __missing__(self,key): 
        return 0

#arg:要檢測的內容(名稱#0000,id,mention...)
async def find_user(ctx,arg):
    if arg == None:
        member = None
    else:
        try:
            member = await commands.MemberConverter().convert(ctx,arg)
        except commands.MemberNotFound:
            member = None
    return member

async def find_channel(ctx,arg):
    if arg == None:
        channel = None
    else:
        try:
            channel = await commands.TextChannelConverter().convert(ctx,arg)
        except commands.ChannelNotFound:
            channel = None
    return channel

async def find_user2(ctx,arg):
    try:
        user = await commands.UserConverter().convert(ctx,arg)
    except commands.UserNotFound:
        user = None
    return user

class find():
    pass

def message_update(message):
    pass

