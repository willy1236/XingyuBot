import discord,requests,genshin
from discord.ext import commands
from bs4 import BeautifulSoup
from discord.commands import SlashCommandGroup

from core.classes import Cog_Extension
from BotLib.funtions import find
from BotLib.database import JsonDatabase
from BotLib.interface.game import *
from BotLib.basic import BotEmbed

def player_search(url):
    response = requests.get(url)
    soup = BeautifulSoup(response.text, "html.parser")
    results = soup.find_all("h1",class_="row")

    for result in results:
        if result.div.string == None:
            result2 = str(result.div)[166:]
            lvl = ''.join([x for x in result2 if x.isdigit()])
            return lvl

db = JsonDatabase()
jdict = db.jdict
set_option = []
for name,value in jdict['game_set_option'].items():
    set_option.append(discord.OptionChoice(name=name,value=value))


class system_game(Cog_Extension):
    #0=未開放 1=開放自由填寫 2=需驗證
    games = {'steam':2,'osu':1,'apex':1,'lol':1}

    game = SlashCommandGroup("game", "遊戲資訊相關指令")
    lol = SlashCommandGroup("lol", "League of Legends相關指令")
    osu = SlashCommandGroup("osu", "Osu相關指令")
    apex = SlashCommandGroup("apex", "Apex相關指令")
    dbd = SlashCommandGroup("dbd", "Dead by Daylight相關指令")
    steam = SlashCommandGroup("steam", "Steam相關指令")
    hoyo = SlashCommandGroup("hoyo", "MiHaYo相關指令")
        
    @game.command(description='設定遊戲資料')
    async def set(self,
                ctx,
                game:discord.Option(str,name='遊戲',description='要設定的遊戲',required=True,choices=set_option),
                data:discord.Option(str,name='資料',description='要設定的資料',default=None)
                ):
        gdata = self.db.gdata
        userid = str(ctx.author.id)
        if not userid in gdata:
            gdata[userid] = {}
            self.db.write('gdata',gdata)
            await ctx.send('偵測到資料庫內無使用者資料，已自動註冊',delete_after=5)

        need_verify = ['steam']
        #清除該遊戲資料
        if not data:
            gdata[userid][game] = None
            await ctx.send(f'已重設{game}資料')
            return
        
        #首次設定該遊戲
        if not game in gdata[userid]:
                gdata[userid][game] = None

        #依遊戲做設定
        if game in need_verify:
            if game == 'steam':
                APIdata = SteamInterface().get_user(data)
                if APIdata:
                    gdata[userid]['steam'] = {'id':APIdata.id,'name':APIdata.name}
                    db.write('gdata',gdata)
                    await ctx.respond(f'已將{game}資料設定為 {APIdata.name}')
                else:
                    await ctx.respond(f'錯誤:找不到此用戶',ephemeral=True)

        else:
            gdata[userid][game] = data
            db.write('gdata',gdata)
            await ctx.respond(f'已將{game}資料設定為 {data}')

    @game.command(description='查詢遊戲資料')
    async def find(self,
                ctx,
                user:discord.Option(discord.Member,name='用戶',description='要查詢的用戶',default=None)
                ):
        gdata = JsonDatabase().gdata
        user = user or ctx.author
        userid = str(user.id)
        
        if user == ctx.author or ctx.author.id == 419131103836635136:
            if user and userid in gdata:
                data = {}
                for game in self.games:
                    if game in gdata[userid]:
                        if 'name' in gdata[userid][game]:
                            data[game] = f"{gdata[userid][game]['name']}\n({gdata[userid][game]['id']})"
                        else:
                            data[game] = gdata[userid][game]
                    else:
                        data[game] = None

                embed = BotEmbed.simple(title=user)
                for game in self.games:
                    embed.add_field(name=game, value=data[game], inline=False)
                embed.set_thumbnail(url=user.display_avatar.url)
                await ctx.respond(embed=embed)
            else:
                await ctx.respond('無法查詢此人的資料，可能是用戶尚未註冊資料庫',ephemeral=True)
        else:
            await ctx.respond('目前不開放查詢別人的資料喔',ephemeral=True)

    @lol.command(description='查詢League of Legends用戶資料')
    async def user(self,ctx,userid:discord.Option(str,name='用戶',description='要查詢的用戶')):
        url = 'https://lol.moa.tw/summoner/show/'+userid
        lvl = player_search(url) or '讀取失敗'

        embed = discord.Embed(title="LOL玩家查詢", url=url, color=0xc4e9ff)
        embed.add_field(name="玩家名稱", value=userid, inline=False)
        embed.add_field(name="等級", value=lvl, inline=False)
        embed.add_field(name="查詢戰績", value="LOL戰績網(lol.moa.tw)", inline=False)
        embed.set_thumbnail(url='https://i.imgur.com/B0TMreW.png')
        await ctx.respond(embed=embed)

    @osu.command(description='查詢Osu用戶資料')
    @commands.cooldown(rate=1,per=1)
    async def user(self,
                ctx,
                userid:discord.Option(str,name='用戶',description='要查詢的用戶，可輸入遊戲名稱或dc名稱',default=None)
                ):
        #資料庫調用
        userid = userid or ctx.author.id
        userid = await JsonDatabase.get_gamedata(userid,'osu',ctx)
        
        if not userid:
            await ctx.respond('查詢失敗:用戶尚未註冊資料庫',ephemeral=True)
            return
        
        player = OsuInterface().get_player(userid)
        if player:
            await ctx.respond('查詢成功',embed=player.desplay())
        else:
            await ctx.respond('查詢失敗:查無此ID',ephemeral=True)

    @osu.command(description='查詢Osu圖譜資料')
    @commands.cooldown(rate=1,per=1)
    async def map(self,
                ctx,
                mapid:discord.Option(str,name='圖譜id',description='要查詢的圖譜ID',default=None)
                ):
        embed = OsuInterface().get_beatmap(mapid).desplay()
        if embed:
            await ctx.respond('查詢成功',embed=embed)
        else:
            await ctx.respond('查詢失敗:查無此ID',ephemeral=True)

    @apex.command(description='查詢Apex玩家資料')
    @commands.cooldown(rate=1,per=3)
    async def user(self,
                ctx:discord.ApplicationContext,
                userid:discord.Option(str,name='用戶',description='要查詢的用戶，可輸入遊戲名稱或dc名稱',default=None)
                ):
        #資料庫調用
        userid = userid or ctx.author.id
        userid = await JsonDatabase.get_gamedata(userid,'apex',ctx)
        
        if not userid:
            await ctx.respond(content='查詢失敗:用戶尚未註冊資料庫',delete_after=5)
            return
        
        player = ApexInterface().get_player(userid)
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

    @apex.command(description='查詢Apex伺服器資料',enabled=False)
    @commands.cooldown(rate=1,per=3)
    async def server(self,ctx):
        embed = ApexInterface().get_server_status().desplay()
        await ctx.respond(content='查詢成功',embed=embed)

    @dbd.command(description='查詢Dead by daylight玩家資料')
    @commands.cooldown(rate=1,per=1)
    async def user(self,
                ctx,
                userid:discord.Option(str,name='用戶',description='要查詢的用戶，可輸入遊戲名稱或dc名稱',default=None)
                ):
        #資料庫調用
        userid = userid or ctx.author.id
        userid = await JsonDatabase.get_gamedata(userid,'steam',ctx)
        
        if not userid:
            await ctx.respond(content='查詢失敗:用戶尚未註冊資料庫',ephemeral=True)
            return
        
        player = DBDInterface().get_player(userid)
        if player:
            await ctx.respond(content='查詢成功',embed=player.desplay())
        else:
            await ctx.respond(content='查詢失敗:查無此ID或個人資料設定私人',ephemeral=True)

    @steam.command(description='查詢Steam用戶資料')
    @commands.cooldown(rate=1,per=1)
    async def user(self,
                ctx,
                userid:discord.Option(str,name='用戶',description='要查詢的用戶，可輸入遊戲名稱或dc名稱',default=None)
                ):
        #資料庫調用
        userid = userid or ctx.author.id
        userid = await JsonDatabase.get_gamedata(userid,'steam',ctx)
        
        if not userid:
            await ctx.respond(content='查詢失敗:用戶尚未註冊資料庫',ephemeral=True)
            return

        user = SteamInterface().get_user(userid)
        if user:
            await ctx.respond(content='查詢成功',embed=user.desplay())
        else:
            await ctx.respond(content='查詢失敗:查無此ID',ephemeral=True)

    # @commands.command()
    # @commands.cooldown(rate=1,per=1)
    # async def hoyohelp(self,ctx):
    #     embed = BotEmbed.simple("原神(hoyo) 指令")
    #     embed.add_field(name="!!hoyo set <ltuid> <ltoken>", value="設定cookies(需先設定才能使用其他功能)", inline=False)
    #     embed.add_field(name="!!hoyo help", value="如何取得設定cookies", inline=False)
    #     embed.add_field(name="!!hoyo diary", value="取得每月原石來源統計", inline=False)
    #     await ctx.send(embed=embed)

    @hoyo.command(description='如何設定cookies(需先設定才能使用其他功能)')
    @commands.cooldown(rate=1,per=1)
    async def help(self,ctx):
        embed = BotEmbed.simple("1.前往 https://www.hoyolab.com/ 並登入\n2.複製以下代碼```script:d=document.cookie; c=d.includes('account_id') || alert('過期或無效的Cookie,請先登出帳號再重新登入!'); c && document.write(d)```\n3.在網址列打上java後直接貼上複製的代碼\n4.找到`ltuid=`跟`ltoken=`並複製其中的內容\n5.使用指令 /hoyo set <ltuid> <ltoken>")
        await ctx.respond(embed=embed)

    @hoyo.command(description='設定cookies')
    @commands.cooldown(rate=1,per=1)
    async def set(self,
                ctx,
                ltuid:discord.Option(str,name='ltuid',required=True)
                ,ltoken:discord.Option(str,name='ltoken',required=True)
                ):
        await ctx.message.delete()
        db = JsonDatabase()
        jhoyo = db.jhoyo
        dict = {
            'ltuid': ltuid,
            'ltoken': ltoken,
        }
        jhoyo[str(ctx.author.id)] = dict
        db.write('jhoyo',jhoyo)
        await ctx.respond(f'{ctx.author.mention} 設定完成')

    @hoyo.command(description='取得每月原石來源統計')
    @commands.cooldown(rate=1,per=1)
    async def diary(self,ctx):
        db = JsonDatabase()
        jhoyo = db.jhoyo
        cookies = jhoyo.get(str(ctx.author.id),None)
        if not cookies:
            raise commands.errors.ArgumentParsingError("沒有設定cookies")
        client = genshin.Client(cookies)
        diary = await client.get_diary()

        ts = {
            'Events':'活動',
            'Adventure':'冒險',
            'Mail':'郵件',
            'Daily Activity':'每日任務',
            'Quests':'一般任務',
            'Other':'其他',
            'Spiral Abyss':'深境螺旋',
        }
        embed = BotEmbed.simple(title=f'本月總計：{diary.data.current_primogems} 顆原石')
        for category in diary.data.categories:
            name = category.name
            embed.add_field(name=ts.get(name,name),value=f'{category.amount}({category.percentage}%)')
        await ctx.respond(ctx.author.mention,embed=embed)

    @hoyo.command(description='尋找用戶')
    @commands.cooldown(rate=1,per=1)
    async def find(self,
                ctx,
                hoyolab_name:discord.Option(str,name='hoyolab名稱',description='要查詢的用戶',default=None)
                ):
        db = JsonDatabase()
        jhoyo = db.jhoyo
        cookies = jhoyo.get(str(ctx.author.id),None)
        if not cookies:
            raise commands.errors.ArgumentParsingError("沒有設定cookies")
        client = genshin.Client(cookies)

        hoyolab_user = None
        users = await client.search_users(hoyolab_name)
        for user in users:
            if user.nickname == hoyolab_name:
                hoyolab_user = user
                break
        #print(user.hoyolab_uid)
        if hoyolab_user:    
            try:
                cards = await client.get_record_cards(user.hoyolab_uid)
                for card in cards:
                    #print(card.uid, card.level, card.nickname)
                    #活躍天數days_active 獲得角色數characters 成就達成數achievements 深境螺旋spiral_abyss
                    if card.game == genshin.types.Game.GENSHIN:
                    #    print(card.data[0].value,card.data[1].value,card.data[2].value,card.data[3].value)
                        embed = BotEmbed.simple(title=card.nickname)
                        embed.add_field(name="HoYOLab UID",value=hoyolab_user.hoyolab_uid)
                        embed.add_field(name="角色UID",value=card.uid)
                        embed.add_field(name="活躍天數",value=card.data[0].value)
                        embed.add_field(name="獲得角色數",value=card.data[1].value)
                        embed.add_field(name="成就達成數",value=card.data[2].value)
                        embed.add_field(name="深境螺旋",value=card.data[3].value)
                        await ctx.respond(embed=embed)

                    
            except genshin.errors.DataNotPublic:
                if e.retcode == 10102:
                    await ctx.respond('用戶資訊未公開')
            except genshin.errors.GenshinException as e:
                await ctx.respond(e)
        else:
            await ctx.respond('用戶未找到')

def setup(bot):
    bot.add_cog(system_game(bot))