import discord
from discord.errors import Forbidden, NotFound
from discord.ext import commands
import json ,random,asyncio

from library import Counter,find,converter,random_color,BRS
from core.classes import Cog_Extension
from BotLib.user import *
from BotLib.basic import Database

jdata = json.load(open('setting.json','r',encoding='utf8'))
picdata = json.load(open('database/picture.json',mode='r',encoding='utf8'))
rsdata = Counter(json.load(open('database/role_save.json',mode='r',encoding='utf8')))

class command(Cog_Extension):
    @commands.command()
    async def find(self,ctx,id):
        success = 0
        member = await find.user(ctx,id)
        if member != None:
            embed = BRS.simple(title=f'{member.name}#{member.discriminator}', description="ID:用戶(伺服器成員)")
            embed.add_field(name="暱稱", value=member.nick, inline=False)
            embed.add_field(name="是否為機器人", value=member.bot, inline=False)
            embed.add_field(name="最高身分組", value=member.top_role.mention, inline=True)
            embed.add_field(name="目前狀態", value=member.status, inline=True)
            embed.add_field(name="是否為Discord官方", value=member.system, inline=False)
            embed.add_field(name="帳號創建日期", value=member.created_at, inline=False)
            embed.set_thumbnail(url=member.display_avatar.url)
            success += 1

        user = await find.user2(ctx,id)
        if user != None and member == None:
            embed = BRS.simple(title=f'{user.name}#{user.discriminator}', description="ID:用戶")
            embed.add_field(name="是否為機器人", value=user.bot, inline=False)
            embed.add_field(name="是否為Discord官方", value=user.system, inline=False)
            embed.add_field(name="帳號創建日期", value=user.created_at, inline=False)
            embed.set_thumbnail(url=user.display_avatar.url)
            success += 1

        channel = await find.channel(ctx,id)
        if channel != None:
            embed = BRS.simple(title=channel.name, description="ID:頻道")
            embed.add_field(name="所屬類別", value=channel.category, inline=False)
            embed.add_field(name="所屬公會", value=channel.guild, inline=False)
            embed.add_field(name="創建時間", value=channel.created_at, inline=False)
            success += 1
        
        guild = await find.guild(ctx,id)
        if guild != None:
            embed = BRS.simple(title=guild.name, description="ID:公會")
            embed.add_field(name="公會擁有者", value=guild.owner, inline=False)
            embed.add_field(name="創建時間", value=guild.created_at, inline=False)
            embed.add_field(name="驗證等級", value=guild.verification_level, inline=False)
            embed.add_field(name="成員數", value=len(guild.members), inline=False)
            embed.add_field(name="文字頻道數", value=len(guild.text_channels), inline=False)
            embed.add_field(name="語音頻道數", value=len(guild.voice_channels), inline=False)
            embed.set_footer(text='數字可能因權限不足而有少算，敬請特別注意')
            embed.set_thumbnail(url=guild.icon.url)
            success += 1
            
        if success == 1:
            await ctx.send(embed=embed)
        elif success > 1:
            await BRS.error(self,ctx,f'find:id重複(出現{success}次)')
            await ctx.send('出現錯誤，已自動向機器人擁有者回報')
        else:
            await ctx.send('無法辨認此ID',delete_after=5)
            

    @commands.command()
    @commands.cooldown(rate=1,per=10)
    async def feedback(self,ctx,*,msg):
        send_msg = await ctx.send('請稍後...',delete_after=10)
        await BRS.feedback(self,ctx,msg)
        await ctx.message.delete()
        await send_msg.edit('訊息已發送',delete_after=5)


    @commands.group(invoke_without_command=True)
    async def role(self,ctx,*user_list):
        if 'default' in user_list:
            user_list = (419131103836635136,528935362199027716,465831362168094730,539405949681795073,723435216244572160,490136735557222402)
        embed=BRS.simple()
        embed.set_author(name="身分組計算結果")
        rsdata = Counter(json.load(open('database/role_save.json',mode='r',encoding='utf8')))
        for i in user_list:
            user = await find.user(ctx,i)
            if user != None:
                role_count = len(rsdata[str(user.id)])

                embed.add_field(name=user.name, value=f"{role_count}", inline=False)
                # if ignore_count > 0:
                #     text = text + f'\n{user.name}扣除{ignore_count}個後擁有{role_count}個身分組'
                # else:
                #     text = text + f'\n{user.name}擁有{role_count}個身分組'
        await ctx.send(embed=embed)


    @role.command()
    @commands.cooldown(rate=1,per=5)
    async def add(self,ctx,name,*user_list):
        permission = discord.Permissions.none()
        #color = discord.Colour.random()
        r,g,b=random_color()
        color = discord.Colour.from_rgb(r,g,b)
        new_role = await ctx.guild.create_role(name=name,permissions=permission,color=color)
        if user_list != []:
            for user in user_list:
                user = await find.user(ctx,user)
                if user != None:
                    await user.add_roles(new_role,reason='指令:加身分組')
            await ctx.message.add_reaction('✔️')
        await ctx.message.add_reaction('✅')


    @role.command()
    @commands.is_owner()
    async def save(self,ctx,user):
        def save_role(user):
            dict = rsdata
            roledata = dict[str(user.id)] or {}
            for role in user.roles:
                if role.id == 877934319249797120:
                    break
                if role.name == '@everyone':
                    continue
                if str(role.id) not in roledata:
                    print(f'新增:{role.name}')
                roledata[str(role.id)] = [role.name,role.created_at.strftime('%Y%m%d')]
                dict[str(user.id)] = roledata
            with open('database/role_save.json',mode='w',encoding='utf8') as jfile:
                json.dump(dict,jfile,indent=4)
        
        guild = self.bot.get_guild(jdata['guild']['001'])
        add_role = guild.get_role(877934319249797120)
        if user == 'all':
            for user in add_role.members:
                save_role(user)
            await ctx.message.add_reaction('✅')
        else:
            user = await find.user(ctx,user)
            if user != None and add_role in user.roles:
                save_role(user)
                await ctx.message.add_reaction('✅')
            elif add_role not in user.roles:
                ctx.send('錯誤:此用戶沒有"加身分組"')


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
    @commands.cooldown(rate=1,per=2)
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
        jloot = Counter(json.load(open('database/lottery.json',mode='r',encoding='utf8')))
            
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
        
        with open('database/lottery.json',mode='w',encoding='utf8') as jfile:
            json.dump(jloot,jfile,indent=4)
        embed=BRS.lottery()
        embed.add_field(name='抽卡結果', value=f"六星:{result['six']} 五星:{result['five']} 四星:{result['four']} 三星:{result['three']}", inline=False)
        #text = f"抽卡結果:\n六星:{result['six']} 五星:{result['five']} 四星:{result['four']} 三星:{result['three']}\n未抽得六星次數:{jloot[user_id]}"
        embed.add_field(name='保底累積', value=jloot[user_id], inline=False)
        if len(six_list) > 0:
            embed.add_field(name='六星出現', value=six_list, inline=False)
            #text = text + f'\n六星出現:{six_list}'
        if len(six_list_100) > 0:
            embed.add_field(name='保底', value=six_list_100, inline=False)
            #text = text + f'\n保底:{six_list_100}'
        await ctx.send(embed=embed)


    @commands.group(invoke_without_command=True)
    async def bet(self,ctx,id,choice,money:int):
        bet_data = Counter(json.load(open('database/bet.json',mode='r',encoding='utf8')))
        money_now = Point(ctx.author.id).pt
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
            Point(ctx.author.id).add(money*-1)
            bet_data[id][choice]['member'][str(ctx.author.id)] += money
            with open("database/bet.json",'w',encoding='utf8') as jfile:
                json.dump(bet_data,jfile,indent=4)
            
            await ctx.send('下注完成!')


    @bet.command()
    async def create(self,ctx,title,pink,blue,time):
        bet_data = json.load(open("database/bet.json",'r',encoding='utf8'))
        id = str(ctx.author.id)
        sec = converter.time(time)
        if id in bet_data:
            await ctx.send('錯誤:你已經創建一個賭盤了喔')
            return
        elif sec > 600:
            await ctx.send('錯誤:時間太長了喔')
            return
    
        with open("database/bet.json",'w',encoding='utf8') as jfile:
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
        
        embed = BRS.simple(title='賭盤', description=f'編號: {id}')
        embed.add_field(name='賭盤內容', value=title, inline=False)
        embed.add_field(name="粉紅幫", value=pink, inline=False)
        embed.add_field(name="藍藍幫", value=blue, inline=False)
        await ctx.send(embed=embed)
        await asyncio.sleep(delay=sec)
        await ctx.send(f'編號:{id}\n下注時間結束')
        with open("database/bet.json",'w',encoding='utf8') as jfile:
            bet_data[id]['IsOn'] = 0
            json.dump(bet_data,jfile,indent=4)


    @bet.command()
    async def end(self,ctx,end):
        #錯誤檢測
        if end not in ['blue','pink']:
            await ctx.send('結果錯誤:我不知道到底是誰獲勝了呢')
            return
        id = str(ctx.author.id)
        bet_data = json.load(open('database/bet.json',mode='r',encoding='utf8'))
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
        for i in winner:
            pt1 = winner[i] * (mag+1)
            Point(i).add(pt1)
        #更新資料庫
        del bet_data[id]
        with open("database/bet.json",'w',encoding='utf8') as jfile:
            json.dump(bet_data,jfile,indent=4)
        #結果公布
        if end == 'pink':
            await ctx.send(f'編號:{id}\n恭喜粉紅幫獲勝!')
        else:
            await ctx.send(f'編號:{id}\n恭喜藍藍幫獲勝!')


    @commands.command()
    async def choice(self,ctx,*args):
        result = random.choice(args)
        await ctx.send(f'我選擇:{result}')

    @commands.slash_command(description='向大家說哈瞜')
    async def hello(ctx, name: str = None):
        name = name or ctx.author.name
        await ctx.respond(f"Hello {name}!")

def setup(bot):
    bot.add_cog(command(bot))