import random
from discord.ext import commands
from core.classes import Cog_Extension
from BotLib.database import Database
from BotLib.basic import BotEmbed

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

picdata = Database().picdata
jdata = Database().jdata

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
        raise ValueError("max must below 255")
    color = []
    while len(color) < 3:        
        color.append(random.choice(range(max)))
    return color

class Counter(dict):
    '''如果讀不到資料補0避免keyerror'''
    def __missing__(self,key): 
        return 0

class find(Cog_Extension):
    '''arg=要檢測的內容(名稱#0000,id,mention...)'''
    async def user(ctx,arg:str):
        if arg:
            try:
                member = await commands.MemberConverter().convert(ctx,str(arg))
            except commands.MemberNotFound:
                member = None
        else:
            member = None
        return member

    async def channel(ctx,arg:str):
        if arg:
            try:
                channel = await commands.TextChannelConverter().convert(ctx,str(arg))
            except commands.ChannelNotFound:
                channel = None
        else:
            channel = None
        return channel

    async def role(ctx,arg:str):
        if arg:
            try:
                role = await commands.RoleConverter().convert(ctx,str(arg))
            except commands.RoleNotFound:
                role = None
        else:
            role = None
        return role

    async def user2(ctx,arg:str):
        try:
            user = await commands.UserConverter().convert(ctx,str(arg))
        except commands.UserNotFound:
            user = None
        return user

    async def emoji(ctx,arg:str):
        try:
            emoji = await commands.EmojiConverter().convert(ctx,str(arg))
        except commands.EmojiNotFound:
            emoji = None
        return emoji

    async def guild(ctx,arg:str):
        try:
            guild = await commands.GuildConverter().convert(ctx,str(arg))
        except commands.GuildNotFound:
            guild = None
        return guild

    async def role(ctx,arg:str):
        try:
            role = await commands.RoleConverter().convert(ctx,str(arg))
        except commands.RoleNotFound:
            role = None
        return role

class BRS():
    async def error(self,ctx,error:str):
        jdata = Database().jdata
        report_channel = self.bot.get_channel(jdata['report_channel'])
        embed=BotEmbed.simple()
        embed.set_author(name="BRS | 錯誤回報")
        embed.add_field(name='錯誤指令', value=f'```py\n{error}```', inline=True)
        embed.add_field(name='使用指令', value=f'```{ctx.message.content}```', inline=False)
        embed.add_field(name='使用者', value=f"{ctx.author}\n{ctx.author.id}", inline=False)
        embed.add_field(name='發生頻道', value=f'{ctx.channel}\n{ctx.channel.id}', inline=True)
        embed.add_field(name='發生群組', value=f'{ctx.guild}\n{ctx.guild.id}', inline=True)
        await report_channel.send(embed=embed)
    
    async def scam(self,msg):
        jdata = Database().jdata
        scam_channel = self.bot.get_channel(jdata['scam_channel'])
        embed=BotEmbed.simple()
        embed.set_author(name="BRS | 詐騙回報")
        embed.add_field(name='詐騙訊息', value=msg.content, inline=True)
        embed.add_field(name='發送者', value=f"{msg.author}\n{msg.author.id}", inline=False)
        embed.add_field(name='發生頻道', value=f'{msg.channel}\n{msg.channel.id}', inline=True)
        embed.add_field(name='發生群組', value=f'{msg.guild}\n{msg.guild.id}', inline=True)
        await scam_channel.send(embed=embed)

    async def feedback(self,ctx,msg):
        jdata = Database().jdata
        feedback_channel = self.bot.get_channel(jdata['feedback_channel'])
        embed=BotEmbed.simple()
        embed.set_author(name="BRS | 回饋訊息")
        embed.add_field(name='訊息內容', value=msg, inline=True)
        embed.add_field(name='發送者', value=f"{ctx.author}\n{ctx.author.id}", inline=False)
        embed.add_field(name='來源頻道', value=f'{ctx.channel}\n{ctx.channel.id}', inline=True)
        embed.add_field(name='來源群組', value=f'{ctx.guild}\n{ctx.guild.id}', inline=True)
        await feedback_channel.send(embed=embed)

    async def dm(self,msg):
        jdata = Database().jdata
        dm_channel = self.bot.get_channel(jdata['dm_channel'])
        embed=BotEmbed.simple()
        embed.set_author(name="BRS | 私人訊息")
        embed.add_field(name='訊息內容', value=msg.content, inline=True)
        embed.add_field(name='發送者', value=f"{msg.author}\n{msg.author.id}", inline=False)
        await dm_channel.send(embed=embed)

    async def mentioned(self,msg):
        jdata = Database().jdata
        dm_channel = self.bot.get_channel(jdata['mentioned_channel'])
        embed=BotEmbed.simple()
        embed.set_author(name="BRS | 提及訊息")
        embed.add_field(name='訊息內容', value=msg.content, inline=True)
        embed.add_field(name='發送者', value=f"{msg.author}\n{msg.author.id}", inline=False)
        embed.add_field(name='來源頻道', value=f'{msg.channel}\n{msg.channel.id}', inline=True)
        embed.add_field(name='來源群組', value=f'{msg.guild}\n{msg.guild.id}', inline=True)
        await dm_channel.send(embed=embed)
    
    async def mention_everyone(self,msg):
        jdata = Database().jdata
        dm_channel = self.bot.get_channel(jdata['mention_everyone_channel'])
        embed=BotEmbed.simple()
        embed.set_author(name="BRS | 提及所有人訊息")
        embed.add_field(name='訊息內容', value=msg.content, inline=True)
        embed.add_field(name='發送者', value=f"{msg.author}\n{msg.author.id}", inline=False)
        embed.add_field(name='來源頻道', value=f'{msg.channel}\n{msg.channel.id}', inline=True)
        embed.add_field(name='來源群組', value=f'{msg.guild}\n{msg.guild.id}', inline=True)
        await dm_channel.send(embed=embed)

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