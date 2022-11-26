import discord,random,asyncio,math,datetime
from discord.errors import Forbidden, NotFound
from discord.ext import commands,pages
from discord.commands import SlashCommandGroup

from BotLib.funtions import find,converter,random_color,BRS
from core.classes import Cog_Extension
from BotLib.interface.user import *
from BotLib.database import JsonDatabase
from BotLib.basic import BotEmbed

class command(Cog_Extension):
    picdata = JsonDatabase().picdata
    rsdata = JsonDatabase().rsdata

    twitch = SlashCommandGroup("twitch", "Twitch相關指令")

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


    @commands.slash_command(description='抽卡試手氣')
    @commands.cooldown(rate=1,per=2)
    async def lottery(self,ctx,times:discord.Option(int,name='抽卡次數',description='可輸入1~1000的整數',default=1,min_value=1,max_value=1000)):
        result = {'six':0,'five':0,'four':0,'three':0}
        user_id = str(ctx.author.id)
        six_list = []
        six_list_100 = []
        guaranteed = 100
        jloot = Database().jloot
            
        for i in range(1,times+1):
            choice =  random.randint(1,100)
            if choice == 1 or jloot[user_id] >= guaranteed-1:
                result["six"] += 1
                if jloot[user_id] >= guaranteed-1:
                    six_list_100.append(str(i))
                else:
                    six_list.append(str(i))
                jloot[user_id] = 0
            else:
                if choice >= 2 and choice <= 11:
                    result["five"] += 1
                    jloot[user_id] += 1
                elif choice >= 12 and choice <= 41:
                    result["four"]+= 1
                    jloot[user_id] += 1
                else:
                    result["three"] += 1
                    jloot[user_id] += 1
        
        Database().write('jloot',jloot)
        embed=BotEmbed.lottery()
        embed.add_field(name='抽卡結果', value=f"六星:{result['six']} 五星:{result['five']} 四星:{result['four']} 三星:{result['three']}", inline=False)
        embed.add_field(name='保底累積', value=jloot[user_id], inline=False)
        if len(six_list) > 0:
            embed.add_field(name='六星出現', value=','.join(six_list), inline=False)
        if len(six_list_100) > 0:
            embed.add_field(name='保底', value=','.join(six_list_100), inline=False)
        await ctx.respond(embed=embed)


    # @commands.group(invoke_without_command=True)
    # async def bet(self,ctx,id,choice,money:int):
    #     bet_data = Database().bet_data
    #     money_now = Point(ctx.author.id).pt
    #     if id not in bet_data:
    #         await ctx.send('編號錯誤:沒有此編號的賭盤喔')
    #     elif bet_data[id]['Ison'] == 0:
    #         await ctx.send('錯誤:此賭盤已經關閉了喔')
    #     elif choice not in ['pink','blue']:
    #         await ctx.send('選擇錯誤:我不知道你要選擇什麼')
    #     elif money <= 0:
    #         await ctx.send('金額錯誤:無法輸入小於1的數字')
    #     elif money_now < money:
    #         await ctx.send('金額錯誤:你沒有那麼多點數')
    #     elif id == str(ctx.author.id):
    #         await ctx.send('錯誤:你不可以下注自己的賭盤')
    #     else:
    #         Point(ctx.author.id).add(money*-1)
    #         bet_data[id][choice]['member'][str(ctx.author.id)] += money
    #         Database().write('bet_data',bet_data)
    #         await ctx.send('下注完成!')


    # @bet.command()
    # async def create(self,ctx,title,pink,blue,time):
    #     bet_data = Database().bet_data
    #     id = str(ctx.author.id)
    #     sec = converter.time(time)
    #     if id in bet_data:
    #         await ctx.send('錯誤:你已經創建一個賭盤了喔')
    #         return
    #     elif sec > 600:
    #         await ctx.send('錯誤:時間太長了喔')
    #         return

    #     data = {}
    #     data['title'] = title
    #     data['IsOn'] = 1
    #     data['blue'] = {}
    #     data['blue']['title'] = blue
    #     data['blue']['member'] = {}
    #     data['pink'] = {}
    #     data['pink']['title'] = pink
    #     data['pink']['member'] = {}
    #     bet_data[id] = data        
    #     Database().write('bet_data',bet_data)
            
    #     embed = BotEmbed.simple(title='賭盤', description=f'編號: {id}')
    #     embed.add_field(name='賭盤內容', value=title, inline=False)
    #     embed.add_field(name="粉紅幫", value=pink, inline=False)
    #     embed.add_field(name="藍藍幫", value=blue, inline=False)
    #     await ctx.send(embed=embed)
    #     await asyncio.sleep(delay=sec)
        
    #     await ctx.send(f'編號{id}:\n下注時間結束')
    #     bet_data = Database().bet_data
    #     bet_data[id]['IsOn'] = 0
    #     Database().write('bet_data',bet_data)


    # @bet.command()
    # async def end(self,ctx,end):
    #     #錯誤檢測
    #     if end not in ['blue','pink']:
    #         await ctx.send('結果錯誤:我不知道到底是誰獲勝了呢')
    #         return
    #     id = str(ctx.author.id)
    #     bet_data = Database().bet_data
    #     if not bet_data[id]['IsOn']:
    #         await ctx.send('錯誤:此賭盤的開放下注時間尚未結束')
    #         return
    #     #計算雙方總點數
    #     pink_total = 0
    #     for i in bet_data[id]['pink']['member']:
    #         pink_total += bet_data[id]['pink']['member'][i]
    #     blue_total = 0
    #     for i in bet_data[id]['blue']['member']:
    #         blue_total += bet_data[id]['blue']['member'][i]
    #     #偵測是否兩邊皆有人下注
    #     if blue_total and pink_total:
    #         #獲勝者設定
    #         if end == 'pink':
    #             winner = bet_data[id]['pink']['member']
    #         else:
    #             winner = bet_data[id]['blue']['member']
    #         #前置準備
    #         if pink_total > blue_total:
    #             mag = pink_total / blue_total
    #         else:
    #             mag = blue_total / pink_total
    #         #結果公布
    #         if end == 'pink':
    #             await ctx.send(f'編號{id}:\n恭喜粉紅幫獲勝!')
    #         else:
    #             await ctx.send(f'編號{id}:\n恭喜藍藍幫獲勝!')
    #         #點數計算
    #         for i in winner:
    #             pt1 = winner[i] * (mag+1)
    #             Point(i).add(pt1)
            
    #     else:
    #         for i in bet_data[id]['blue']['member']:
    #             user = await find.user(ctx,i)
    #             id = str(user.id)
    #             Point(id).add(bet_data[id]['blue']['member'][id])
            
    #         for i in bet_data[id]['pink']['member']:
    #             user = await find.user(ctx,i)
    #             id = str(user.id)
    #             Point(id).add(bet_data[id]['pink']['member'][id])
    #         await ctx.send(f'編號{id}:\n因為有一方沒有人選擇，所以此局平手，點數將歸還給所有人')
    #     #更新資料庫
    #     del bet_data[id]
    #     Database().write('bet_data',bet_data)


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
    async def set(self,
                ctx,
                twitch_user:discord.Option(str,required=True,name='twitch用戶',description='當此用戶開台時會發送通知'),
                channel:discord.Option(discord.TextChannel,required=True,name='頻道',description='通知發送頻道'),
                role:discord.Option(discord.Role,required=True,name='身分組',description='發送通知時tag的身分組')
                ):
        db = Database()
        jtwitch = db.jtwitch
        channel = await find.channel(ctx,channel)
        if not channel:
            raise commands.errors.ArgumentParsingError('沒找到頻道')

        role = await find.role(ctx,role)
        if not role:
            raise commands.errors.ArgumentParsingError('沒找到身分組')            

        if twitch_user not in jtwitch['users']:
            jtwitch['users'].append(twitch_user)
            jtwitch['role'][twitch_user] = {}
            jtwitch['channel'][twitch_user] = {}

        jtwitch['role'][twitch_user][str(ctx.guild.id)] = str(role.id)
        jtwitch['channel'][twitch_user][str(ctx.guild.id)] = str(channel.id)

        db.write('jtwitch',jtwitch)
        await ctx.respond(f'設定成功：{twitch_user}的開台通知將會發送在{channel.mention}並會通知{role.mention}')

    @twitch.command(description='移除twitch開台通知')
    async def remove(self,ctx,twitch_user:discord.Option(str,required=True,name='twitch用戶')):
        db = Database()
        jtwitch = db.jtwitch
        if twitch_user in jtwitch['users'] and str(ctx.guild.id) in jtwitch['channel'][twitch_user]:
            jtwitch['users'].remove(twitch_user)
            del jtwitch['role'][twitch_user][str(ctx.guild.id)]
            if not jtwitch['role'][twitch_user]:
                del jtwitch['role'][twitch_user]

            del jtwitch['channel'][twitch_user][str(ctx.guild.id)]
            if not jtwitch['channel'][twitch_user]:
                del jtwitch['channel'][twitch_user]
            db.write('jtwitch',jtwitch)
            await ctx.respond(f'已移除 {twitch_user} 的開台通知')
        else:
            await ctx.respond(f'{twitch_user} 還沒有被設定通知')

    @twitch.command(description='確認twitch開台通知')
    async def notice(self,ctx,twitch_user:discord.Option(str,required=True,name='twitch用戶')):
        db = Database()
        jtwitch = db.jtwitch
        if twitch_user in jtwitch['users'] and str(ctx.guild.id) in jtwitch['channel'][twitch_user]:
            channel = self.bot.get_channel(int(jtwitch['channel'][twitch_user][str(ctx.guild.id)]))
            await ctx.respond(f'{twitch_user} 的開台通知在 {channel.mention}')
        else:
            await ctx.respond(f'{twitch_user} 在此群組沒有設開台通知')

def setup(bot):
    bot.add_cog(command(bot))