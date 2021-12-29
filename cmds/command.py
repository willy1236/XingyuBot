import discord
from discord.errors import Forbidden, NotFound
from discord.ext import commands
import json ,random,asyncio

from library import Counter,find_user ,find_channel , find_role,converter
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
            await ctx.send('參數錯誤，請輸入!!info help取得幫助',delete_after=5)

    @commands.group(invoke_without_command=True)
    @commands.cooldown(rate=1,per=3)
    async def help(self,ctx):
        bot_name = self.bot.user.name

        embed = discord.Embed(title=bot_name, description="目前可使用的指令如下:", color=0xc4e9ff)
        embed.add_field(name="!!help <pt/game/set/role>", value="系列指令", inline=False)
        embed.add_field(name="!!info <內容/help>", value="獲得相關資訊", inline=False)
        embed.add_field(name="!!sign", value="每日簽到(更多功能敬請期待)", inline=False)
        #embed.add_field(name="!!osu <player> <玩家名稱>", value="查詢Osu玩家(更多功能敬請期待)", inline=False)
        embed.add_field(name="!!find <id>", value="搜尋指定用戶", inline=False)
        embed.add_field(name="!!feedback <內容>", value="傳送訊息給機器人擁有者", inline=False)
        embed.add_field(name="!!lottery [次數]", value="抽獎", inline=False)
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
        embed = discord.Embed(description="Game系列指令:", color=0xc4e9ff)
        embed.add_field(name="!!set <crass_chat> [頻道]", value="設定跨群聊天頻道", inline=False)
        embed.add_field(name="!!set <all_anno> [頻道]", value="設定全群公告頻道", inline=False)
        await ctx.send(embed=embed)

    @help.command()
    async def role(self,ctx):
        embed = discord.Embed(description="Game系列指令:", color=0xc4e9ff)
        embed.add_field(name="!!role <用戶>", value="取得用戶的身分組數量(可批量輸入多個用戶)", inline=False)
        embed.add_field(name="!!role add <名稱> [用戶]", value="取得用戶的身分組數量(可批量輸入多個用戶)", inline=False)
        embed.add_field(name="!!role nick <名稱/顏色代碼>", value="更改稱號(顏色請輸入HEX格式)", inline=False)

    @help.command()
    @commands.is_owner()
    async def owner(self,ctx):
        bot_name = self.bot.user.name

        embed = discord.Embed(title=bot_name, description="目前可使用的指令如下(onwer):", color=0xc4e9ff)
        embed.add_field(name="!!send <頻道ID/用戶ID/0> <內容>", value="發送指定訊息", inline=False)
        embed.add_field(name="!!all_anno <內容>", value="對所有伺服器進行公告", inline=False)
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
            user = await find_user(ctx,user_list[i])
            if user != None:
                l = 0
                ignore_count = 0
                role_list = user.roles
                while l < len(role_list):
                    if role_list[l].id in role_ignore:
                        role_list.remove(role_list[l])
                        ignore_count = ignore_count +1
                    else:
                        l = l+1
                role_count = len(role_list)-1
                
                if ignore_count > 0:
                    text = text + f'\n{user.name}扣除{ignore_count}個後擁有{role_count}個身分組'
                else:
                    text = text + f'\n{user.name}擁有{role_count}個身分組'
            i = i + 1
        await ctx.send(text)

    @role.command()
    async def add(self,ctx,name,user=None):
        user = await find_user(ctx,user)
        permission = discord.Permissions.none()
        new_role = await ctx.guild.create_role(name=name,permissions=permission)
        if user != None:
            await user.add_roles(new_role)
            await ctx.message.add_reaction('✅')

    @role.command()
    @commands.is_owner()
    async def ignore(self,ctx,role='None'):
        if role != 'None':
            role = await find_role(ctx,role)

        if ctx.guild.id == 613747262291443742:
            if role == 'None':
                text = '刪除清單:\n'
                for i in role_ignore:
                    text = text + ctx.guild.get_role(i).name + ','
                await ctx.send(text)
            # elif role.id in role_ignore and role != None:
            #     role_ignore.remove(role.id)
            #     await ctx.send(f'{role.name} 刪除完成',delete_after=5)
            # elif role != None:
            #     role_ignore.append(role.id)
            #     await ctx.send(f'{role.name} 刪除完成',delete_after=5)

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
                


    @commands.group(invoke_without_command=True)
    async def set(self,ctx):
        pass

    @set.command()
    async def crass_chat(self,ctx,channel='remove'):
        if channel != 'remove':
            channel = await find_channel(ctx,channel)
        channels = ctx.guild.channels
        have = 0
        for i in channels:
            if i.id in jdata['crass_chat']:
                have = have + 1
        
        if channel == 'remove':
            with open('setting.json','w+',encoding='utf8') as f:
                for i in channels:
                    if i.id in jdata['crass_chat']:
                        jdata['crass_chat'].remove(i.id)
                json.dump(jdata, f,indent=4)
                await ctx.send(f'設定完成，已移除跨群聊天頻道')

        elif channel != None and have == 0:
            with open('setting.json','w+',encoding='utf8') as f:
                jdata['crass_chat'].append(channel.id)
                json.dump(jdata, f,indent=4)
                await ctx.send(f'設定完成，已將跨群聊天頻道設為{channel.mention}')

        elif channel != None and have > 0:
            with open('setting.json','w+',encoding='utf8') as f:
                for i in channels:
                    if i.id in jdata['crass_chat']:
                        jdata['crass_chat'].remove(i.id)
                jdata['crass_chat'].append(channel.id)
                json.dump(jdata, f,indent=4)
                await ctx.send(f'設定完成，已將跨群聊天頻道更新為{channel.mention}')

    @set.command()
    async def all_anno(self,ctx,channel='remove'):
        if channel != 'remove':
            channel = await find_channel(ctx,channel)
        channels = ctx.guild.channels
        have = 0
        for i in channels:
            if i.id in jdata['all_anno']:
                have = have + 1
        
        if channel == 'remove':
            with open('setting.json','w+',encoding='utf8') as f:
                for i in channels:
                    if i.id in jdata['all_anno']:
                        jdata['all_anno'].remove(i.id)
                json.dump(jdata, f,indent=4)
                await ctx.send(f'設定完成，已移除全群公告頻道')

        elif channel != None and have == 0:
            with open('setting.json','w+',encoding='utf8') as f:
                jdata['all_anno'].append(channel.id)
                json.dump(jdata, f,indent=4)
                await ctx.send(f'設定完成，已將全群公告頻道設為{channel.mention}')

        elif channel != None and have > 0:
            with open('setting.json','w+',encoding='utf8') as f:
                for i in channels:
                    if i.id in jdata['all_anno']:
                        jdata['all_anno'].remove(i.id)
                jdata['all_anno'].append(channel.id)
                json.dump(jdata, f,indent=4)
                await ctx.send(f'設定完成，已將全群公告頻道更新為{channel.mention}')
        

    
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
        guaranteed = 100
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
        

    @commands.command()
    async def test(self, ctx,arg):
        #print(self.bot.command(name='lottery').__call__)
        #self.bot.command(name='lottery')
        text = converter.time(arg)
        await ctx.send(text)

    
    # @commands.command(enabled=False)
    # async def test(self,ctx,user=None):
    #     user = await find_user(ctx,user)
    #     await ctx.send(f"{user or '沒有找到用戶'}")
    
    @commands.group()
    async def bet(self,ctx,id,choice,money):
        pass
    
    async def create(self, ctx,title,pink,blue,time):
        sec = converter.time(time)
        id = str(ctx.author.id)
        embed = discord.Embed(title='賭盤', description=f'編號: {id}', color=0xc4e9ff)
        embed.add_field(name='賭盤內容', value=title, inline=False)
        embed.add_field(name="粉紅幫", value=pink, inline=False)
        embed.add_field(name="藍藍幫", value=blue, inline=False)
        await ctx.send(embed=embed)
        await asyncio.sleep(delay=sec)
        await ctx.send('下注時間結束')
        

        
        

def setup(bot):
    bot.add_cog(command(bot))