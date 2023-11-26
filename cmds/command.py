import discord,random,asyncio,datetime,re
from discord.errors import Forbidden, NotFound
from discord.ext import commands,pages
from discord.commands import SlashCommandGroup

from core.classes import Cog_Extension
from starcord import Jsondb,BRS,log,BotEmbed,ChoiceList,sclient
from starcord.DataExtractor.client import StarClient
from starcord.utilities.funtions import find,random_color
from starcord.ui_element.button import Delete_Add_Role_button
from starcord.ui_element.view import PollView
from starcord.errors import CommandError
from starcord.DataExtractor import GoogleCloud
from starcord.types import Position

from mysql.connector.errors import Error as sqlerror

#openai.api_key = Jsondb.get_token('openai')
bet_option = ChoiceList.set('bet_option')
busy_time_option = ChoiceList.set('busy_time_option')
position_option = ChoiceList.set('position_option')
party_option = ChoiceList.set('party_option')

jdata = Jsondb.jdata
main_guild = Jsondb.jdata.get('main_guild')

class command(Cog_Extension):

    bet = SlashCommandGroup("bet", "賭盤相關指令")
    role = SlashCommandGroup("role", "身分組管理指令")
    busytime = SlashCommandGroup("busytime", "忙碌時間統計指令")
    poll = SlashCommandGroup("poll", "投票相關指令")
    election = SlashCommandGroup("election", "選舉相關指令",guild_ids=main_guild)
    party = SlashCommandGroup("party", "政黨相關指令",guild_ids=main_guild)

    @role.command(description='查詢身分組數')
    async def count(self,ctx,user_list:discord.Option(str,required=False,name='要查詢的用戶',description='多個用戶請用空格隔開，或可輸入default查詢常用人選')):
        await ctx.defer()
        if not user_list:
            user_list = [ctx.author]
        elif 'default' in user_list:
            user_list = [419131103836635136,528935362199027716,465831362168094730,539405949681795073,723435216244572160,490136735557222402]
        else:
            user_list = user_list.split()
        
        embed = BotEmbed.simple("身分組計算結果")
        for i in user_list:
            user = await find.user(ctx,i)
            if user:
                id = user.id
                record = sclient.get_role_save_count(id)
                embed.add_field(name=user.name, value=record, inline=False)
        await ctx.respond(embed=embed)
 
    @role.command(description='加身分組')
    @commands.bot_has_permissions(manage_roles=True)
    @commands.cooldown(rate=1,per=5)
    async def add(self,
                  ctx:discord.ApplicationContext,
                  name:discord.Option(str,name='身分組名',description='新身分組名稱'),
                  user_list:discord.Option(str,required=False,name='要加身份組的用戶',description='多個用戶請用空格隔開')):
        await ctx.defer()
        permission = discord.Permissions.none()
        r,g,b = random_color(200)
        color = discord.Colour.from_rgb(r,g,b)
        new_role = await ctx.guild.create_role(name=name,permissions=permission,color=color)
        added_user = []
        
        if user_list:
            user_list = user_list.split()
            for user in user_list:
                user = await find.user(ctx,user)
                if user and user != self.bot.user:
                    try:
                        dbdata = sclient.get_main_account(user.id)
                        if dbdata:
                            user = ctx.guild.get_member(dbdata['main_account'])
                    except sqlerror:
                        pass
                    await user.add_roles(new_role,reason='指令:加身分組')
                    added_user.append(user.mention)
                elif user == self.bot.user:
                    await ctx.respond("請不要加我身分組好嗎")
                elif user and user.bot:
                    await ctx.respond("請不要加機器人身分組好嗎")
        
        view = Delete_Add_Role_button(new_role,ctx.author)
        if added_user:
            view.message = await ctx.respond(f"已添加 {new_role.name} 給{' '.join(added_user)}",view=view)
        else:
            view.message = await ctx.respond(f"已創建 {new_role.name} 身分組",view=view)


    @role.command(description='儲存身分組')
    @commands.cooldown(rate=1,per=5)
    @commands.is_owner()
    async def save(self,
                   ctx:discord.ApplicationContext,
                   user:discord.Option(str,name='用戶名',description='輸入all可儲存所有身分組')):
        def save_role(user:discord.Member):
            user_id = user.id
            for role in user.roles:
                if role.id == 877934319249797120:
                    break
                if role.name == '@everyone':
                    continue
                try:
                    #1062
                    sclient.add_role_save(user_id,role.id,role.name,role.created_at.date())
                    log.info(f'新增:{role.name}')
                except sqlerror as e:
                    if e.errno == 1062:
                        pass
                    else:
                        log.warning(f'儲存身分組時發生錯誤：{role.name}')
                        raise

        await ctx.defer()
        guild = self.bot.get_guild(jdata['main_guild'][0])
        add_role = guild.get_role(877934319249797120)
        if user == 'all':
            for user in add_role.members:
                save_role(user)
            await ctx.respond('身分組儲存完成',delete_after=5)
        else:
            user = await find.user(ctx,user)
            if user and add_role in user.roles:
                save_role(user)
                await ctx.respond('身分組儲存完成',delete_after=5)
            elif add_role not in user.roles:
                await ctx.respond('錯誤:此用戶沒有"加身分組"')

    @role.command(description='清除身分組')
    @commands.is_owner()
    async def rsmove(self,ctx):
        await ctx.defer()
        for user in ctx.guild.get_role(877934319249797120).members:
            log.info(user.name)
            for role in user.roles:
                if role.id == 877934319249797120:
                    break
                if role.name == '@everyone':
                    continue
                log.info(f'已移除:{role.name}')
                await role.delete()
                await asyncio.sleep(0.5)
        await ctx.respond('身分組清理完成',delete_after=5)

    @role.command(description='更改暱稱')
    @commands.bot_has_permissions(manage_roles=True)
    async def nick(self, ctx, arg:discord.Option(str,name='欲更改的內容',description='可輸入新暱稱或輸入以#開頭的6位顏色代碼')):
        await ctx.defer()
        user = ctx.author
        role = user.roles[-1]
        if role.name.startswith('稱號 | '):
            if arg.startswith('#'):
                await role.edit(colour=arg,reason='稱號:顏色改變')
            else:
                await role.edit(name=f'稱號 | {arg}',reason='稱號:名稱改變')
            await ctx.respond('暱稱更改完成',delete_after=5)
        else:
            await ctx.respond(f'錯誤:{ctx.author.mention}沒有稱號可更改',delete_after=5)

    @role.command(description='身分組紀錄')
    async def record(self, ctx, user:discord.Option(discord.Member,name='欲查詢的成員',description='留空以查詢自己',default=None)):
        await ctx.defer()
        user = user or ctx.author
        record = sclient.get_role_save(user.id)
        if record:
            page = []
            i = 10
            page_now = -1
            for data in record:
                if i >= 10:
                    page.append(BotEmbed.simple(f"{user.name} 身分組紀錄"))
                    i = 0
                    page_now += 1
                role_name = data['role_name']
                time = data['time']
                page[page_now].add_field(name=role_name, value=time, inline=False)
                i += 1

            paginator = pages.Paginator(pages=page, use_default_buttons=True)
            await paginator.respond(ctx.interaction, ephemeral=False)
            
        else:
            raise commands.errors.ArgumentParsingError('沒有此用戶的紀錄')


    @commands.slash_command(description='抽抽試手氣')
    @commands.cooldown(rate=1,per=2)
    async def draw(self,ctx,times:discord.Option(int,name='抽卡次數',description='可輸入1~1000的整數',default=1,min_value=1,max_value=1000)):
        result = {'six':0,'five':0,'four':0,'three':0}
        user_id = str(ctx.author.id)
        six_list = []
        six_list_100 = []
        guaranteed = 100
        
        dbuser = sclient.get_partial_dcuser(user_id,"guaranteed")
        user_guaranteed = dbuser.guaranteed or 0
            
        for i in range(times):
            choice =  random.randint(1,100)
            if choice == 1:
                result["six"] += 1
                six_list.append(str(i+1))
                user_guaranteed = 0
            elif user_guaranteed >= guaranteed-1:
                result["six"] += 1
                six_list_100.append(str(i+1))
                user_guaranteed = 0

            elif choice >= 2 and choice <= 11:
                result["five"] += 1
                user_guaranteed += 1
            elif choice >= 12 and choice <= 41:
                result["four"]+= 1
                user_guaranteed += 1
            else:
                result["three"] += 1
                user_guaranteed += 1

        
        dbuser.update_data('user_discord','guaranteed',user_guaranteed)
        embed=BotEmbed.lottery()
        embed.add_field(name='抽卡結果', value=f"六星x{result['six']} 五星x{result['five']} 四星x{result['four']} 三星x{result['three']}", inline=False)
        embed.add_field(name='保底累積', value=user_guaranteed, inline=False)
        if six_list:
            embed.add_field(name='六星出現', value=','.join(six_list), inline=False)
        if six_list_100:
            embed.add_field(name='保底六星', value=','.join(six_list_100), inline=False)
        await ctx.respond(embed=embed)

    @commands.slash_command(description='TRPG擲骰')
    async def dice(self,ctx,
                   dice_n:discord.Option(int,name='骰子數',description='總共擲幾顆骰子，預設為1',default=1,min_value=1),
                   dice:discord.Option(int,name='面骰',description='骰子為幾面骰，預設為100',default=100,min_value=1)):
        sum = 0
        for i in range(dice_n):
            sum += random.randint(1,dice)
        await ctx.respond(f'{dice_n}d{dice} 結果： {sum}')


    @bet.command(description='賭盤下注')
    async def place(self,ctx,
                    bet_id:discord.Option(str,name='賭盤',description='',required=True),
                    choice:discord.Option(str,name='下注顏色',description='',required=True,choices=bet_option),
                    money:discord.Option(int,name='下注點數',description='',required=True,min_value=1)):
        if bet_id == ctx.author.id:
            await ctx.respond('錯誤：你不可以下注自己的賭盤',ephemeral=True)
            return
        
        bet = sclient.get_bet_data(bet_id)
        if not bet:
            await ctx.respond('編號錯誤：沒有此編號的賭盤喔',ephemeral=True)
            return
        elif not bet['Ison']:
            await ctx.respond('錯誤：此賭盤已經關閉了喔',ephemeral=True)
            return
        
        user_data = sclient.get_point(str(ctx.author.id))

        if user_data['point'] < money:
            await ctx.respond('點數錯誤：你沒有那麼多點數',ephemeral=True)
            return

        sclient.update_point('add',str(ctx.author.id),money*-1)
        sclient.place_bet(bet_id,choice,money)
        await ctx.respond('下注完成!')


    @bet.command(description='創建賭盤')
    async def create(self,ctx,
                     title:discord.Option(str,name='賭盤標題',description='',required=True),
                     pink:discord.Option(str,name='粉紅幫標題',description='',required=True),
                     blue:discord.Option(str,name='藍藍幫標題',description='',required=True),
                     time:discord.Option(int,name='賭盤開放時間',description='',required=True,min_value=10,max_value=600)):
        bet_id = str(ctx.author.id)
        bet = sclient.get_bet_data(bet_id)
        if bet:
            await ctx.respond('錯誤：你已經創建一個賭盤了喔',ephemeral=True)
            return

        sclient.create_bet(bet_id,title,pink,blue)
            
        embed = BotEmbed.simple(title='賭盤', description=f'編號: {bet_id}')
        embed.add_field(name='賭盤內容', value=title, inline=False)
        embed.add_field(name="粉紅幫", value=pink, inline=False)
        embed.add_field(name="藍藍幫", value=blue, inline=False)
        await ctx.respond(embed=embed)
        await asyncio.sleep(delay=time)
        
        await ctx.send(f'編號{bet_id}：下注時間結束')
        sclient.update_bet(bet_id)


    @bet.command(description='結束賭盤')
    async def end(self,ctx,end:discord.Option(str,name='獲勝下注顏色',description='',required=True,choices=bet_option)):
        bet_id = str(ctx.author.id)
        #錯誤檢測
        bet = sclient.get_bet_data(bet_id)
        if bet['IsOn']:
            await ctx.respond('錯誤：此賭盤的開放下注時間尚未結束',ephemeral=True)
            return
        
        #計算雙方總點數
        total = sclient.get_bet_total(bet_id)
        
        #偵測是否兩邊皆有人下注
        if total[0] and total[1]:
            #獲勝者設定
            winners = sclient.get_bet_winner(bet_id,end)
            #前置準備
            pink_total = total[0]
            blue_total = total[1]
            if pink_total > blue_total:
                mag = pink_total / blue_total
            else:
                mag = blue_total / pink_total
            #結果公布
            if end == 'pink':
                await ctx.respond(f'編號{bet_id}：恭喜粉紅幫獲勝!')
            elif end == 'blue':
                await ctx.respond(f'編號{bet_id}：恭喜藍藍幫獲勝!')
            #點數計算
            for i in winners:
                pt_add = i['money'] * (mag+1)
                sclient.update_point('add',i['user_id'],pt_add)
            
        else:
            users = sclient.get_bet_winner(bet_id,'blue')
            for i in users:
                sclient.update_point('add',i['user_id'],i['money'])
            
            users = sclient.get_bet_winner(bet_id,'pink')
            for i in users:
                sclient.update_point('add',i['user_id'],i['money'])
            await ctx.respond(f'編號{bet_id}：因為有一方沒有人選擇，所以此局平手，點數將歸還給所有人')
        
        #更新資料庫
        sclient.remove_bet(bet_id)    

    @commands.user_command()  # create a user command for the supplied guilds
    async def whois(self,ctx, member: discord.Member):  # user commands return the member
        user = member
        embed = BotEmbed.simple(title=f'{user.name}#{user.discriminator}', description="ID:用戶(伺服器成員)")
        embed.add_field(name="暱稱", value=user.nick, inline=False)
        embed.add_field(name="最高身分組", value=user.top_role.mention, inline=True)
        embed.add_field(name="目前狀態", value=user.raw_status, inline=True)
        if user.activity:
            embed.add_field(name="目前活動", value=user.activity, inline=True)
        embed.add_field(name="是否為機器人", value=user.bot, inline=False)
        embed.add_field(name="是否為Discord官方", value=user.system, inline=True)
        embed.add_field(name="是否被禁言", value=user.timed_out, inline=True)
        embed.add_field(name="加入群組日期", value=user.joined_at, inline=False)
        embed.add_field(name="帳號創建日期", value=user.created_at, inline=False)
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.set_footer(text=f"id:{user.id}")
        await ctx.respond(embed=embed,ephemeral=True)

    @commands.user_command(name="禁言10秒")
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def timeout_10s(self,ctx, member: discord.Member):
        time = datetime.timedelta(seconds=10)
        await member.timeout_for(time,reason="指令：禁言10秒")
        await ctx.respond(f"已禁言{member.mention} 10秒",ephemeral=True)
    
    @commands.user_command(name="不想理你生態區",guild_ids=jdata['main_guild'])
    @commands.has_permissions(moderate_members=True)
    async def user_command2(self,ctx, member: discord.Member):
        await ctx.respond(f"開始執行",ephemeral=True)
        channel = self.bot.get_channel(613760923668185121)
        for i in range(40):
            if member.voice and member.voice.channel != channel:
                await member.move_to(channel)
            await asyncio.sleep(0.5)

    @commands.slash_command(description='傳送訊息給機器人擁有者')
    @commands.cooldown(rate=1,per=10)
    async def feedback(self,
                       ctx:discord.ApplicationContext,
                       text:discord.Option(str,name='訊息',description='要傳送的訊息內容，歡迎提供各項建議')):
        await ctx.defer()
        await BRS.feedback(self,ctx,text)
        await ctx.respond(f"訊息已發送!",ephemeral=True,delete_after=3)

    @staticmethod
    def Autocomplete(self: discord.AutocompleteContext):
        return ['test']

    @commands.slash_command(description='讓機器人選擇一樣東西')
    async def choice(self,ctx,args:discord.Option(str,name='選項',description='多個選項請用空格隔開')):
        args = args.split()
        result = random.choice(args)
        await ctx.respond(f'我選擇:{result}')

    # @commands.cooldown(rate=1,per=50)
    # @commands.slash_command(description='既然ChatGPT那麼紅，那為何不試試看跟AI聊天呢?')
    # async def chat(self,ctx:discord.ApplicationContext,content:discord.Option(str,name='訊息',description='要傳送的訊息內容')):
    #     await ctx.defer()
    #     raise CommandError('目前聊天的額度已過期，故無法使用此指令，敬請期待未來更新')
    #     response = openai.Completion.create(
    #         model="text-davinci-003",
    #         prompt=content,
    #         temperature=0.9,
    #         max_tokens=500,
    #         top_p=1,
    #         frequency_penalty=0.0,
    #         presence_penalty=0.6,
    #         stop=[" Human:", " AI:"]
    #     )
    #     text = response['choices'][0]['text']
    #     await ctx.respond(text)

    @busytime.command(description='新增沒空時間')
    async def add(self,
                  ctx:discord.ApplicationContext,
                  date:discord.Option(str,name='日期',description='6/4請輸入0604 6/5~6/8請輸入0605~0608 以此類推'),
                  time:discord.Option(str,name='時間',description='',choices=busy_time_option)):
        try:
            if len(date) == 4:
                datetime.datetime.strptime(date,"%m%d")
                sclient.add_busy(ctx.author.id,date,time)
                await ctx.respond('設定完成')
            elif len(date) == 9:
                date1_str = date[0:4]
                date2_str = date[5:9]
                date1 = datetime.datetime.strptime(date1_str,"%m%d")
                date2 = datetime.datetime.strptime(date2_str,"%m%d")
        except ValueError:
            await ctx.respond('錯誤：日期格式錯誤')
            return
            
        for i in range((date2 - date1).days + 1):
            date_str = date1.strftime("%m%d")
            sclient.add_busy(str(ctx.author.id),date_str,time)
            date1 += datetime.timedelta(days=1)
        await ctx.respond('設定完成')


    @busytime.command(description='移除沒空時間')
    async def remove(self,
                     ctx:discord.ApplicationContext,
                     date:discord.Option(str,name='日期',description='6/4請輸入0604 6/5~6/8請輸入0605~0608 以此類推'),
                     time:discord.Option(str,name='時間',description='',choices=busy_time_option)):
        try:
            if len(date) == 4:
                datetime.datetime.strptime(date,"%m%d")
                sclient.remove_busy(ctx.author.id, date,time)
                await ctx.respond('移除完成')
            elif len(date) == 9:
                date1_str = date[0:4]
                date2_str = date[5:9]
                date1 = datetime.datetime.strptime(date1_str,"%m%d")
                date2 = datetime.datetime.strptime(date2_str,"%m%d")
        except ValueError:
            await ctx.respond('錯誤：日期格式錯誤')
            return
        
        for i in range((date2 - date1).days + 1):
            date_str = date1.strftime("%m%d")
            sclient.remove_busy(str(ctx.author.id),date_str,time)
            date1 += datetime.timedelta(days=1)
        await ctx.respond('設定完成')

    @busytime.command(description='確認沒空時間')
    async def check(self,
                    ctx:discord.ApplicationContext,
                    date:discord.Option(str,name='日期',description='請輸入四位數日期 如6/4請輸入0604 留空查詢現在時間',required=False),
                    days:discord.Option(int,name='連續天數',description='想查詢的天數 預設為7',default=7,min_value=1,max_value=270)):
        if date:
            date_now = datetime.datetime.strptime(date,"%m%d")
        else:
            date_now = datetime.datetime.now()
        text = ""

        for i in range(days):
            date_str = date_now.strftime("%m%d")
            dbdata = sclient.get_busy(date_str)
            list = ["早上","下午","晚上"]
            for j in dbdata:
                try:
                    if j['time'] == "1":
                        list.remove("早上")
                    if j['time'] == "2":
                        list.remove("下午")
                    if j['time'] == "3":
                        list.remove("晚上")
                except ValueError:
                    pass

            text += f"{date_str}: {','.join(list)}\n"
            date_now += datetime.timedelta(days=1)

        embed = BotEmbed.simple('目前有空時間',text)
        await ctx.respond(embed=embed)

    @busytime.command(description='統計沒空時間')
    async def statistics(self,ctx):
        user_list = self.bot.get_guild(613747262291443742).get_role(1097455657428471918).members
        text = ''
        for i in user_list:
            dbdata = sclient.get_statistics_busy(i.id)
            text += f'{i.mention}: {dbdata.get("count(user_id)")}\n'
        embed = BotEmbed.simple('總計',text)
        await ctx.respond(embed=embed)

    @busytime.command(description='創建活動',guild_ids=main_guild)
    async def event(self,ctx,
                    date:discord.Option(str,name='時間',description='請輸入四位數日期+四位數時間 如8/25 14:00請輸入08251400'),
                    during:discord.Option(int,name='活動持續天數',description='活動將持續幾天',default=1,min_value=1,max_value=31)):
        guild = self.bot.get_guild(613747262291443742)
        
        timezone = datetime.timezone(datetime.timedelta(hours=8))
        today = datetime.datetime.today()
        date += str(today.year)
        start_time = datetime.datetime.strptime(date,"%m%d%H%M%Y")
        if start_time < today:
            date += str(today.year + 1)
            start_time = datetime.datetime.strptime(date,"%m%d%H%M%Y")
        start_time = start_time.replace(tzinfo=timezone)
        
        end_time = datetime.datetime(start_time.year,start_time.month,start_time.day,0,0,0) + datetime.timedelta(days=during)
        end_time = end_time.replace(tzinfo=timezone)

        event = await guild.create_scheduled_event(name="【第二屆線上TRPG】正式場第三場-???",start_time=start_time,end_time=end_time,location="https://trpgline.com/zh-TW/admin")
        await ctx.respond(f"{event.name} 已建立完成")
        channel = self.bot.get_channel(1097158403358478486)
        await channel.send(f"{event.name}：{event.url}")

    @commands.user_command(name="辣味貢丸一周年",guild_ids=main_guild)
    @commands.bot_has_permissions(moderate_members=True)
    async def meatball(self,ctx, member: discord.Member):
        time = datetime.timedelta(seconds=60)
        await member.timeout_for(time,reason="辣味貢丸一周年")
        await member.edit(nick="我是辣味貢丸")
        role = member.guild.get_role(1136338119835254946)
        await member.add_roles(role)
        
        await ctx.respond(f"辣味貢丸大禮包~",ephemeral=True)
        channel = self.bot.get_channel(640541440103153674)
        await channel.send(f"{member.mention}收到了一份貢丸大禮包")
        sclient.add_userdata_value(member.id,"user_discord","meatball_times",1)
        
        # admin_role = member.get_role(613748153644220447)
        # if admin_role:
        #     await member.remove_roles(admin_role)

    @poll.command(description='創建投票',guild_ids=main_guild)
    async def create(self,ctx,
                     title:discord.Option(str,name='標題',description='投票標題，限45字內'),
                     options:discord.Option(str,name='選項',description='投票選項，最多輸入10項，每個選項請用英文,隔開'),
                     alternate_account_can_vote:discord.Option(bool,name='小帳是否算有效票',description='預設為true',default=True),
                     show_name:discord.Option(bool,name='投票結果是否顯示用戶名',description='預設為false，若投票人數多建議關閉',default=False)):
        options = options.split(",")
        if len(options) > 10 or len(options) < 1:
            await ctx.respond(f"錯誤：投票選項超過10項或小於1項",ephemeral=True)
            return
        
        view = sclient.create_poll(title,options,ctx.author.id,ctx.guild.id,alternate_account_can_vote,show_name)
        embed = view.display()
        embed.set_author(name=ctx.author.name,icon_url=ctx.author.avatar.url)
        message = await ctx.respond(embed=embed,view=view)
        sclient.update_poll(view.poll_id,"message_id",message.id)

    @commands.is_owner()
    @poll.command(description='重新創建投票介面',guild_ids=main_guild)
    async def view(self,ctx,
                   poll_id:discord.Option(int,name='投票id',description='')):
        dbdata = sclient.get_poll(poll_id)
        if dbdata:
            view = PollView(dbdata['poll_id'],sqldb=sclient)
            await ctx.respond(view=view,embed=view.display())
        else:
            await ctx.respond("錯誤：查無此ID")

    @commands.slash_command(description='共用「94共用啦」雲端資料夾',guild_ids=main_guild)
    async def drive(self,ctx,email:discord.Option(str,name='gmail帳戶',description='要使用的Gmail帳戶，留空已移除資料',required=False)):
        await ctx.defer()
        data = sclient.get_userdata(ctx.author.id,"user_data")
        if not email:
            if data and data.get("email"):
                GoogleCloud().remove_file_permissions("1bDtsLbOi5crIOkWUZbQmPq3dXUbwWEan",data.get("drive_share_id"))
                sclient.set_userdata(ctx.author.id,"user_data","email",None)
                sclient.set_userdata(ctx.author.id,"user_data","drive_share_id",None)
            else:
                await ctx.respond(f"{ctx.author.mention}：此帳號沒有設定過google帳戶")
                return
        
        if data and data.get("drive_share_id"):
            await ctx.respond(f"{ctx.author.mention}：此帳號已經共用雲端資料夾了")
            return
        
        r = re.compile(r"@gmail.com")
        if not r.search(email):
            await ctx.respond(f"{ctx.author.mention}：Gmail格式錯誤")
            return
        
        google_data = GoogleCloud().add_file_permissions("1bDtsLbOi5crIOkWUZbQmPq3dXUbwWEan",email)
        sclient.set_staruser_data(ctx.author.id,email,google_data.get("id"))
        await ctx.respond(f"{ctx.author.mention}：已與 {email} 共用雲端資料夾")

    @election.command(description='加入選舉')
    async def join(self, ctx,
                   position:discord.Option(str,name='職位',description='要競選的職位',choices=position_option),
                   user_dc:discord.Option(discord.Member,name='成員',description='要競選的成員（此選項供政黨代表一次性報名用）',required=False)):
        user_dc = user_dc or ctx.author
        sclient.add_election(user_dc.id,3,position)
        await ctx.respond(f"{user_dc.mention}：完成競選報名 {Jsondb.jdict['position_option'].get(position)}")

    @election.command(description='離開選舉')
    async def leave(self, ctx):
        sclient.remove_election(ctx.author.id,3)
        await ctx.respond(f"{ctx.author.mention}：完成競選退出")

    @election.command(description='候選人名單')
    @commands.is_owner()
    async def format(self, ctx):
        await ctx.defer()
        session = 3
        dbdata = sclient.get_election_full_by_session(session)
        result = {
            "president": {},
            "legislative_president": {},
            "executive_president": {}
        }
        
        for i in dbdata:
            discord_id = i['discord_id']
            party_name = i['party_name'] or "無黨籍"
            position = i['position']
            
            user = self.bot.get_user(i['discord_id'])
            if user:
                if discord_id in result[position]:
                    result[position][discord_id][1].append(party_name)
                else:
                    result[position][discord_id] = [user.mention, [party_name]]
            
            f"{user.mention} （{party_name}）"
        embed = BotEmbed.simple(f"第{session}屆中央選舉名單")
        
        for position_name in result:
            text = ""
            count = 0
            for i in result[position_name]:
                count += 1
                user_mention = result[position_name][i][0]
                party_name = ",".join(result[position_name][i][1])
                text += f"{count}. {user_mention} （{party_name}）\n"
            embed.add_field(name=Jsondb.jdict['position_option'].get(position_name),value=text,inline=False)

        await ctx.respond(embed=embed)

    @election.command(description='開始投票')
    @commands.is_owner()
    async def start(self,ctx:discord.ApplicationContext):
        await ctx.defer()
        session = 3

        count_data = sclient.get_election_count(session)
        for position_data in count_data:
            if position_data['count'] > 0:
                position_name = Jsondb.jdict['position_option'].get(position_data['position'])
                title = f"第{session}屆中央選舉：{position_name}"
                options = []
                for i in range(1,position_data['count'] + 1):
                    options.append(f"{i}號")

                view = sclient.create_poll(title,options,ctx.author.id,ctx.guild.id,False)

                message = await ctx.send(embed=view.display(),view=view)
                sclient.update_poll(view.poll_id,"message_id",message.id)
                await asyncio.sleep(1)
        await ctx.respond(f"第{session}屆中央選舉投票創建完成")

        timezone = datetime.timezone(datetime.timedelta(hours=8))
        start_time = datetime.datetime.now(timezone)
        if start_time.hour < 20:
            end_time = datetime.datetime(start_time.year,start_time.month,start_time.day,20,0,0,tzinfo=timezone)
        else:
            end_time = start_time + datetime.timedelta(days=1)
            
        event = await ctx.guild.create_scheduled_event(name="【快樂營中央選舉】第三屆",start_time=start_time,end_time=end_time,location="#🏛中央投票所")

    @party.command(description='加入政黨')
    async def join(self,ctx:discord.ApplicationContext,
                    party_id:discord.Option(int,name='政黨',description='要參加的政黨',choices=party_option)):
        sclient.join_party(ctx.author.id,party_id)
        try:
            dbdata = sclient.get_party_data(party_id)
            role_id = dbdata["role_id"]
            role = ctx.guild.get_role(role_id)
            if role:
                await ctx.author.add_roles(role)
        except:
            pass

        await ctx.respond(f"{ctx.author.mention} 已加入政黨 {ChoiceList.get_tw(str(party_id),'party_option')}")

    @party.command(description='離開政黨')
    async def leave(self,ctx:discord.ApplicationContext,
                    party_id:discord.Option(int,name='政黨',description='要參加的政黨',choices=party_option)):
        sclient.leave_party(ctx.author.id,party_id)
        try:
            dbdata = sclient.get_party_data(party_id)
            role_id = dbdata["role_id"]
            role = ctx.author.get_role(role_id)
            if role:
                await ctx.author.remove_roles(role)
        except:
            pass

        await ctx.respond(f"{ctx.author.mention} 已退出政黨 {ChoiceList.get_tw(str(party_id),'party_option')}")

    @party.command(description='政黨列表')
    async def list(self,ctx:discord.ApplicationContext):
        dbdata = sclient.get_all_party_data()
        embed = BotEmbed.simple("政黨統計")
        for party in dbdata:
            embed.add_field(name=party["party_name"], value=f"政黨ID：{party['party_id']}\n政黨人數：{party['count']}")
        await ctx.respond(embed=embed)


def setup(bot):
    bot.add_cog(command(bot))