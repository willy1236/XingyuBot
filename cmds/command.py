import asyncio
import ctypes
import random
import re
import subprocess
from datetime import datetime, timedelta, timezone

import discord
import psutil
from discord.errors import Forbidden, NotFound
from discord.ext import commands,pages
from discord.commands import SlashCommandGroup
from mysql.connector.errors import Error as sqlerror

from starcord import Cog_Extension,Jsondb,BRS,log,BotEmbed,ChoiceList,sclient
from starcord.Utilities import find, random_color, create_only_role_list, create_role_magification_dict, calculate_eletion_session
from starcord.ui_element.button import Delete_Add_Role_button
from starcord.ui_element.view import PollView
from starcord.DataExtractor import GoogleCloud
from starcord.types import Coins
from cmds.bot_event import check_registration

bet_option = ChoiceList.set('bet_option')
position_option = ChoiceList.set('position_option')
party_option = ChoiceList.set('party_option')

main_guild = Jsondb.jdata.get('main_guild')

session = calculate_eletion_session()

position_role = {
    "1": 1161686745126019082,
    "2": 1161686757373399132,
    "3": 1162714634441195530,
    "4": 1187609355131027456
}

class command(Cog_Extension):
    bet = SlashCommandGroup("bet", "賭盤相關指令")
    role = SlashCommandGroup("role", "身分組管理指令")
    poll = SlashCommandGroup("poll", "投票相關指令")
    election = SlashCommandGroup("election", "選舉相關指令",guild_ids=main_guild)
    party = SlashCommandGroup("party", "政黨相關指令",guild_ids=main_guild)
    registration = SlashCommandGroup("registration", "戶籍相關指令",guild_ids=main_guild)

    @role.command(description='查詢身分組數')
    async def count(self,ctx,user_list:discord.Option(str,required=False,name='要查詢的用戶',description='多個用戶請用空格隔開，或可輸入default查詢常用人選')):
        await ctx.defer()
        if not user_list:
            user_list = [ctx.author.id]
        elif 'default' in user_list:
            user_list = [419131103836635136,528935362199027716,465831362168094730,539405949681795073,723435216244572160,490136735557222402]
        else:
            user_list = user_list.split()
        
        embed = BotEmbed.simple("身分組計算結果")
        for i in user_list:
            user = await find.user(ctx,i)
            if user:
                id = user.id
                record = sclient.sqldb.get_role_save_count(id)
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
            for user in user_list.split():
                user = await find.user(ctx,user)
                if user and user != self.bot.user:
                    try:
                        dbdata = sclient.sqldb.get_main_account(user.id)
                        if dbdata:
                            user = ctx.guild.get_member(dbdata['main_account'])
                    except sqlerror:
                        pass
                    
                    await user.add_roles(new_role,reason='指令:加身分組')
                    added_user.append(user.mention)
                    if ctx.guild.id == 613747262291443742 and not user.get_role(877934319249797120):
                        divider_role = ctx.guild.get_role(877934319249797120)
                        await user.add_roles(divider_role,reason='指令:加身分組')

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
    @commands.bot_has_permissions(manage_roles=True)
    async def save(self,
                   ctx:discord.ApplicationContext):
        await ctx.defer()
        guild = self.bot.get_guild(main_guild[0])
        
        for role in guild.roles:
            if role.id == 877934319249797120:
                break
            elif not role.is_default():
                for user in role.members:
                    try:
                        #1062
                        sclient.sqldb.add_role_save(user.id,role)
                        log.info(f'新增:{role.name}')
                    except sqlerror as e:
                        if e.errno != 1062:
                            log.warning(f'儲存身分組時發生錯誤：{role.name}')
                            raise
                            
        await ctx.respond('身分組儲存完成',delete_after=5)

    @role.command(description='清除身分組')
    @commands.is_owner()
    async def rsmove(self,ctx):
        await ctx.defer()
        guild = self.bot.get_guild(main_guild[0])
        if not guild.get_role(877934319249797120):
            await ctx.respond('錯誤：找不到"加身分組"',delete_after=5)
            return
        
        for role in guild.roles:
            if role.id == 877934319249797120:
                break
            if role.is_default():
                continue
            log.info(f'已移除:{role.name}')
            await role.delete()
            await asyncio.sleep(0.5)
        
        await ctx.respond('身分組清理完成',delete_after=5)

    # @role.command(description='更改暱稱')
    # @commands.bot_has_permissions(manage_roles=True)
    # async def nick(self, ctx, arg:discord.Option(str,name='欲更改的內容',description='可輸入新暱稱或輸入以#開頭的6位顏色代碼')):
    #     await ctx.defer()
    #     user = ctx.author
    #     role = user.roles[-1]
    #     if role.name.startswith('稱號 | '):
    #         if arg.startswith('#'):
    #             await role.edit(colour=arg,reason='稱號:顏色改變')
    #         else:
    #             await role.edit(name=f'稱號 | {arg}',reason='稱號:名稱改變')
    #         await ctx.respond('暱稱更改完成',delete_after=5)
    #     else:
    #         await ctx.respond(f'錯誤:{ctx.author.mention}沒有稱號可更改',delete_after=5)

    @role.command(description='身分組紀錄')
    async def record(self, ctx:discord.ApplicationContext, user:discord.Option(discord.Member,name='欲查詢的成員',description='留空以查詢自己',default=None)):
        await ctx.defer()
        user = user or ctx.author
        record = sclient.sqldb.get_role_save(user.id)
        if not record:
            raise commands.errors.ArgumentParsingError('沒有此用戶的紀錄')
        
        page:list[discord.Embed] = []
        i = 10
        for data in record:
            if i >= 10:
                page.append(BotEmbed.simple(f"{user.name} 身分組紀錄"))
                i = 0
            role_name = data['role_name']
            time = data['time']
            page[-1].add_field(name=role_name, value=time, inline=False)
            i += 1

        paginator = pages.Paginator(pages=page, use_default_buttons=True)
        await paginator.respond(ctx.interaction, ephemeral=False)
            
    
    @role.command(description='身分組排行榜')
    async def ranking(self, ctx,
                      ranking_count:discord.Option(int,name='排行榜人數',default=5,min_value=1,max_value=30)):
        await ctx.defer()
        dbdata = sclient.sqldb.get_role_save_count_list()
        sorted_data = sorted(dbdata.items(), key=lambda x:x[1])
        embed = BotEmbed.simple("身分組排行榜")
        for i in range(ranking_count):
            try:
                data = sorted_data[i]
                user = self.bot.get_user(data[0])
                username = user.mention if user else data[0]
                count = data[1]
                embed.add_field(name=f"第{i+1}名", value=f"{username} {count}個", inline=False)
            except IndexError:
                break
        await ctx.respond(embed=embed)

    @commands.slash_command(description='抽抽試手氣')
    @commands.cooldown(rate=1,per=2)
    async def draw(self,ctx,times:discord.Option(int,name='抽卡次數',description='可輸入1~1000的整數',default=1,min_value=1,max_value=1000)):
        result = {'six':0,'five':0,'four':0,'three':0}
        user_id = str(ctx.author.id)
        six_list = []
        six_list_100 = []
        guaranteed = 100
        
        dbuser = sclient.sqldb.get_partial_dcuser(user_id,"guaranteed")
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
        for _ in range(dice_n):
            sum += random.randint(1,dice)
        await ctx.respond(f'{dice_n}d{dice} 結果：{sum}')


    @bet.command(description='賭盤下注')
    async def place(self,ctx,
                    bet_id:discord.Option(str,name='賭盤',description='',required=True),
                    choice:discord.Option(str,name='下注顏色',description='',required=True,choices=bet_option),
                    money:discord.Option(int,name='下注點數',description='',required=True,min_value=1)):
        if bet_id == ctx.author.id:
            await ctx.respond('錯誤：你不可以下注自己的賭盤',ephemeral=True)
            return
        
        bet = sclient.sqldb.get_bet_data(bet_id)
        if not bet:
            await ctx.respond('編號錯誤：沒有此編號的賭盤喔',ephemeral=True)
            return
        elif not bet['Ison']:
            await ctx.respond('錯誤：此賭盤已經關閉了喔',ephemeral=True)
            return
        
        user_data = sclient.sqldb.get_coin(str(ctx.author.id),Coins.POINT)

        if user_data['point'] < money:
            await ctx.respond('點數錯誤：你沒有那麼多點數',ephemeral=True)
            return

        sclient.sqldb.update_coins(str(ctx.author.id),'add',Coins.POINT,money*-1)
        sclient.sqldb.place_bet(bet_id,choice,money)
        await ctx.respond('下注完成!')


    @bet.command(description='創建賭盤')
    async def create(self,ctx,
                     title:discord.Option(str,name='賭盤標題',description='',required=True),
                     pink:discord.Option(str,name='粉紅幫標題',description='',required=True),
                     blue:discord.Option(str,name='藍藍幫標題',description='',required=True),
                     time:discord.Option(int,name='賭盤開放時間',description='',required=True,min_value=10,max_value=600)):
        bet_id = str(ctx.author.id)
        bet = sclient.sqldb.get_bet_data(bet_id)
        if bet:
            await ctx.respond('錯誤：你已經創建一個賭盤了喔',ephemeral=True)
            return

        sclient.sqldb.create_bet(bet_id,title,pink,blue)
            
        embed = BotEmbed.simple(title='賭盤', description=f'編號: {bet_id}')
        embed.add_field(name='賭盤內容', value=title, inline=False)
        embed.add_field(name="粉紅幫", value=pink, inline=False)
        embed.add_field(name="藍藍幫", value=blue, inline=False)
        await ctx.respond(embed=embed)
        await asyncio.sleep(delay=time)
        
        await ctx.send(f'編號{bet_id}：下注時間結束')
        sclient.sqldb.update_bet(bet_id)


    @bet.command(description='結束賭盤')
    async def end(self,ctx,end:discord.Option(str,name='獲勝下注顏色',description='',required=True,choices=bet_option)):
        bet_id = str(ctx.author.id)
        #錯誤檢測
        bet = sclient.sqldb.get_bet_data(bet_id)
        if bet['IsOn']:
            await ctx.respond('錯誤：此賭盤的開放下注時間尚未結束',ephemeral=True)
            return
        
        #計算雙方總點數
        total = sclient.sqldb.get_bet_total(bet_id)
        
        #偵測是否兩邊皆有人下注
        if total[0] and total[1]:
            #獲勝者設定
            winners = sclient.sqldb.get_bet_winner(bet_id,end)
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
                sclient.sqldb.update_coins(i['user_id'],'add',Coins.POINT,pt_add)
            
        else:
            users = sclient.sqldb.get_bet_winner(bet_id,'blue')
            for i in users:
                sclient.sqldb.update_coins(i['user_id'],'add',Coins.POINT,i['money'])
            
            users = sclient.sqldb.get_bet_winner(bet_id,'pink')
            for i in users:
                sclient.sqldb.update_coins(i['user_id'],'add',Coins.POINT,i['money'])
            await ctx.respond(f'編號{bet_id}：因為有一方沒有人選擇，所以此局平手，點數將歸還給所有人')
        
        #更新資料庫
        sclient.sqldb.remove_bet(bet_id)    

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
        time = timedelta(seconds=10)
        await member.timeout_for(time,reason="指令：禁言10秒")
        await ctx.respond(f"已禁言{member.mention} 10秒",ephemeral=True)
    
    #@commands.user_command(name="不想理你生態區",guild_ids=main_guild)
    @commands.user_command(name="懲戒集中營",guild_ids=main_guild)
    #@commands.has_permissions(moderate_members=True)
    async def user_command2(self,ctx, member: discord.Member):
        await ctx.respond(f"開始執行",ephemeral=True)
        
        role = ctx.guild.get_role(1195407446315892888)
        member.add_roles(role,reason="指令：懲戒集中營 開始")
        
        time = timedelta(seconds=20)
        embed = BotEmbed.simple_warn_sheet(member,ctx.author,last=time,reason="懲戒集中營",title="已被懲戒")
        await self.bot.get_channel(1195406858056368189).send(embed=embed)
        
        channel = self.bot.get_channel(613760923668185121)
        for i in range(40):
            if member.voice and member.voice.channel != channel:
                await member.move_to(channel)
            await asyncio.sleep(0.5)
        member.remove_roles(role,reason="指令：懲戒集中營 結束")

    @commands.slash_command(description='傳送訊息給機器人擁有者')
    @commands.cooldown(rate=1,per=10)
    async def feedback(self,
                       ctx:discord.ApplicationContext,
                       text:discord.Option(str,name='訊息',description='要傳送的訊息內容，歡迎提供各項建議')):
        await ctx.defer()
        await BRS.feedback(self.bot,ctx,text)
        await ctx.respond(f"訊息已發送!",ephemeral=True,delete_after=3)

    @staticmethod
    def Autocomplete(self: discord.AutocompleteContext):
        return ['test']

    @commands.slash_command(description='讓機器人選擇一樣東西')
    async def choice(self,ctx,args:discord.Option(str,name='選項',description='多個選項請用空格隔開')):
        args = args.split()
        result = random.choice(args)
        await ctx.respond(f'我選擇:{result}')

    @commands.user_command(name="摃殘",guild_ids=main_guild)
    async def bonk(self,ctx:discord.ApplicationContext, member: discord.Member):
        if not ctx.user.get_role(1178151415403790478):
            await ctx.respond(f"你不是台中摃殘黨員",ephemeral=True)
            return
        
        member.timeout_for(duration=timedelta(seconds=10),reason="bonk")
        await ctx.respond(f"{member.mention}：bonk")

    @poll.command(description='創建投票')
    async def create(self,
                     ctx:discord.ApplicationContext,
                     title:discord.Option(str,name='標題',description='投票標題，限45字內'),
                     options:discord.Option(str,name='選項',description='投票選項，最多輸入20項，每個選項請用英文,隔開'),
                     show_name:discord.Option(bool,name='顯示投票人',description='預設為false，若投票人數多建議關閉',default=False),    
                     check_results_in_advance:discord.Option(bool,name='預先查看結果',description='預設為true',default=True),
                     results_only_initiator:discord.Option(bool,name='僅限發起人能查看結果',description='預設為false',default=False),
                     ban_alternate_account_voting:discord.Option(bool,name='是否禁止小帳投票',description='僅供特定群組使用，預設為false',default=False),
                     number_of_user_votes:discord.Option(int,name='一人最多可投票數',description='預設為1',default=1, min_value=1, max_value=20),
                     only_role:discord.Option(str,name='限制身分組',description='若提供。則只有擁有身分組才能投票，多個身分組以英文,隔開，身分組可輸入id、提及、名稱等',default=None),
                     role_magnification:discord.Option(str,name='身分組權重',description='若提供，擁有身分組的用戶票數將乘指定倍數，取最高，格式為：身分組1,權重,身分組2,權重...，身分組可輸入id、提及、名稱等',default=None),
                     ):
        options = options.split(",")
        if len(options) > 20 or len(options) < 1:
            await ctx.respond(f"錯誤：投票選項超過20項或小於1項",ephemeral=True)
            return  
        
        only_role_list = await create_only_role_list(only_role,ctx) if only_role else []
        role_magnification_dict = await create_role_magification_dict(role_magnification,ctx) if role_magnification else {}

        view = sclient.create_poll(title,options,ctx.author.id,ctx.guild.id,ban_alternate_account_voting,show_name,check_results_in_advance,results_only_initiator,number_of_user_votes,only_role_list=only_role_list,role_magnification_dict=role_magnification_dict)
        embed = view.embed(ctx.guild)
        message = await ctx.respond(embed=embed,view=view)
        sclient.sqldb.update_poll(view.poll_id,"message_id",message.id)

    @commands.is_owner()
    @poll.command(description='重新創建投票介面')
    async def view(self,ctx,
                   poll_id:discord.Option(int,name='投票id',description='')):
        dbdata = sclient.sqldb.get_poll(poll_id)
        if dbdata:
            view = PollView(dbdata['poll_id'],sqldb=sclient.sqldb)    
            await ctx.respond(view=view,embed=view.embed(ctx.guild))
        else:
            await ctx.respond("錯誤：查無此ID")

    @commands.is_owner()
    @poll.command(description='取得投票結果')
    async def result(self,ctx:discord.ApplicationContext,
                   poll_id:discord.Option(int,name='投票id',description='')):
        await ctx.defer()
        view = PollView(poll_id,sclient.sqldb,self.bot)
        embed = view.results_embed(ctx.interaction)
        await ctx.respond(embed=embed)

    @commands.slash_command(description='共用「94共用啦」雲端資料夾',guild_ids=main_guild)
    async def drive(self,ctx,email:discord.Option(str,name='gmail帳戶',description='要使用的Gmail帳戶，留空以移除資料',required=False)):
        await ctx.defer()
        suser = sclient.sqldb.get_user(ctx.author.id)
        fileId = "1bDtsLbOi5crIOkWUZbQmPq3dXUbwWEan"
        if not email:
            if suser and suser.email:
                GoogleCloud().remove_file_permissions(fileId, suser.drive_share_id)
                sclient.sqldb.remove_sharefolder_data(ctx.author.id)
            else:
                await ctx.respond(f"{ctx.author.mention}：此帳號沒有設定過google帳戶")
                return
        
        if suser and suser.drive_share_id:
            await ctx.respond(f"{ctx.author.mention}：此帳號已經共用雲端資料夾了")
            return
        
        r = re.compile(r"@gmail.com")
        if not r.search(email):
            await ctx.respond(f"{ctx.author.mention}：Gmail格式錯誤")
            return
        
        google_data = GoogleCloud().add_file_permissions(fileId,email)
        sclient.sqldb.set_sharefolder_data(ctx.author.id, email, google_data["id"])
        await ctx.respond(f"{ctx.author.mention}：已與 {email} 共用雲端資料夾")

    @election.command(description='加入選舉')
    async def join(self, ctx,
                   position:discord.Option(int,name='職位',description='要競選的職位',choices=position_option),
                   user_dc:discord.Option(discord.Member,name='成員',description='要競選的成員（此選項供政黨代表統一報名用）',required=False),
                   party_id:discord.Option(int,name='代表政黨',description='如果有多個政黨，可選擇要代表的政黨',default=None,choices=party_option)):
        user_dc = user_dc or ctx.author

        if party_id:
            dbdata = sclient.sqldb.get_user_party(user_dc.id)
            joined_party = [party_data.get("party_id") for party_data in dbdata] if dbdata else []
            if not party_id in joined_party:
                await ctx.respond(f"{user_dc.mention}：你沒有參加 {ChoiceList.get_tw(party_id,'party_option')}")
                return
        
        sclient.sqldb.add_election(user_dc.id,session + 1,position,party_id)
        await ctx.respond(f"{user_dc.mention}：完成競選報名 {ChoiceList.get_tw(position,'position_option')}")
        

    @election.command(description='離開選舉')
    async def leave(self, ctx, 
                    position:discord.Option(str,name='職位',description='要退選的職位',choices=position_option)):
        sclient.sqldb.remove_election(ctx.author.id,session + 1,position)
        
        text = f"{ctx.author.mention}：完成競選退出"
        if position:
            text += " " + ChoiceList.get_tw(position,'position_option')
        await ctx.respond(text)

    @election.command(description='候選人名單')
    @commands.is_owner()
    async def format(self, ctx, last:discord.Option(bool,name='上屆候選人名單',description='是否顯示上屆候選人名單',default=False)):
        await ctx.defer()
        embed = sclient.election_format(session if last else session + 1, self.bot)
        await ctx.respond(embed=embed)

    @election.command(description='開始投票')
    @commands.is_owner()
    async def start(self,ctx:discord.ApplicationContext):
        await ctx.defer()
        dbdata = sclient.sqldb.get_election_full_by_session(session)
        results = {}
        for position in Jsondb.options["position_option"].keys():
            results[position] = []
        
        for data in dbdata:
            user_id = data['discord_id']
            #party_name = i['party_name'] or "無黨籍"
            position = str(data['position'])
            
            user = ctx.guild.get_member(user_id)
            username = user_id if not user else (user.display_name if user.display_name else (user.global_name if user.global_name else user.name))
            if username not in results[position]:
                results[position].append(username)

        # count_data = sclient.get_election_count(session)
        # count_dict = {}
        # for data in count_data:
        #     pos = data['position']
        #     count = data['count']
        #     count_dict[pos] = count

        for position in Jsondb.options["position_option"].keys():
            #count = count_dict[position]
            if len(results[position]) <= 0:
                continue

            position_name = ChoiceList.get_tw(position, "position_option")
            title = f"第{session}屆中央選舉：{position_name}"
            #options = [f"{i}號" for i in range(1,count + 1)]
            i = 1
            options = []
            for username in results[position]:
                options.append(f"{i}號 {username}" )
                i += 1

            view = sclient.create_election_poll(title, options, self.bot.user.id, ctx.guild.id, self.bot)

            message = await ctx.send(embed=view.embed(ctx.guild),view=view)
            await asyncio.sleep(1)
        await ctx.respond(f"第{session}屆中央選舉投票創建完成")

        tz = timezone(timedelta(hours=8))
        start_time = datetime.now(tz)
        if start_time.hour < 20:
            end_time = datetime(start_time.year,start_time.month,start_time.day,20,0,0,tzinfo=tz)
        else:
            end_time = start_time + timedelta(days=1)
        
        start_time += timedelta(seconds=10)
        event = await ctx.guild.create_scheduled_event(name="【快樂營中央選舉】投票階段",start_time=start_time,end_time=end_time,location="<#1163127708839071827>")

    @election.command(description='結算選舉')
    @commands.is_owner()
    async def end(self,
                  ctx:discord.ApplicationContext,
                  officials:discord.Option(str,name='官員清單',description='多人以空格分隔，職位以,分隔並按順序排列，若該職位從缺請留空')
                  ):
        await ctx.defer()
        session = calculate_eletion_session()
        officials = officials.split(",")
        
        if len(officials) != 4:
            await ctx.respond("錯誤：官員清單不完整")
            return

        # 移除身分組
        for roleid in position_role.values():
            role = ctx.guild.get_role(roleid)
            if not role:
                continue
            for user in role.members:
                await user.remove_roles(role,reason=f"第{session}界官員卸任")
                await asyncio.sleep(0.5)
        
        # 製作當選官員名單並分配身分組
        dct = {}
        save_list = []
        for n in Jsondb.options["position_option"].keys():
            lst = []
            roleid = position_role[n]
            role = ctx.guild.get_role(roleid)

            for user in officials[int(n) - 1].split(" "):
                user = await find.user(ctx, user)
                if not user:
                    continue
                
                lst.append(user)
                save_list.append([user.id, session, n])
                if role:
                    await user.add_roles(role,reason=f"第{session}屆官員當選")
                    await asyncio.sleep(0.5)

            dct[n] = lst
        
        # 輸出當選官員名單
        now = datetime.now()
        text = f'# 第{session}屆中央政府（{now.strftime("%Y-%m")}）'
        for n, userlist in Jsondb.options["position_option"].items():
            text += f"\n{ChoiceList.get_tw(n,'position_option')}：{' '.join(userlist)}"
        
        #lab = Legal Affairs Bureau
        sclient.sqldb.add_officials(save_list)
        lab_channel = self.bot.get_channel(1160467781473533962)
        await lab_channel.send(text)
        await ctx.respond("結算完成，恭喜當選者")

    @party.command(description='加入政黨')
    async def join(self,ctx:discord.ApplicationContext,
                    party_id:discord.Option(int,name='政黨',description='要參加的政黨',choices=party_option)):
        sclient.sqldb.join_party(ctx.author.id,party_id)
        dbdata = sclient.sqldb.get_party_data(party_id)
        role_id = dbdata["role_id"]
        try:
            role = ctx.guild.get_role(role_id)
            if role:
                await ctx.author.add_roles(role)
        except:
            pass

        await ctx.respond(f"{ctx.author.mention} 已加入政黨 {ChoiceList.get_tw(party_id,'party_option')}")

    @party.command(description='離開政黨')
    async def leave(self,ctx:discord.ApplicationContext,
                    party_id:discord.Option(int,name='政黨',description='要離開的政黨',choices=party_option)):
        sclient.sqldb.leave_party(ctx.author.id,party_id)
        dbdata = sclient.sqldb.get_party_data(party_id)
        role_id = dbdata["role_id"]
        try:
            role = ctx.author.get_role(role_id)
            if role:
                await ctx.author.remove_roles(role)
        except:
            pass

        await ctx.respond(f"{ctx.author.mention} 已退出政黨 {ChoiceList.get_tw(party_id,'party_option')}")

    @party.command(description='政黨列表')
    async def list(self,ctx:discord.ApplicationContext):
        dbdata = sclient.sqldb.get_all_party_data()
        embed = BotEmbed.simple("政黨統計")
        for party in dbdata:
            creator = self.bot.get_user(party['creator_id'])
            creator_mention = creator.mention if creator else f"<@{party['creator_id']}>"
            embed.add_field(name=party["party_name"], value=f"政黨ID：{party['party_id']}\n政黨人數：{party['count']}\n創黨人：{creator_mention}")
        await ctx.respond(embed=embed)

    @commands.slash_command(description="開啟mc伺服器",guild_ids=main_guild)
    @commands.cooldown(rate=1,per=120)
    async def startserver(self,ctx:discord.ApplicationContext):
        def is_bat_running(bat_name:str):
            bat_name = bat_name.lower()
            for proc in psutil.process_iter():
                try:
                    if proc.name().lower() == bat_name:
                        return True
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
            return False

        file_path = r'D:\minecraft_server\1.20.1_yeecraft\start.bat'
        if is_bat_running("java.exe"):
            await ctx.respond("伺服器已開啟")
        else:
            subprocess.call(file_path)
            await ctx.respond("已發送開啟指令")

    @registration.command(description='確認/更新戶籍')
    @commands.cooldown(rate=1,per=10)
    async def update(self,ctx):
        user = sclient.sqldb.get_dcuser(ctx.author.id)
        if user.registration:
            await ctx.respond("你已經註冊戶籍了")
            return

        guild_id = check_registration(ctx.author)
        if guild_id:
            guild = self.bot.get_guild(guild_id)
            dbdata = sclient.sqldb.get_resgistration_by_guildid(guild_id)
            role_guild = self.bot.get_guild(613747262291443742)
            role = role_guild.get_role(dbdata['role_id'])

            if role:
                await role_guild.get_member(ctx.author.id).add_roles(role)
            sclient.sqldb.set_userdata(ctx.author.id,"user_discord","discord_registration",dbdata['registrations_id'])
            
            await ctx.respond(f"已註冊戶籍至 {guild.name}")
        else:
            await ctx.respond("你沒有可註冊的戶籍")

    @registration.command(description='設定戶籍')
    @commands.is_owner()
    @commands.cooldown(rate=1,per=10)
    async def set(self,ctx,
                     user:discord.Option(discord.Member,name='用戶'),
                     registrations_id:discord.Option(int,name='戶籍id')):
        dbdata = sclient.sqldb.get_resgistration(registrations_id)
        guild = self.bot.get_guild(dbdata['guild_id'])
        
        role_guild = self.bot.get_guild(613747262291443742)
        role = role_guild.get_role(dbdata['role_id'])

        if role:
            await role_guild.get_member(ctx.author.id).add_roles(role)
        sclient.sqldb.set_userdata(ctx.author.id,"user_discord","discord_registration",dbdata['registrations_id'])
        
        await ctx.respond(f"已註冊戶籍至 {guild.name}")

    @commands.slash_command(description="紀錄身分組")
    @commands.is_owner()
    async def registerrole(self,ctx,
                           role:discord.Option(discord.Role,name='保存的身分組'),
                           description:discord.Option(str,name='描述',description="保存的身分組描述",required=False),
                           delete_role:discord.Option(bool,name='保存後是否刪除身分組',default=False),
                           remove_member:discord.Option(bool,name='保存後是否清空身分組成員',default=False)):
        sclient.sqldb.backup_role(role,description)
        await ctx.respond(f"已將 {role.name} 身分組儲存")
        
        #身分組儲存後執行確保資料完整
        if delete_role:
            await role.delete()
            await ctx.send(f"已將 {role.name} 刪除")
        elif remove_member:
            for member in role.members:
                await member.remove_roles(role)
                await asyncio.sleep(1)
            await ctx.send(f"已將 {role.name} 成員清空")

    @commands.slash_command(description="取得邀請連結")
    async def getinvite(self, ctx,
                        invite_url:discord.Option(str,name='邀請連結網址')):
        invite = await self.bot.fetch_invite(invite_url)
        guild = self.bot.get_guild(invite.guild.id)
        embed = BotEmbed.simple("邀請連結")
        embed.add_field(name="伺服器名稱",value=invite.guild.name)
        
        if guild:
            invite = next((i for i in await guild.invites() if i.code == invite.code), invite)
            embed.add_field(name="伺服器人數",value=invite.guild.member_count)
            embed.add_field(name="邀請人",value=invite.inviter.mention)
            embed.add_field(name="邀請頻道",value=invite.channel.name)
            embed.add_field(name="邀請次數",value=f"{invite.uses}/{invite.max_uses if invite.max_uses else '無限制'}")
            embed.add_field(name="臨時成員",value=invite.temporary  )
            created_str = f"<t:{int(invite.created_at.timestamp())}>" if invite.created_at else "未知"
            embed.add_field(name="創建於",value=created_str)
        else:
            embed.add_field(name="伺服器人數",value=invite.approximate_member_count)
            embed.add_field(name="邀請人",value=invite.inviter.mention)
            embed.add_field(name="邀請頻道",value=invite.channel.name)
            embed.add_field(name="邀請次數",value=f"未知/{invite.max_uses if invite.max_uses else '無限制'}")
            embed.add_field(name="臨時成員",value="未知")
            embed.add_field(name="創建於",value="未知")
            embed.set_footer(text="邀請機器人加入獲取完整資訊")

        expires_str = f"<t:{int(invite.expires_at.timestamp())}>" if invite.expires_at else "無"
        embed.add_field(name="過期於",value=expires_str)
        embed.add_field(name="伺服器邀請連結",value=invite.url,inline=False)
        if invite.guild.icon:
            embed.set_thumbnail(url=invite.guild.icon.url)
        await ctx.respond(embed=embed)

def setup(bot):
    bot.add_cog(command(bot))