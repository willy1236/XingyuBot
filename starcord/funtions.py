import random
from discord.ext import commands

#(*args) 傳入多個參數->list
#(**kwargs) 傳入多個參數->dict
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

#jfile.seek(0)
#指標移至檔案開頭

#list
#s3=s1&s2 # 交集︰取兩個集合中，相同的資料
#s3=s1|s2 # 聯集︰取兩個合中的所有資料，但不重複取
#s3=s1-s2 # 差集︰從 s1 中，減去和 s2 重疊的部分
#s3=s1^s2 # 反交集︰取兩個集合中，重複的部分

#s=set("Hello") # 把字串中的字母折拆成集合
#dic={x:x*2 for x in [3,4,5]} # 從列表的資料中產生字典

#async -> await

def is_number(n):
    try:  
        float(n)
        import unicodedata
        unicodedata.numeric(n)
        return True
    except (TypeError, ValueError):
        return False

def random_color(max=255):
    if max > 255:
        raise ValueError("max must below 256")
    color = []
    for i in range(3):
        color.append(random.randint(0,max))
    return color

class Counter(dict):
    '''如果讀不到資料補0避免keyerror'''
    def __missing__(self,key):
        return 0

class find:
    '''arg=要檢測的內容(名稱#0000,id,mention...)'''
    @staticmethod
    async def user(ctx,arg:str):
        if arg:
            try:
                member = await commands.MemberConverter().convert(ctx,str(arg))
            except commands.MemberNotFound:
                member = None
        else:
            member = None
        return member

    @staticmethod
    async def channel(ctx,arg:str):
        if arg:
            try:
                channel = await commands.TextChannelConverter().convert(ctx,str(arg))
            except commands.ChannelNotFound:
                channel = None
        else:
            channel = None
        return channel

    @staticmethod
    async def role(ctx,arg:str):
        if arg:
            try:
                role = await commands.RoleConverter().convert(ctx,str(arg))
            except commands.RoleNotFound:
                role = None
        else:
            role = None
        return role

    @staticmethod
    async def user2(ctx,arg:str):
        try:
            user = await commands.UserConverter().convert(ctx,str(arg))
        except commands.UserNotFound:
            user = None
        return user

    @staticmethod
    async def emoji(ctx,arg:str):
        try:
            emoji = await commands.EmojiConverter().convert(ctx,str(arg))
        except commands.EmojiNotFound:
            emoji = None
        return emoji

    @staticmethod
    async def guild(ctx,arg:str):
        try:
            guild = await commands.GuildConverter().convert(ctx,str(arg))
        except commands.GuildNotFound:
            guild = None
        return guild

    @staticmethod
    async def role(ctx,arg:str):
        try:
            role = await commands.RoleConverter().convert(ctx,str(arg))
        except commands.RoleNotFound:
            role = None
        return role

class converter():
    def time(arg:str):
        '''10s->1,0用str相加 s則轉換後用int相乘'''
        dict = {'s':1,'m':60,'h':3600}
        n=0
        m=''
        for i in arg:
            try:
                int(i)
                m+=i
            except ValueError:
                try:
                    m=int(m)
                    n=n+(m*dict[i])
                    m=''
                except KeyError:
                    raise KeyError
        return n