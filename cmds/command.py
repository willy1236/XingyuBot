import discord,random,asyncio,math,datetime
from discord.errors import Forbidden, NotFound
from discord.ext import commands,pages
from discord.commands import SlashCommandGroup

from bothelper.funtions import find,converter,random_color
from core.classes import Cog_Extension
from bothelper.interface.user import *
from bothelper import Jsondb,BRS

from mysql.connector.errors import Error as sqlerror

jdict = Jsondb.jdict

bet_option = []
for name,value in jdict['bet_option'].items():
    bet_option.append(discord.OptionChoice(name=name,value=value))


class command(Cog_Extension):
    picdata = Jsondb.picdata
    #rsdata = bothelper.Jsondb.rsdata

    twitch = SlashCommandGroup("twitch", "Twitch相關指令")
    bet = SlashCommandGroup("bet", "賭盤相關指令")
    role = SlashCommandGroup("role", "身分組管理指令")

    # @commands.command()
    # @commands.cooldown(rate=1,per=3)
    # async def find(self,ctx,id):
    #     success = 0
    #     user = await self.bot.get_or_fetch_user(id)
    #     if user and user in ctx.guild.members:
    #         user = ctx.guild.get_member(user.id)
    #         embed = BotEmbed.simple(title=f'{user.name}#{user.discriminator}', description="ID:用戶(伺服器成員)")
    #         embed.add_field(name="暱稱", value=user.nick, inline=False)
    #         embed.add_field(name="最高身分組", value=user.top_role.mention, inline=True)
    #         embed.add_field(name="目前狀態", value=user.raw_status, inline=True)
    #         if user.activity:
    #             embed.add_field(name="目前活動", value=user.activity, inline=True)
    #         embed.add_field(name="是否為機器人", value=user.bot, inline=False)
    #         embed.add_field(name="是否為Discord官方", value=user.system, inline=True)
    #         embed.add_field(name="是否被禁言", value=user.timed_out, inline=True)
    #         embed.add_field(name="加入群組日期", value=user.joined_at, inline=False)
    #         embed.add_field(name="帳號創建日期", value=user.created_at, inline=False)
    #         embed.set_thumbnail(url=user.display_avatar.url)
    #         embed.set_footer(text=f"id:{user.id}")
    #         success += 1
    #     elif user:
    #         embed = BotEmbed.simple(title=f'{user.name}#{user.discriminator}', description="ID:用戶")
    #         embed.add_field(name="是否為機器人", value=user.bot, inline=False)
    #         embed.add_field(name="是否為Discord官方", value=user.system, inline=False)
    #         embed.add_field(name="帳號創建日期", value=user.created_at, inline=False)
    #         embed.set_thumbnail(url=user.display_avatar.url)
    #         success += 1

    #     channel = self.bot.get_channel(id)
    #     if channel:
    #         embed = BotEmbed.simple(title=channel.name, description="ID:頻道")
    #         embed.add_field(name="所屬類別", value=channel.category, inline=False)
    #         embed.add_field(name="所屬公會", value=channel.guild, inline=False)
    #         embed.add_field(name="創建時間", value=channel.created_at, inline=False)
    #         success += 1
        
    #     guild = self.bot.get_guild(id)
    #     if guild:
    #         embed = BotEmbed.simple(title=guild.name, description="ID:公會")
    #         embed.add_field(name="公會擁有者", value=guild.owner, inline=False)
    #         embed.add_field(name="創建時間", value=guild.created_at, inline=False)
    #         embed.add_field(name="驗證等級", value=guild.verification_level, inline=False)
    #         embed.add_field(name="成員數", value=len(guild.members), inline=False)
    #         embed.add_field(name="文字頻道數", value=len(guild.text_channels), inline=False)
    #         embed.add_field(name="語音頻道數", value=len(guild.voice_channels), inline=False)
    #         embed.set_footer(text='數字可能因權限不足而有少算，敬請特別注意')
    #         embed.set_thumbnail(url=guild.icon.url)
    #         success += 1
            
    #     if success == 1:
    #         await ctx.send(embed=embed)
    #     elif success > 1:
    #         await BRS.error(self,ctx,f'find:id重複(出現{success}次)')
    #         await ctx.send('出現錯誤，已自動向機器人擁有者回報')
    #     else:
    #         await ctx.send('無法辨認此ID',delete_after=5)

    @role.command(description='查詢身分組數')
    async def count(self,ctx,user_list:discord.Option(str,required=False,name='要查詢的用戶',description='多個用戶請用空格隔開，或可輸入default查詢常用人選')):
        await ctx.defer()
        if not user_list:
            user_list = [ctx.author]
        elif 'default' in user_list:
            user_list = [419131103836635136,528935362199027716,465831362168094730,539405949681795073,723435216244572160,490136735557222402]
        else:
            user_list = user_list.split()
        
        embed=BotEmbed.general("身分組計算結果")
        for i in user_list:
            user = await find.user(ctx,i)
            if user:
                id = str(user.id)
                record = self.sqldb.get_role_save_count(id)
                embed.add_field(name=user.name, value=record[0]['COUNT(user_id)'], inline=False)
        await ctx.respond(embed=embed)

    @role.command(description='加身分組')
    @commands.cooldown(rate=1,per=5)
    async def add(self,
                  ctx:discord.ApplicationContext,
                  name:discord.Option(str,name='身分組名',description='新身分組名稱'),
                  user_list:discord.Option(str,required=False,name='要加身份組的用戶',description='多個用戶請用空格隔開')):
        await ctx.defer()
        permission = discord.Permissions.none()
        r,g,b=random_color(200)
        color = discord.Colour.from_rgb(r,g,b)
        new_role = await ctx.guild.create_role(name=name,permissions=permission,color=color)
        added_role = []
        if user_list:
            user_list = user_list.split()
            for user in user_list:
                user = await find.user(ctx,user)
                if user and user != self.bot.user:
                    await user.add_roles(new_role,reason='指令:加身分組')
                    added_role.append(user)
                elif user == self.bot.user:
                    await ctx.respond("請不要加我身分組好嗎")
                elif user and user.bot:
                    await ctx.respond("請不要加機器人身分組好嗎")
        
        if added_role != []:
            all_user = ''
            for user in added_role:
                all_user += f' {user.mention}'
            await ctx.respond(f"已添加 {new_role.name} 給{all_user}")
        else:
            await ctx.respond(f"已創建 {new_role.name} 身分組")


    @role.command(description='儲存身分組')
    @commands.cooldown(rate=1,per=5)
    @commands.is_owner()
    async def save(self,
                   ctx:discord.ApplicationContext,
                   user:discord.Option(str,name='用戶名',description='輸入all可儲存所有身分組')):
        def save_role(user):
            user_id = user.id
            for role in user.roles:
                if role.id == 877934319249797120:
                    break
                if role.name == '@everyone':
                    continue
                try:
                    #1062
                    self.sqldb.add_role_save(user_id,str(role.id),role.name,role.created_at.strftime('%Y%m%d'))
                    print(f'新增:{role.name}')
                except sqlerror as e:
                    if e.errno == 1062:
                        pass
                    else:
                        print(f'儲存身分組時發生錯誤：{role.name}')
                        raise

        
        await ctx.defer()
        jdata = Jsondb.jdata
        guild = self.bot.get_guild(jdata['guild']['001'])
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
            print(user.name)
            for role in user.roles:
                if role.id == 877934319249797120:
                    break
                if role.name == '@everyone':
                    continue
                print(f'已移除:{role.name}')
                await role.delete()
                asyncio.sleep(0.5)
        await ctx.respond('身分組清理完成',delete_after=5)

    @role.command(description='更改暱稱')
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
        record = self.sqldb.get_role_save(str(user.id))
        if record:
            page = []
            i = 0
            page_now = 0
            page.append(BotEmbed.simple(f"{user.name} 身分組紀錄"))
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


    @commands.slash_command(description='抽卡試手氣')
    @commands.cooldown(rate=1,per=2)
    async def lottery(self,ctx,times:discord.Option(int,name='抽卡次數',description='可輸入1~1000的整數',default=1,min_value=1,max_value=1000)):
        result = {'six':0,'five':0,'four':0,'three':0}
        user_id = str(ctx.author.id)
        six_list = []
        six_list_100 = []
        guaranteed = 100
        #db = bothelper.Jsondb
        #jloot = db.jloot
        data = self.sqldb.get_userdata(user_id,'user_lottery')
        if data:
            user_guaranteed = data['guaranteed']
        else:
            user_guaranteed = 0
            
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
        
        #db.write('jloot',jloot)
        self.sqldb.update_userdata(user_id,'user_lottery','guaranteed',user_guaranteed)
        embed=BotEmbed.lottery()
        embed.add_field(name='抽卡結果', value=f"六星:{result['six']} 五星:{result['five']} 四星:{result['four']} 三星:{result['three']}", inline=False)
        embed.add_field(name='保底累積', value=user_guaranteed, inline=False)
        if len(six_list) > 0:
            embed.add_field(name='六星出現', value=','.join(six_list), inline=False)
        if len(six_list_100) > 0:
            embed.add_field(name='保底', value=','.join(six_list_100), inline=False)
        await ctx.respond(embed=embed)


    @bet.command(description='賭盤下注')
    async def place(self,ctx,
                    bet_id:discord.Option(str,name='賭盤',description='',required=True),
                    choice:discord.Option(str,name='下注顏色',description='',required=True,choices=bet_option),
                    money:discord.Option(int,name='下注點數',description='',required=True,min_value=1)):
        if bet_id == ctx.author.id:
            await ctx.respond('錯誤：你不可以下注自己的賭盤',ephemeral=True)
            return
        
        bet = self.sqldb.get_bet_data(bet_id)
        if not bet:
            await ctx.respond('編號錯誤：沒有此編號的賭盤喔',ephemeral=True)
            return
        elif not bet['Ison']:
            await ctx.respond('錯誤：此賭盤已經關閉了喔',ephemeral=True)
            return
        
        user_data = self.sqldb.get_point(str(ctx.author.id))

        if user_data['point'] < money:
            await ctx.respond('點數錯誤：你沒有那麼多點數',ephemeral=True)
            return

        self.sqldb.update_point('add',str(ctx.author.id),money*-1)
        self.sqldb.place_bet(bet_id,choice,money)
        await ctx.respond('下注完成!')


    @bet.command(description='創建賭盤')
    async def create(self,ctx,
                     title:discord.Option(str,name='賭盤標題',description='',required=True),
                     pink:discord.Option(str,name='粉紅幫標題',description='',required=True),
                     blue:discord.Option(str,name='藍藍幫標題',description='',required=True),
                     time:discord.Option(int,name='賭盤開放時間',description='',required=True,min_value=10,max_value=600)):
        bet_id = str(ctx.author.id)
        # sec = converter.time(time)
        bet = self.sqldb.get_bet_data(bet_id)
        if bet:
            await ctx.respond('錯誤：你已經創建一個賭盤了喔',ephemeral=True)
            return
        # elif time > 600:
        #     await ctx.send('錯誤:時間太長了喔')
        #     return

        self.sqldb.create_bet(bet_id,title,pink,blue)
            
        embed = BotEmbed.simple(title='賭盤', description=f'編號: {bet_id}')
        embed.add_field(name='賭盤內容', value=title, inline=False)
        embed.add_field(name="粉紅幫", value=pink, inline=False)
        embed.add_field(name="藍藍幫", value=blue, inline=False)
        await ctx.respond(embed=embed)
        await asyncio.sleep(delay=time)
        
        await ctx.send(f'編號{bet_id}：下注時間結束')
        self.sqldb.update_bet(bet_id)


    @bet.command(description='結束賭盤')
    async def end(self,ctx,end:discord.Option(str,name='獲勝下注顏色',description='',required=True,choices=bet_option)):
        bet_id = str(ctx.author.id)
        #錯誤檢測
        bet = self.sqldb.get_bet_data(bet_id)
        if bet['IsOn']:
            await ctx.respond('錯誤：此賭盤的開放下注時間尚未結束',ephemeral=True)
            return
        
        #計算雙方總點數
        total = self.sqldb.get_bet_total(bet_id)
        
        #偵測是否兩邊皆有人下注
        if total[0] and total[1]:
            #獲勝者設定
            winners = self.sqldb.get_bet_winner(bet_id,end)
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
                self.sqldb.update_point('add',i['user_id'],pt_add)
            
        else:
            users = self.sqldb.get_bet_winner(bet_id,'blue')
            for i in users:
                self.sqldb.update_point('add',i['user_id'],i['money'])
            
            users = self.sqldb.get_bet_winner(bet_id,'pink')
            for i in users:
                self.sqldb.update_point('add',i['user_id'],i['money'])
            await ctx.respond(f'編號{bet_id}：因為有一方沒有人選擇，所以此局平手，點數將歸還給所有人')
        
        #更新資料庫
        self.sqldb.remove_bet(bet_id)


    # @commands.command()
    # async def ma(self,ctx,argAl,argAw,argAn,argBl,argBw,argBn):
    #     argAl = int(argAl)
    #     argAw = int(argAw)
    #     argAn = argAn.split()
        
    #     argBl = int(argBl)
    #     argBw = int(argBw)
    #     argBn = argBn.split()

    #     def setup(l:int,w:int,n:list):
    #         j = 0
    #         X = []
    #         X2 = []
    #         for i in n:
    #             j+=1
    #             X2.append(i)
    #             if j == w:
    #                 X.append(X2)
    #                 j = 0
    #                 X2 = []
    #         return X

    #     A = setup(argAl,argAw,argAn)
    #     B = setup(argBl,argBw,argBn)

    #     #l*w l*w
    #     if argAw != argBl:
    #         await ctx.send('A B矩陣無法相乘')
    #     elif argAl*argAw != len(argAn):
    #         await ctx.send('A矩陣格式不對')
    #     elif argBl*argBw != len(argBn):
    #         await ctx.send('B矩陣格式不對')
    #     else:
    #         C = []
    #         Cl = argAl
    #         Cw = argBw

    #         for i in range(1,Cl+1):
    #             C2 = []
    #             for j in range(1,Cw+1):
    #                 C3 = 0
    #                 for k in range(1,argAw+1):
    #                     #print(f'{int(A[j-1][k-1])} * {int(B[k-1][i-1])}={int(A[j-1][k-1]) * int(B[k-1][i-1])}')
    #                     #print(C3)
    #                     C3 += int(A[i-1][k-1]) * int(B[k-1][j-1])
    #                 C2.append(C3)
    #             C.append(C2)
            
    #         embed = BotEmbed.simple('矩陣乘法')
    #         embed.add_field(name='A矩陣',value=f'{A}, {argAl}x{argAw}')
    #         embed.add_field(name='B矩陣',value=f'{B}, {argBl}x{argBw}')
    #         embed.add_field(name='AXB矩陣(C矩陣)',value=f'{C}, {Cl}x{Cw}')
    #         await ctx.send(embed=embed)

    @twitch.command(description='設置twitch開台通知')
    async def set(self,ctx,
                  twitch_user:discord.Option(str,required=True,name='twitch用戶',description='當此用戶開台時會發送通知'),
                  channel:discord.Option(discord.TextChannel,required=True,name='頻道',description='通知發送頻道'),
                  role:discord.Option(discord.Role,required=False,default=None,name='身分組',description='發送通知時tag的身分組')):
        guildid = ctx.guild.id
        channelid = channel.id
        if role:
            roleid = role.id
        else:
            roleid = None
        
        self.sqldb.set_notice_community('twitch',twitch_user,guildid,channelid,roleid)
        if role:
            await ctx.respond(f'設定成功：{twitch_user}的開台通知將會發送在{channel.mention}並會通知{role.mention}')
        else:
            await ctx.respond(f'設定成功：{twitch_user}的開台通知將會發送在{channel.mention}')

    @twitch.command(description='移除twitch開台通知')
    async def remove(self,ctx,twitch_user:discord.Option(str,required=True,name='twitch用戶')):
        guildid = ctx.guild.id
        
        self.sqldb.remove_notice_community('twitch',twitch_user,guildid)
        await ctx.respond(f'已移除 {twitch_user} 的開台通知')
        #await ctx.respond(f'{twitch_user} 還沒有被設定通知')

    @twitch.command(description='確認twitch開台通知')
    async def notice(self,ctx,twitch_user:discord.Option(str,required=True,name='twitch用戶')):
        guildid = ctx.guild.id
        
        record = self.sqldb.get_notice_community_user('twitch',twitch_user,guildid)
        if record:
            channel = self.bot.get_channel(record[0]['channel_id'])
            await ctx.respond(f'TwitchID: {twitch_user} 的開台通知在 {channel.mention}')
        else:
            await ctx.respond(f'TwitchID: {twitch_user} 在此群組沒有設開台通知')

    @commands.slash_command(description='向大家說哈瞜')
    async def hello(self,ctx, name: str = None):
        await ctx.defer()
        name = name or ctx.author.name
        await ctx.respond(f"Hello {name}!")

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

    @commands.user_command(name="禁言15秒")
    @commands.has_permissions(moderate_members=True)
    async def timeout_10s(self,ctx, member: discord.Member):
        time = datetime.timedelta(seconds=15)
        await member.timeout_for(time,reason="指令：禁言15秒")
        await ctx.respond(f"已禁言{member.mention} 15秒",ephemeral=True)

    @commands.slash_command(description='傳送訊息給伺服器擁有者')
    @commands.cooldown(rate=1,per=10)
    async def feedback( self,
                        ctx:discord.ApplicationContext,
                        text:discord.Option(str,name='訊息',description='要傳送的訊息內容'),
                        ):
        await ctx.defer()
        await BRS.feedback(self,ctx,text)
        await ctx.respond(f"訊息已發送!",ephemeral=True,delete_after=3)

    @staticmethod
    def Autocomplete(self: discord.AutocompleteContext):
        return ['test']

    @commands.slash_command(description='讓機器人選擇一樣東西')
    async def choice(self,ctx,args:discord.Option(str,required=False,name='選項',description='多個選項請用空格隔開')):
        args = args.split()
        result = random.choice(args)
        await ctx.respond(f'我選擇:{result}')

def setup(bot):
    bot.add_cog(command(bot))