import json,random
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

#json寫入法
#1.mode='r'讀一遍關掉，再mode='r+'或mode='w'開啟dump進去
#2.mode='r+'開啟，先data = json.load(jfile)，最後用json.seek(0)後再dump

#json mode
#'r'=讀取 'w'=寫入(開啟檔案時會先清除內容) 'r+'=讀寫(開啟檔案時不會清除內容)

#list
#s3=s1&s2 # 交集︰取兩個集合中，相同的資料
#s3=s1|s2 # 聯集︰取兩個合中的所有資料，但不重複取
#s3=s1-s2 # 差集︰從 s1 中，減去和 s2 重疊的部分
#s3=s1^s2 # 反交集︰取兩個集合中，重複的部分

#s=set("Hello") # 把字串中的字母折拆成集合
#dic={x:x*2 for x in [3,4,5]} # 從列表的資料中產生字典

#str->list
#i=0
#text = []
#while i< len(arg):
#    text.append(arg[i])
#    i=i+1

#async -> await

def is_number(n):
    try:  
        float(n)
        import unicodedata
        unicodedata.numeric(n)
        return True
    except (TypeError, ValueError):
        return False

def random_color():
    color = []
    while len(color) < 3:        
        color.append(random.choice(range(200)))
    return color

#如果讀不到資料補0避免keyerror
class Counter(dict):
    def __missing__(self,key): 
        return 0

class point():
    def __init__(self,userID:str):
        self.user = userID
    
    def check(self):
        jpt = Counter(json.load(open('point.json',mode='r',encoding='utf8')))
        pt = jpt[self.user] #json內資料格為str形式
        return pt
    
    def set(self,amount:int):
        jpt = Counter(json.load(open('point.json',mode='r',encoding='utf8')))
        with open('point.json',mode='w',encoding='utf8') as jfile:
            jpt[self.user] = amount
            json.dump(jpt,jfile,indent=4)
    
    def add(self,amount:int):
        jpt = Counter(json.load(open('point.json',mode='r',encoding='utf8')))
        with open('point.json',mode='w',encoding='utf8') as jfile:
            jpt[self.user] += amount
            json.dump(jpt,jfile,indent=4)

#arg:要檢測的內容(名稱#0000,id,mention...)
class find():
    async def user(ctx,arg):
        if arg == None:
            member = None
        else:
            try:
                member = await commands.MemberConverter().convert(ctx,arg)
            except commands.MemberNotFound:
                member = None
        return member

    async def channel(ctx,arg):
        if arg == None:
            channel = None
        else:
            try:
                channel = await commands.TextChannelConverter().convert(ctx,arg)
            except commands.ChannelNotFound:
                channel = None
        return channel

    async def role(ctx,arg):
        if arg == None:
            role = None
        else:
            try:
                role = await commands.RoleConverter().convert(ctx,arg)
            except commands.RoleNotFound:
                role = None
        return role

    async def user2(ctx,arg):
        try:
            user = await commands.UserConverter().convert(ctx,arg)
        except commands.UserNotFound:
            user = None
        return user

    async def emoji(ctx,arg):
        try:
            emoji = await commands.EmojiConverter().convert(ctx,arg)
        except commands.EmojiNotFound:
            emoji = None
        return emoji

    async def guild(ctx,arg):
        try:
            guild = await commands.GuildConverter().convert(ctx,arg)
        except commands.GuildNotFound:
            guild = None
        return guild

    async def role(ctx,arg):
        try:
            role = await commands.RoleConverter().convert(ctx,arg)
        except commands.RoleNotFound:
            role = None
        return role
class converter():
    def time(arg:str):
        #10s->1,0用str相加 s則轉換後用int相乘
        dict = {'s':1,'m':60,'h':3600}
        n=0
        m='0'
        for i in arg:
            try:
                int(i)
                m=m+i
            except ValueError:
                try:
                    m=int(m)
                    n=n+(m*dict[i])
                    m='0'
                except KeyError:
                    raise KeyError
        return n
        

def message_update(message):
    pass

