import discord
from discord.errors import Forbidden, NotFound
from discord.ext import commands
import json ,random,asyncio

from library import Counter,find,converter,random_color,check_point
from core.classes import Cog_Extension


jdata = json.load(open('setting.json','r',encoding='utf8'))
role_ignore = [858566145156972554,901713612668813312,879587736128999454,613748153644220447,884082363859083305,613749564356427786,861812096777060352,889148839016169542,874628716385435719,858558233403719680,891644752666198047,896424834475638884,706794165094187038,619893837833306113,877934319249797120]

class command(Cog_Extension):
    @commands.command(help='原始的help指令')
    async def assist(self,ctx,arg='help'):
        await ctx.send_help(arg)

    @commands.command()
    async def info(self, ctx, arg='help'):
        if arg == 'help':
            await ctx.send("vpn類\nvpn | vpn列表\nvpn01 | vpn使用教學\n\n跨群聊天類\ncrass_chat | 跨群聊天列表\n\n共用類\nshare | 雲端共用資料夾資訊")

        elif arg == 'crass_chat':
            await ctx.send("crass_chat | 跨群聊天列表\n1.別人都在硬啦! 我偏偏要軟啦!!\n2.我就讚owob\n\n在跨群聊天頻道直接發送訊息即可\n想在自己群加入此系統，可找機器人擁有者")
        
        elif arg == 'vpn':
            await ctx.send("vpn | vpn列表\n名稱:willy1236_1 密:123456987 | willy的房間")
        elif arg == 'vpn01':
            await ctx.send("vpn01 | vpn安裝教學\n1.下載Radmin(vpn)\nhttps://www.radmin-vpn.com/tw/\n2.選擇 加入網路 並輸入名稱及密碼(可輸入!!info vpn查詢)\n3.記得 改名 讓大家知道你是誰\n\nIP為 xx.xxx.xx.xxx:ooooo\nx:開地圖的人的IP(VPN的IP)\no:公開至區網時會顯示")
        elif arg == 'share':
            await ctx.send("雲端共用資料夾 | 94共用啦\n可以在這裡下載或共用檔案\n請洽威立以取得雲端權限")
        
        else:
            raise commands.errors.ArgumentParsingError("info:參數錯誤")
            #await ctx.send('參數錯誤，請輸入!!info help取得幫助',delete_after=5)

    @commands.group(invoke_without_command=True)
    @commands.cooldown(rate=1,per=3)
    async def help(self,ctx):
        bot_name = self.bot.user.name

        embed = discord.Embed(title=bot_name, description="目前可使用的指令如下:", color=0xc4e9ff)
        embed.add_field(name="!!help <pt/game/set/role/bet>", value="系列指令", inline=False)
        embed.add_field(name="!!info <內容/help>", value="獲得相關資訊", inline=False)
        embed.add_field(name="!!sign", value="每日簽到(更多功能敬請期待)", inline=False)
        #embed.add_field(name="!!osu <player> <玩家名稱>", value="查詢Osu玩家(更多功能敬請期待)", inline=False)
        embed.add_field(name="!!find <id>", value="搜尋指定用戶", inline=False)
        embed.add_field(name="!!feedback <內容>", value="傳送訊息給機器人擁有者", inline=False)
        embed.add_field(name="!!lottery [次數]", value="抽獎", inline=False)
        embed.add_field(name="!!about", value="關於機器人的小資訊", inline=False)
        await ctx.send(embed=embed)

    @help.command()
    async def pt(self,ctx):
        embed = discord.Embed(description="Pt系列指令:", color=0xc4e9ff)
        embed.add_field(name="!!pt [用戶]", value="查詢Pt數", inline=False)
        embed.add_field(name="!!pt give <用戶> <數量>", value="將Pt轉給指定用戶", inline=False)
        await ctx.send(embed=embed)

    @help.command()
    async def game(self,ctx):
        embed = discord.Embed(description="Game系列指令:", color=0xc4e9ff)
        embed.add_field(name="!!game <set> <遊戲> <資料>", value="設定你在資料庫內的遊戲名稱", inline=False)
        embed.add_field(name="!!game <find> <用戶>", value="查詢用戶在資料庫內的遊戲名稱(未開放)", inline=False)
        embed.add_field(name="!!lol <player> <玩家名稱>", value="查詢LOL戰績(更多功能敬請期待)", inline=False)
        await ctx.send(embed=embed)

    @help.command()
    async def set(self,ctx):
        embed = discord.Embed(description="Set系列指令:", color=0xc4e9ff)
        embed.add_field(name="!!set <crass_chat> [頻道]", value="設定跨群聊天頻道", inline=False)
        embed.add_field(name="!!set <all_anno> [頻道]", value="設定全群公告頻道", inline=False)
        await ctx.send(embed=embed)

    @help.command()
    async def role(self,ctx):
        embed = discord.Embed(description="Role系列指令:", color=0xc4e9ff)
        embed.add_field(name="!!role <用戶>", value="取得用戶的身分組數量(可批量輸入多個用戶)", inline=False)
        embed.add_field(name="!!role add <名稱> [用戶]", value="取得用戶的身分組數量(可批量輸入多個用戶)", inline=False)
        embed.add_field(name="!!role nick <名稱/顏色代碼>", value="更改稱號(顏色請輸入HEX格式)", inline=False)
        await ctx.send(embed=embed)

    @help.command()
    async def bet(self,ctx):
        embed = discord.Embed(description="Bet系列指令:", color=0xc4e9ff)
        embed.add_field(name="!!bet <賭盤ID> <blue/pink> <下注金額>", value="賭盤下注", inline=False)
        embed.add_field(name="!!bet create <賭盤標題> <粉紅幫標題> <藍藍幫標題> <下注時間>", value="創建賭盤(時間格式為'10s''1m20s'等，不可超過600s)", inline=False)
        embed.add_field(name="!!bet end <blue/pink>",value="結算賭盤",inline=False)
        await ctx.send(embed=embed)
    
    @help.command()
    @commands.is_owner()
    async def owner(self,ctx):
        bot_name = self.bot.user.name

        embed = discord.Embed(title=bot_name, description="目前可使用的指令如下(onwer):", color=0xc4e9ff)
        embed.add_field(name="!!send <頻道ID/用戶ID/0> <內容>", value="發送指定訊息", inline=False)
        embed.add_field(name="!!anno <內容>", value="對所有伺服器進行公告", inline=False)
        embed.add_field(name="!!edit <訊息ID> <新訊息>", value="編輯訊息", inline=False)
        embed.add_field(name="!!reaction <訊息ID> <add/remove> <表情/表情ID>", value="添加/移除反應", inline=False)
        embed.add_field(name="!!ptset <用戶ID> <+/-/set> <數量>", value="更改指定用戶Pt數", inline=False)
        embed.add_field(name="!!reset", value="簽到重置", inline=False)
        embed.add_field(name="!!role ignore", value="取得計算身分組時扣掉的身分組", inline=False)
        await ctx.send(embed=embed)

    @help.command()
    async def admin(self,ctx):
        bot_name = self.bot.user.name

        embed = discord.Embed(title=bot_name, description="目前可使用的指令如下(admin):", color=0xc4e9ff)
        embed.add_field(name="!!clean <數字>", value="清除訊息(需求管理訊息)", inline=False)
        await ctx.send(embed=embed)

    @commands.command()
    async def find(self,ctx,id:int):
        member = ctx.guild.get_member(id)
        if member != None:
            embed = discord.Embed(title=f'{member.name}#{member.discriminator}', description="ID:用戶(伺服器成員)", color=0xc4e9ff)
            embed.add_field(name="暱稱", value=member.nick, inline=False)
            embed.add_field(name="是否為機器人", value=member.bot, inline=False)
            embed.add_field(name="最高身分組", value=member.top_role.mention, inline=True)
            embed.add_field(name="目前狀態", value=member.status, inline=True)
            embed.add_field(name="帳號創建日期", value=member.created_at, inline=False)
            embed.set_thumbnail(url=member.avatar_url)
            await ctx.send(embed=embed)
            return
        try:
            user = await self.bot.fetch_user(id)
        except NotFound:
            user = None
        try:
            channel = await self.bot.fetch_channel(id)
        except (NotFound,Forbidden):
            channel = None
        try:
            guild = await self.bot.fetch_guild(id)
        except (NotFound,Forbidden):
            guild = None
            
        if user != None:
            embed = discord.Embed(title=f'{user.name}#{user.discriminator}', description="ID:用戶", color=0xc4e9ff)
            embed.add_field(name="是否為機器人", value=user.bot, inline=False)
            embed.add_field(name="是否為Discord官方", value=user.system, inline=False)
            embed.add_field(name="帳號創建日期", value=user.created_at, inline=False)
            embed.set_thumbnail(url=user.avatar_url)
        elif channel != None:
            embed = discord.Embed(title=channel.name, description="ID:頻道", color=0xc4e9ff)
            embed.add_field(name="所屬類別", value=channel.category, inline=False)
            embed.add_field(name="所屬公會", value=channel.guild, inline=False)
            embed.add_field(name="創建時間", value=channel.created_at, inline=False)
        elif guild != None:
            embed = discord.Embed(title=guild.name, description="ID:公會", color=0xc4e9ff)
            embed.add_field(name="公會擁有者", value=guild.owner, inline=False)
            embed.add_field(name="創建時間", value=guild.created_at, inline=False)
            embed.add_field(name="驗證等級", value=guild.verification_level, inline=False)
            embed.add_field(name="成員數", value=len(guild.members), inline=False)
            embed.add_field(name="文字頻道數", value=len(guild.text_channels), inline=False)
            embed.add_field(name="語音頻道數", value=len(guild.voice_channels), inline=False)
            embed.set_footer(text='數字可能因權限不足而有少算，敬請特別注意')
            embed.set_thumbnail(url=guild.icon_url)
        else:
            await ctx.send('無法辨認此ID',delete_after=5)
            return
        await ctx.send(embed=embed)

    @commands.command()
    @commands.cooldown(rate=1,per=10)
    async def feedback(self,ctx,*,msg):
        await ctx.message.delete()
        user = ctx.author
        guild = ctx.guild
        channel = ctx.channel
        feedback_channel = self.bot.get_channel(jdata['feedback_channel'])
        embed = discord.Embed(color=0xc4e9ff)
        embed.add_field(name='廣播電台 | 回饋訊息', value=msg, inline=False)
        embed.set_author(name=f'{user}\n({user.id})',icon_url=f'{user.avatar_url}')
        embed.set_footer(text=f'來自: {guild}, {channel}')
        await feedback_channel.send(embed=embed)
        await ctx.send('訊息已發送',delete_after=5)

    @commands.group(invoke_without_command=True)
    async def role(self,ctx,*user_list):
        i = 0
        text = '身分組計算結果:\n'
        while i < len(user_list):
            user = await find.user(ctx,user_list[i])
            if user != None:
                l = 0
                ignore_count = 0
                role_list = user.roles
                while l < len(role_list):
                    if role_list[l].id in role_ignore:
                        role_list.remove(role_list[l])
                        ignore_count += 1
                    else:
                        l += 1
                role_count = len(role_list)-1
                
                if ignore_count > 0:
                    text = text + f'\n{user.name}扣除{ignore_count}個後擁有{role_count}個身分組'
                else:
                    text = text + f'\n{user.name}擁有{role_count}個身分組'
            i += 1
        await ctx.send(text)

    @role.command()
    async def add(self,ctx,name,user=None):
        user = await find.user(ctx,user)
        permission = discord.Permissions.none()
        #color = discord.Colour.random()
        r,g,b=random_color()
        color = discord.Colour.from_rgb(r,g,b)
        new_role = await ctx.guild.create_role(name=name,permissions=permission,color=color)
        if user != None:
            await user.add_roles(new_role)
        await ctx.message.add_reaction('✅')

    @role.command()
    @commands.is_owner()
    async def ignore(self,ctx,role='None'):
        if role != 'None':
            role = await find.role(ctx,role)

        if ctx.guild.id == 613747262291443742:
            if role == 'None':
                text = '刪除清單:\n'
                for i in role_ignore:
                    text = text + ctx.guild.get_role(i).name + ','
                await ctx.send(text)

    @role.command()
    async def nick(self, ctx,arg):
        user = ctx.author
        role = user.roles[-1]
        if role.name.startswith('稱號 | '):
            if arg.startswith('#'):
                await role.edit(colour=arg,reason='稱號:顏色改變')
            else:
                await role.edit(name=f'稱號 | {arg}',reason='稱號:名稱改變')
            await ctx.send('稱號更改已完成')
        else:
            await ctx.send('錯誤:你沒有稱號可更改',delete_after=5)
        
    @commands.command()
    async def about(self,ctx):
        await ctx.send(f'目前我已服務了{len(self.bot.guilds)}個伺服器\n共包含了{len(self.bot.users)}位成員')
        
    @commands.command()
    @commands.cooldown(rate=5,per=1)
    async def lottery(self,ctx,times:int=1):
        if times > 1000:
            await ctx.send('太多了拉，請填入少一點的數字')
            return
        i=0
        result={'six':0,'five':0,'four':0,'three':0}
        user_id = str(ctx.author.id)
        six_list = []
        six_list_100 = []
        guaranteed = 300
        jloot = Counter(json.load(open('lottery.json',mode='r',encoding='utf8')))
            
        while i < times:
            choice =  random.randint(1,100)
            if choice == 1 or jloot[user_id] >= guaranteed-1:
                result["six"] =result["six"]+1
                if jloot[user_id] >= guaranteed-1:
                    six_list_100.append(i+1)
                else:
                    six_list.append(i+1)
                jloot[user_id] = 0
            elif choice >= 2 and choice <= 11:
                result["five"]=result["five"]+1
                jloot[user_id] = jloot[user_id]+1
            elif choice >= 12 and choice <= 41:
                result["four"]=result["four"]+1
                jloot[user_id] = jloot[user_id]+1
            else:
                result["three"]=result["three"]+1
                jloot[user_id] = jloot[user_id]+1
            i =i+1
        
        with open('lottery.json',mode='w',encoding='utf8') as jfile:
            json.dump(jloot,jfile,indent=4)
        text = f"抽卡結果:\n六星:{result['six']} 五星:{result['five']} 四星:{result['four']} 三星:{result['three']}\n未抽得六星次數:{jloot[user_id]}"
        if len(six_list) > 0:
            text = text + f'\n六星出現:{six_list}'
        if len(six_list_100) > 0:
            text = text + f'\n保底:{six_list_100}'
        await ctx.send(text)
        
    
    @commands.group(invoke_without_command=True)
    async def bet(self,ctx,id,choice,money:int):
        bet_data = Counter(json.load(open('bet.json',mode='r',encoding='utf8')))
        money_now = check_point(ctx.author.id)
        if id not in bet_data:
            await ctx.send('編號錯誤:沒有此編號的賭盤喔')
        elif bet_data[id]['Ison'] == 0:
            await ctx.send('錯誤:此賭盤已經關閉了喔')
        elif choice not in ['pink','blue']:
            await ctx.send('選擇錯誤:我不知道你要選擇什麼')
        elif money <= 0:
            await ctx.send('金額錯誤:無法輸入小於1的數字')
        elif money_now < money:
            await ctx.send('金額錯誤:你沒有那麼多點數')
        else:
            jpt = Counter(json.load(open('point.json',mode='r',encoding='utf8')))
            jpt[str(ctx.author.id)] -= money
            with open("point.json",'w',encoding='utf8') as jfile:
                json.dump(jpt,jfile,indent=4)
            bet_data[id][choice]['member'][str(ctx.author.id)] += money
            with open("bet.json",'w',encoding='utf8') as jfile:
                json.dump(bet_data,jfile,indent=4)
            
            await ctx.send('下注完成!')
    
    @bet.command()
    async def create(self,ctx,title,pink,blue,time):
        bet_data = json.load(open("bet.json",'r',encoding='utf8'))
        id = str(ctx.author.id)
        sec = converter.time(time)
        if id in bet_data:
            await ctx.send('錯誤:你已經創建一個賭盤了喔')
            return
        elif sec > 600:
            await ctx.send('錯誤:時間太長了喔')
            return
    
        with open("bet.json",'w',encoding='utf8') as jfile:
            data = {}
            data['title'] = title
            data['IsOn'] = 1
            data['blue'] = {}
            data['blue']['title'] = blue
            data['blue']['member'] = {}
            data['pink'] = {}
            data['pink']['title'] = pink
            data['pink']['member'] = {}
            bet_data[id] = data
            jfile.seek(0)
            json.dump(bet_data,jfile,indent=4)
        
        embed = discord.Embed(title='賭盤', description=f'編號: {id}', color=0xc4e9ff)
        embed.add_field(name='賭盤內容', value=title, inline=False)
        embed.add_field(name="粉紅幫", value=pink, inline=False)
        embed.add_field(name="藍藍幫", value=blue, inline=False)
        await ctx.send(embed=embed)
        await asyncio.sleep(delay=sec)
        await ctx.send(f'編號:{id}\n下注時間結束')
        with open("bet.json",'w',encoding='utf8') as jfile:
            bet_data[id]['IsOn'] = 0
            json.dump(bet_data,jfile,indent=4)
        
    @bet.command()
    async def end(self,ctx,end):
        #錯誤檢測
        if end not in ['blue','pink']:
            await ctx.send('結果錯誤:我不知道到底是誰獲勝了呢')
            return
        id = str(ctx.author.id)
        bet_data = json.load(open('bet.json',mode='r',encoding='utf8'))
        #計算雙方總點數
        pink_total = 0
        for i in bet_data[id]['pink']['member']:
            pink_total += bet_data[id]['pink']['member'][i]
        blue_total = 0
        for i in bet_data[id]['blue']['member']:
            blue_total += bet_data[id]['blue']['member'][i]
        #獲勝者設定
        if end == 'pink':
            winner = bet_data[id]['pink']['member']
        else:
            winner = bet_data[id]['blue']['member']
        #前置準備
        if pink_total > blue_total:
            mag = pink_total / blue_total
        else:
            mag = blue_total / pink_total
        #點數計算
        point = Counter(json.load(open('point.json',mode='r',encoding='utf8')))
        for i in winner:
            pt1 = winner[i] * (mag+1)
            point[i] += int(pt1)
        #更新資料庫
        with open('point.json','w',encoding='utf8') as jfile:
            json.dump(point,jfile,indent=4)
        del bet_data[id]
        with open("bet.json",'w',encoding='utf8') as jfile:
            json.dump(bet_data,jfile,indent=4)
        #結果公布
        if end == 'pink':
            await ctx.send(f'編號:{id}\n恭喜粉紅幫獲勝!')
        else:
            await ctx.send(f'編號:{id}\n恭喜藍藍幫獲勝!')
            
def setup(bot):
    bot.add_cog(command(bot))