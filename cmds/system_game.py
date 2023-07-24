import discord,genshin,re,asyncio
from discord.ext import commands
from discord.commands import SlashCommandGroup
from datetime import timedelta

from core.classes import Cog_Extension
from starcord import BotEmbed,Jsondb,ChoiceList
from starcord.clients.game import *
from starcord.type.game import DatabaseGame

# def player_search(url):
#     response = requests.get(url)
#     soup = BeautifulSoup(response.text, "html.parser")
#     results = soup.find_all("h1",class_="row")

#     for result in results:
#         if result.div.string == None:
#             result2 = str(result.div)[166:]
#             lvl = ''.join([x for x in result2 if x.isdigit()])
#             return lvl

set_option = ChoiceList.set('game_set_option')
hoyo_game_option = [
    discord.OptionChoice(name='原神',value=genshin.Game.GENSHIN),
    discord.OptionChoice(name='崩壞3rd',value=genshin.Game.HONKAI),
    discord.OptionChoice(name='崩壞：星穹軌道',value=genshin.Game.STARRAIL)
]

debug_guild = Jsondb.jdata.get('debug_guild')
jdata = Jsondb.jdata

class system_game(Cog_Extension):
    game = SlashCommandGroup("game", "遊戲資訊相關指令")
    lol = SlashCommandGroup("lol", "League of Legends相關指令")
    osu = SlashCommandGroup("osu", "Osu相關指令")
    apex = SlashCommandGroup("apex", "Apex相關指令")
    dbd = SlashCommandGroup("dbd", "Dead by Daylight相關指令")
    steam = SlashCommandGroup("steam", "Steam相關指令")
    hoyo = SlashCommandGroup("hoyo", "MiHaYo相關指令")
        
    @game.command(description='設定遊戲資料')
    async def set(self,ctx,
                  game:discord.Option(str,name='遊戲',description='要設定的遊戲',required=True,choices=set_option),
                  value:discord.Option(str,name='資料',description='要設定的資料，留空以移除資料',default=None)):
        await ctx.defer()
        id = str(ctx.author.id)
        if not value:
            self.sqldb.remove_game_data(id,game)
            await ctx.respond(f'已將{game}資料移除')
            return

        player_name = None
        player_id = None
        account_id = None
        other_id = None

        game = DatabaseGame(game)
        unneed_verify = []
        if game in unneed_verify:
            player_name = value
        
        elif game == DatabaseGame.STEAM:
            APIdata = SteamInterface().get_user(value)
            if APIdata:
                player_name = APIdata.name
                player_id = APIdata.id,
            else:
                await ctx.respond(f'錯誤:找不到此用戶',ephemeral=True)
                return
        
        elif game == DatabaseGame.LOL:
            APIdata = RiotInterface().get_lolplayer(value)
            if APIdata:
                player_name = APIdata.name
                player_id = APIdata.summonerid
                account_id = APIdata.accountid
                other_id = APIdata.puuid
            else:
                await ctx.respond(f'錯誤:找不到此用戶',ephemeral=True)
                return

        elif game == DatabaseGame.APEX:
            APIdata = ApexInterface().get_player(value)
            if APIdata:
                player_name = APIdata.name
                player_id = APIdata.id
            else:
                await ctx.respond(f'錯誤:找不到此用戶',ephemeral=True)
                return

        elif game == DatabaseGame.OSU:
            APIdata = OsuInterface().get_player(value)
            if APIdata:
                player_name = APIdata.name
                player_id = APIdata.id
            else:
                await ctx.respond(f'錯誤:找不到此用戶',ephemeral=True)
                return

        self.sqldb.set_game_data(id,game.value,player_name,player_id,account_id,other_id)
        await ctx.respond(f'已將用戶的 {game.name} 資料設定為 {player_name}')
            

    @game.command(description='查詢遊戲資料')
    async def find(self,ctx,
                   user:discord.Option(discord.Member,name='用戶',description='要查詢的用戶',default=None),
                   game:discord.Option(str,name='遊戲',description='若輸入此欄，將會用資料庫的資料查詢玩家',default=None,choices=set_option)):
        await ctx.defer()
        user = user or ctx.author
        userid = str(user.id)
        
        if game:
            dbdata = self.sqldb.get_game_data(userid,game)
            if dbdata:
                game = DatabaseGame(game)
                if game == DatabaseGame.STEAM:
                    APIdata = SteamInterface().get_user(dbdata['player_id'])
                elif game == DatabaseGame.OSU:
                    APIdata = OsuInterface().get_player(dbdata['player_name'])
                elif game == DatabaseGame.APEX:
                    APIdata = ApexInterface().get_player(dbdata['player_name'])
                elif game == DatabaseGame.LOL:
                    APIdata = RiotInterface().get_lolplayer(dbdata['player_name'])
            else:
                await ctx.respond(f'錯誤:資料庫中查無資料',ephemeral=True)

            if APIdata:
                await ctx.respond(f'查詢成功',embed=APIdata.desplay())
            else:
                await ctx.respond(f'錯誤:找不到此用戶',ephemeral=True)
            return

        if not (user == ctx.author or self.bot.is_owner(ctx.author)):
            await ctx.respond('目前不開放查詢別人的綜合資料喔',ephemeral=True)
            return
            
        record = self.sqldb.get_game_data(userid)
        if record:
            embed = BotEmbed.simple(title=user)
            for r in record:
                game = r['game']
                name = r['player_name']
                embed.add_field(name=game, value=name, inline=False)
            embed.set_thumbnail(url=user.display_avatar.url)
            await ctx.respond(embed=embed)
        else:
            await ctx.respond('無法查詢此人的資料，可能是用戶尚未註冊資料庫',ephemeral=True)

    # @lol.command(description='查詢League of Legends用戶資料')
    # async def user(self,ctx,userid:discord.Option(str,name='用戶',description='要查詢的用戶')):
    #     url = 'https://lol.moa.tw/summoner/show/'+userid
    #     lvl = player_search(url) or '讀取失敗'

    #     embed = discord.Embed(title="LOL玩家查詢", url=url, color=0xc4e9ff)
    #     embed.add_field(name="玩家名稱", value=userid, inline=False)
    #     embed.add_field(name="等級", value=lvl, inline=False)
    #     embed.add_field(name="查詢戰績", value="LOL戰績網(lol.moa.tw)", inline=False)
    #     embed.set_thumbnail(url='https://i.imgur.com/B0TMreW.png')
    #     await ctx.respond(embed=embed)

    @lol.command(description='查詢League of Legends用戶資料')
    async def user(self,ctx,username:discord.Option(str,name='用戶名稱',description='要查詢的用戶')):
        player = RiotInterface().get_lolplayer(username)
        if player:
            await ctx.respond('查詢成功',embed=player.desplay())
        else:
            await ctx.respond('查詢失敗:查無此ID',ephemeral=True)

    @lol.command(description='查詢League of Legends對戰資料')
    async def match(self,ctx,matchid:discord.Option(str,name='對戰id',description='要查詢的對戰')):
        match = RiotInterface().get_lol_match(matchid)
        if match:
            await ctx.respond('查詢成功',embed=match.desplay())
        else:
            await ctx.respond('查詢失敗:查無此ID',ephemeral=True)

    @lol.command(description='查詢最近一次的League of Legends對戰')
    async def playermatch(self,ctx,username:discord.Option(str,name='用戶名稱',description='要查詢的用戶，留空則使用資料庫查詢',required=False)):
        if not username:
            dbdata = self.sqldb.get_game_data(str(ctx.author.id),DatabaseGame.LOL.value)
            if not dbdata:
                await ctx.respond('查詢失敗:沒有登入資料庫的資料',ephemeral=True)
                return
            puuid = dbdata['puuid']
        else:
            player = RiotInterface().get_lolplayer(username)
            if not player:
                await ctx.respond('查詢失敗:查無此玩家',ephemeral=True)
                return
            puuid = player.puuid
        
        match_list = RiotInterface().get_lol_player_match(puuid,1)
        if not match_list:
            await ctx.respond('查詢失敗:此玩家查無對戰紀錄',ephemeral=True)
            return
        
        match = RiotInterface().get_lol_match(match_list[0])
        if match:
            await ctx.respond('查詢成功',embed=match.desplay())
        else:
            await ctx.respond('查詢失敗：出現未知錯誤',ephemeral=True)
            

    @osu.command(description='查詢Osu用戶資料')
    @commands.cooldown(rate=1,per=1)
    async def user(self,ctx,
                   username:discord.Option(str,name='玩家名稱',description='要查詢的玩家',default=None)):
        player = OsuInterface().get_player(username)
        if player:
            await ctx.respond('查詢成功',embed=player.desplay())
        else:
            await ctx.respond('查詢失敗:查無此玩家',ephemeral=True)

    @osu.command(description='查詢Osu圖譜資料')
    @commands.cooldown(rate=1,per=1)
    async def map(self,ctx,
                  mapid:discord.Option(str,name='圖譜id',description='要查詢的圖譜ID',default=None)):
        map = OsuInterface().get_beatmap(mapid)
        if map:
            await ctx.respond('查詢成功',embed=map.desplay())
        else:
            await ctx.respond('查詢失敗:查無此圖譜',ephemeral=True)

    @apex.command(description='查詢Apex玩家資料')
    @commands.cooldown(rate=1,per=3)
    async def user(self,
                   ctx:discord.ApplicationContext,
                   username:discord.Option(str,name='玩家名稱',description='要查詢的玩家')):
        player = ApexInterface().get_player(username)
        if player:
            await ctx.respond(content='查詢成功',embed=player.desplay())
        else:
            await ctx.respond(content='查詢失敗:查無此ID',ephemeral=True)

    @apex.command(description='查詢Apex地圖資料')
    @commands.cooldown(rate=1,per=3)
    async def map(self,ctx):
        embed = ApexInterface().get_map_rotation().desplay()
        await ctx.respond(content='查詢成功',embed=embed)

    @apex.command(description='查詢Apex合成器內容資料')
    @commands.cooldown(rate=1,per=3)
    async def crafting(self,ctx):
        embed = ApexInterface().get_crafting().desplay()
        await ctx.respond(content='查詢成功',embed=embed)

    # @apex.command(description='查詢Apex伺服器資料',enabled=False)
    # @commands.cooldown(rate=1,per=3)
    # async def server(self,ctx):
    #     return await ctx.respond(content='暫未開放')
    #     embed = ApexInterface().get_server_status().desplay()
    #     await ctx.respond(content='查詢成功',embed=embed)

    @dbd.command(description='查詢Dead by daylight玩家資料')
    @commands.cooldown(rate=1,per=1)
    async def user(self,ctx,
                   userid:discord.Option(str,name='steamid',description='要查詢的玩家id',default=None)):        
        player = DBDInterface().get_player(userid)
        if player:
            await ctx.respond(content='查詢成功',embed=player.desplay())
        else:
            await ctx.respond(content='查詢失敗:查無此ID或個人資料設定私人',ephemeral=True)

    @steam.command(description='查詢Steam用戶資料')
    @commands.cooldown(rate=1,per=1)
    async def user(self,ctx,
                userid:discord.Option(str,name='用戶id',description='要查詢的用戶',default=None)):
        user = SteamInterface().get_user(userid)
        if user:
            await ctx.respond(content='查詢成功',embed=user.desplay())
        else:
            await ctx.respond(content='查詢失敗:查無此ID',ephemeral=True)


    @hoyo.command(description='如何設定cookies(需先設定才能使用其他功能)')
    @commands.cooldown(rate=1,per=1)
    async def help(self,ctx):
        embed = BotEmbed.simple(description="1.前往 https://www.hoyolab.com/ 並登入\n2.複製以下代碼```script:d=document.cookie; c=d.includes('account_id') || alert('過期或無效的Cookie,請先登出帳號再重新登入!'); c && document.write(d)```\n3.在網址列打上java後直接貼上複製的代碼\n4.找到`ltuid=`跟`ltoken=`並複製其中的內容\n5.使用指令 </hoyo set:1045323352421711947>")
        embed2 = BotEmbed.simple(description="擁有此cookie將可以使機器人以登入帳號的身分瀏覽與操作hoyolab的相關功能，但無法用於登入遊戲與改變遊戲中所持有的內容。\n若對此功能有疑慮，可隨時終止使用，cookie也可以隨時刪除，但米哈遊沒有官方正式API，故若不提供cookie將會無法使用相關功能。")
        await ctx.respond(embeds=[embed,embed2])

    @hoyo.command(description='設定cookies')
    @commands.cooldown(rate=1,per=1)
    async def set(self,ctx,
                  ltuid:discord.Option(str,name='ltuid',required=False),
                  ltoken:discord.Option(str,name='ltoken',required=False),
                  uid:discord.Option(str,name='uid',description="非必填 輸入後能在使用某些功能時自動套用 若輸入過可跳過",required=False),
                  #cookie_token:discord.Option(str,name='cookie_token',description="非必填 輸入後才能使用更多功能 如兌換序號",required=False,default=None),
                  remove:discord.Option(bool,name='若要移除資料請設為true',default=False)):
        if not remove:
            self.sqldb.set_hoyo_cookies(str(ctx.author.id),ltuid,ltoken,None)
            if uid:
                self.sqldb.set_game_data(str(ctx.author.id),DatabaseGame.GENSHIN.value,player_id=uid)
            await ctx.respond(f'{ctx.author.mention} 設定完成',ephemeral=True)
        else:
            self.sqldb.remove_hoyo_cookies(str(ctx.author.id))
            self.sqldb.remove_game_data(str(ctx.author.id),DatabaseGame.GENSHIN.value)
            await ctx.respond(f'{ctx.author.mention} cookies移除完成',ephemeral=True)

    @hoyo.command(description='取得每月原石來源統計（原神）')
    @commands.cooldown(rate=1,per=1)
    async def diary(self,ctx):
        await ctx.defer()
        cookies = self.sqldb.get_userdata(str(ctx.author.id),'game_hoyo_cookies')
        if not cookies:
            raise commands.errors.ArgumentParsingError("沒有設定cookies或已過期")
        client = genshin.Client(cookies,lang='zh-tw')
        diary = await client.get_diary()

        embed_list = []
        primogems_gap = diary.data.current_primogems - diary.data.last_primogems
        if primogems_gap > 0:
            text = f'比上個月多{primogems_gap}顆'
        elif primogems_gap < 0:
            text = f'比上個月少{primogems_gap*-1}顆'
        else:
            text = f'與上個月相同'
        embed = BotEmbed.simple(title=f'本月總計：{diary.data.current_primogems} 顆原石',description=text)
        for category in diary.data.categories:
            name = category.name
            embed.add_field(name=name,value=f'{category.amount}({category.percentage}%)')
        embed_list.append(embed)
        
        mora_gap = diary.data.current_mora - diary.data.last_mora
        if primogems_gap > 0:
            text = f'比上個月多{mora_gap}個'
        elif primogems_gap < 0:
            text = f'比上個月少{mora_gap*-1}個'
        else:
            text = f'與上個月相同'
        embed = BotEmbed.simple(title=f'本月總計：{diary.data.current_mora} 個摩拉',description=text)
        embed_list.append(embed)

        await ctx.respond(ctx.author.mention,embeds=embed_list)

    @hoyo.command(description='尋找HoYoLab用戶')
    @commands.cooldown(rate=1,per=1)
    async def hoyolab(self,ctx,
                   hoyolab_name:discord.Option(str,name='hoyolab名稱',description='要查詢的用戶')):
        await ctx.defer()
        cookies = self.sqldb.get_userdata(str(ctx.author.id),'game_hoyo_cookies')
        if not cookies:
            raise commands.errors.ArgumentParsingError("沒有設定cookies或已過期")
        client = genshin.Client(cookies,lang='zh-tw')

        hoyolab_user = None
        users = await client.search_users(hoyolab_name)
        #print(users)
        for user in users:
            if user.nickname == hoyolab_name:
                hoyolab_user = user
                break
        #print(user.hoyolab_uid)

        #自己搜不到自己
        if hoyolab_user:
            try:
                cards = await client.get_record_cards(user.hoyolab_id)
                embed_list= []
                for card in cards:
                    #print(card.uid, card.level, card.nickname)
                    #活躍天數days_active 獲得角色數characters 成就達成數achievements 深境螺旋spiral_abyss
                    if card.game == genshin.types.Game.GENSHIN:
                    #    print(card.data[0].value,card.data[1].value,card.data[2].value,card.data[3].value)
                        embed = BotEmbed.simple(title=f'{card.nickname}(LV.{card.level})')
                        embed.add_field(name="HoYOLab UID",value=hoyolab_user.hoyolab_id)
                        embed.add_field(name="角色UID",value=card.uid)
                        embed.add_field(name="活躍天數",value=card.data[0].value)
                        embed.add_field(name="獲得角色數",value=card.data[1].value)
                        embed.add_field(name="成就達成數",value=card.data[2].value)
                        embed.add_field(name="深境螺旋",value=card.data[3].value)
                        embed_list.append(embed)
                    await ctx.respond(embeds=embed_list)

            except genshin.errors.DataNotPublic:
                #if e.retcode == 10102:
                await ctx.respond('用戶資訊未公開')
            except genshin.errors.GenshinException as e:
                await ctx.respond(e.msg)
        else:
            hoyolab_user = await client.get_hoyolab_user()
            if hoyolab_user:
                #print(hoyolab_user)
                accounts = await client.get_game_accounts()

                embed = BotEmbed.general(name=f"{hoyolab_user.nickname}(LV.{hoyolab_user.level.level})",
                                         icon_url=hoyolab_user.icon,
                                         url=f"https://www.hoyolab.com/accountCenter/postList?id={hoyolab_user.hoyolab_id}",
                                         description=hoyolab_user.introduction)
                embed.add_field(name="HoYOLab ID",value=hoyolab_user.hoyolab_id)
                for account in accounts:
                    if account.game == genshin.types.Game.GENSHIN:
                        embed.add_field(name=f"{account.nickname}(原神)",value=f'{account.server_name} {account.uid} LV.{account.level}',inline=False)
                    elif account.game == genshin.types.Game.HONKAI:
                        embed.add_field(name=f"{account.nickname}(崩壞3rd)",value=f'{account.server_name} {account.uid} LV.{account.level}',inline=False)
                embed.set_image(url=hoyolab_user.bg_url)
                await ctx.respond(embed=embed)
            else:
                await ctx.respond('用戶未找到')

    @hoyo.command(description='尋找原神用戶')
    @commands.cooldown(rate=1,per=1)
    async def genshin(self,ctx,
                   genshin_id:discord.Option(str,name='原神uid',description='要查詢的用戶',default=None)):
        await ctx.defer()
        cookies = self.sqldb.get_userdata(str(ctx.author.id),'game_hoyo_cookies')
        if not cookies:
            raise commands.errors.ArgumentParsingError("沒有設定cookies或已過期")
        client = genshin.Client(cookies,lang='zh-tw')

        user = await client.get_genshin_user(genshin_id)
        #print(user.characters)
        #print(user.info)
        #print(user.stats)
        embed = BotEmbed.simple(title=f'{user.info.nickname}({user.info.server})')
        embed.add_field(name="等級",value=user.info.level)
        embed.add_field(name="成就",value=user.stats.achievements)
        embed.add_field(name="活躍天數",value=user.stats.days_active)
        embed.add_field(name="角色",value=user.stats.characters)
        embed.add_field(name="本期深淵",value=user.stats.spiral_abyss)
        embed.set_image(url=user.info.icon)
        await ctx.respond(embed=embed)

    @hoyo.command(description='尋找崩壞3rd用戶')
    @commands.cooldown(rate=1,per=1)
    async def honkai(self,ctx,
                   honkai_id:discord.Option(str,name='崩壞uid',description='要查詢的用戶',default=None)):
        await ctx.defer()
        cookies = self.sqldb.get_userdata(str(ctx.author.id),'game_hoyo_cookies')
        if not cookies:
            raise commands.errors.ArgumentParsingError("沒有設定cookies或已過期")
        client = genshin.Client(cookies,lang='zh-tw')

        user = await client.get_honkai_user(int(honkai_id))
        #print(user.characters)
        #print(user.info)
        #print(user.stats)
        #print(user)
        embed = BotEmbed.simple(title=f'{user.info.nickname}({user.info.server})')
        embed.add_field(name="等級",value=user.info.level)
        embed.add_field(name="成就",value=user.stats.achievements)
        embed.set_image(url=user.info.icon)
        await ctx.respond(embed=embed)

    @hoyo.command(description='查詢深境螺旋')
    @commands.cooldown(rate=1,per=1)
    async def spiral_abyss(self,ctx,
                           genshin_id:discord.Option(str,name='原神uid',description='要查詢的用戶',default=None),
                           previous:discord.Option(bool,name='是否查詢上期紀錄',description='',default=False)):
        await ctx.defer()
        cookies = self.sqldb.get_userdata(str(ctx.author.id),'game_hoyo_cookies')
        if not cookies:
            raise commands.errors.ArgumentParsingError("沒有設定cookies或已過期")
        client = genshin.Client(cookies,lang='zh-tw')
        
        try:
            r_user = await client.get_genshin_user(genshin_id)
            r_spiral_abyss = await client.get_genshin_spiral_abyss(genshin_id,previous=previous)
        except genshin.errors.DataNotPublic:
            await ctx.respond('用戶資訊未公開')
            return
        
        start_time = (r_spiral_abyss.start_time+timedelta(hours=8)).strftime("%Y/%m/%d")
        end_time = (r_spiral_abyss.end_time+timedelta(hours=8)).strftime("%Y/%m/%d")
        
        embed = BotEmbed.simple(description=f"第{r_spiral_abyss.season}期 {start_time} 至 {end_time}\n挑戰{r_spiral_abyss.total_battles}場中獲勝{r_spiral_abyss.total_wins}場，最深至{r_spiral_abyss.max_floor}層，共獲得{r_spiral_abyss.total_stars}顆星")
        if r_user:
            embed.title=f"{r_user.info.nickname} 的深境螺旋紀錄"
        else:
            embed.title=f"深境螺旋紀錄"
        
        ranks = r_spiral_abyss.ranks
        dict = {
            "角色：最多上場":ranks.most_played,
            "角色：最多擊殺": ranks.most_kills,
            "角色：最痛一擊": ranks.strongest_strike,
            "角色：最多承傷": ranks.most_damage_taken,
            "角色：最多技能使用": ranks.most_skills_used,
            "角色：最多大招使用": ranks.most_bursts_used
        }
        for i in dict:
            text = ''
            for j in dict[i]:
                text += f'{j.name} {j.value}\n'
            if text:
                embed.add_field(name=i,value=text)

        #r_spiral_abyss.floors
        #print(r_spiral_abyss)
        await ctx.respond(embed=embed)

    @hoyo.command(description='兌換禮包碼')
    @commands.cooldown(rate=1,per=1)
    async def code(self,ctx,
                   game:discord.Option(str,name='遊戲',description='要簽到的遊戲',choices=hoyo_game_option),
                   code:discord.Option(str,name='禮包碼',description='要兌換的禮包碼'),
                   uid:discord.Option(str,name='uid',description='要兌換的用戶')):
        if not jdata.get("debug_mode"):
            cookies = self.sqldb.get_userdata(str(ctx.author.id),'game_hoyo_cookies')
        else:
            cookies = genshin.utility.get_browser_cookies("chrome")

        if not cookies:
            raise commands.errors.ArgumentParsingError("沒有設定cookies或已過期")
        client = genshin.Client(cookies,lang='zh-tw')
        await client.redeem_code(code,uid,game=game)  
        await ctx.respond('兌換已完成')

    @hoyo.command(description='簽到設定（多個遊戲請個別設定）（尚在測試可能有bug）')
    @commands.cooldown(rate=1,per=1)
    async def reward(self,ctx,
                   game:discord.Option(str,name='遊戲',description='要簽到的遊戲',choices=hoyo_game_option),
                   need_mention:discord.Option(bool,name='成功簽到時是否要tag提醒',default=True),
                   remove:discord.Option(bool,name='若要移除資料請設為true',default=False)):
        if remove:
            self.sqldb.remove_hoyo_reward(ctx.author.id)
            await ctx.respond('設定已移除')
            return
        
        cookies = self.sqldb.get_userdata(str(ctx.author.id),'game_hoyo_cookies')
        if not cookies:
            raise commands.errors.ArgumentParsingError("沒有設定cookies或已過期")
        self.sqldb.add_hoyo_reward(ctx.author.id,game,ctx.channel.id,need_mention)
        await ctx.respond('設定已完成')
        
    
    @hoyo.command(description='測試',guild_ids=debug_guild)
    @commands.cooldown(rate=1,per=1)
    async def test(self,ctx,
                   hoyolab_uid:discord.Option(str,name='hoyolab_uid',description='要查詢的用戶',default=None)):
        cookies = self.sqldb.get_userdata(str(ctx.author.id),'game_hoyo_cookies')
        if not cookies:
            raise commands.errors.ArgumentParsingError("沒有設定cookies")
        client = genshin.Client(cookies,lang='zh-tw')
        r = await client.get_genshin_spiral_abyss(hoyolab_uid)
        print(r)
        await ctx.respond('done')

    @commands.message_command(name="尋找序號",guild_ids=debug_guild)
    async def exchange_code_genshin(self,ctx,message:discord.Message):
        textline = message.content.splitlines()
        p = re.compile(r'[0-9A-Z]{10,}')
        code_list = []
        for i in textline:
            code = p.match(i)
            if code and code not in code_list:
                code_list.append(code.group())
        
        if code_list:
            codetext = ""
            for i in code_list:
                codetext+=f"\n[{i}](https://genshin.hoyoverse.com/zh-tw/gift?code={i})"
            #await ctx.respond(f"找到以下兌換碼{codetext}\n若有設定cookie及uid則將自動兌換",ephemeral=True)
            await ctx.respond(f"找到以下兌換碼{codetext}",ephemeral=True)

    #         cookies = self.sqldb.get_userdata(str(ctx.author.id),'game_hoyo_cookies')
    #         dbdata = self.sqldb.get_game_data(str(ctx.author.id),DatabaseGame.GENSHIN.value)
    #         if not cookies:
    #             await ctx.send("沒有設定cookies或已過期")
    #             return
    #         if dbdata:
    #             client = genshin.Client(cookies,lang='zh-tw')
    #             uid = dbdata['player_id']
    #             for code in code_list:
    #                 await client.redeem_code(code,uid,game=genshin.Game.GENSHIN)
    #                 asyncio.sleep(3)
    #             await ctx.send('兌換已完成')
        else:
            await ctx.respond(f"沒有找到兌換碼",ephemeral=True)

def setup(bot):
    bot.add_cog(system_game(bot))