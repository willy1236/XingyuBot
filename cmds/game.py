import discord,requests,genshin
from discord.ext import commands
from bs4 import BeautifulSoup

from core.classes import Cog_Extension
from BotLib.funtions import find    
from BotLib.database import Database
from BotLib.gamelib import *
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


class game(Cog_Extension):
    #0=未開放 1=開放自由填寫 2=需驗證
    games = {'steam':2,'osu':1,'apex':1,'lol':1}

    @commands.command()
    async def lol(self,ctx,*arg):
        if arg[0] == 'player':
            player = arg[1]
            url = 'https://lol.moa.tw/summoner/show/'+player
            lvl = player_search(url) or '讀取失敗'

            embed = discord.Embed(title="LOL玩家查詢", url=url, color=0xc4e9ff)
            embed.add_field(name="玩家名稱", value=player, inline=False)
            embed.add_field(name="等級", value=lvl, inline=False)
            embed.add_field(name="查詢戰績", value="LOL戰績網(lol.moa.tw)", inline=False)
            embed.set_thumbnail(url='https://i.imgur.com/B0TMreW.png')
        
            await ctx.send(embed=embed)
        else:
            await ctx.send('目前沒有這種用法喔')

    @commands.group(invoke_without_command=True)
    async def game(self,ctx):
        raise commands.errors.ArgumentParsingError('沒有輸入其他參數')
        
    @game.command()
    async def set(self,ctx,game,data=None):
        db = Database()
        gdata = db.gdata
        userid = str(ctx.author.id)
        if not userid in gdata:
            gdata[userid] = {}
            db.write('gdata',gdata)
            await ctx.send('偵測到資料庫內無使用者資料，已自動註冊',delete_after=5)

        if game in self.games and self.games[game] != 0:
            #清除該遊戲資料
            if not data:
                gdata[userid][game] = None
                await ctx.send(f'已重設{game}資料')
                return
            
            #首次設定該遊戲
            if not game in gdata[userid]:
                    gdata[userid][game] = None

            #依遊戲做設定
            if self.games[game] == 1:
                gdata[userid][game] = data
                await ctx.send(f'已將{game}資料設定為 {data}')
                db.write('gdata',gdata)
            
            elif self.games[game] == 2:
                if game == 'steam':
                    APIdata = SteamData().get_user(data)
                    if APIdata:
                        gdata[userid]['steam'] = {'id':APIdata.id,'name':APIdata.name}
                        db.write('gdata',gdata)
                        await ctx.send(f'已將{game}資料設定為 {APIdata.name}')
                    else:
                        await ctx.send(f'錯誤:找不到此用戶',delete_after=5)
        else:
            await ctx.send(f'遊戲錯誤:此遊戲目前未開放設定',delete_after=10)

    @game.command()
    async def find(self,ctx,user=None):
        gdata = Database().gdata
        if not user:
            user = ctx.author
            userid = str(user.id)
        else:
            user = await find.user2(ctx,user)
            if user:
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
                await ctx.send(embed=embed)
            else:
                await ctx.send('無法查詢此人的資料，可能是無此用戶或用戶尚未註冊資料庫',delete_after=5)
        else:
            await ctx.send('目前不開放查詢別人的資料喔',delete_after=5)

    @commands.group(invoke_without_command=True)
    @commands.cooldown(rate=1,per=1)
    async def osu(self,ctx,userid=None):
        msg = await ctx.send('資料查詢中...')
        #資料庫調用
        userid = userid or ctx.author.id
        userid = await Database.get_gamedata(userid,'osu',ctx)
        
        if not userid:
            await msg.edit(content='查詢失敗:用戶尚未註冊資料庫',delete_after=5)
            return
        
        player = OsuData().get_player(userid)
        if player:
            await msg.edit(content='查詢成功',embed=player.desplay())
        else:
            await msg.edit(content='查詢失敗:查無此ID',delete_after=5)

    @osu.command()
    @commands.cooldown(rate=1,per=1)
    async def map(self,ctx,mapid):
        msg = await ctx.send('資料查詢中...')
        embed = OsuData().get_beatmap(mapid).desplay()
        if embed:
            await msg.edit(content='查詢成功',embed=embed)
        else:
            await msg.edit(content='查詢失敗:查無此ID',delete_after=5)

    @commands.group(invoke_without_command=True)
    @commands.cooldown(rate=1,per=3)
    async def apex(self,ctx,userid=None):
        msg = await ctx.send('資料查詢中...')
        #資料庫調用
        userid = userid or ctx.author.id
        userid = await Database.get_gamedata(userid,'apex',ctx)
        
        if not userid:
            await msg.edit(content='查詢失敗:用戶尚未註冊資料庫',delete_after=5)
            return
        
        player = ApexData().get_player(userid)
        if player:
            await msg.edit(content='查詢成功',embed=player.desplay())
        else:
            await msg.edit(content='查詢失敗:查無此ID',delete_after=5)

    @apex.command()
    @commands.cooldown(rate=1,per=3)
    async def map(self,ctx):
        msg = await ctx.send('資料查詢中...')
        embed = ApexData.get_map_rotation().desplay()
        await msg.edit(content='查詢成功',embed=embed)

    @apex.command()
    @commands.cooldown(rate=1,per=3)
    async def crafting(self,ctx):
        msg = await ctx.send('資料查詢中...')
        embed = ApexData.get_crafting().desplay()
        await msg.edit(content='查詢成功',embed=embed)

    @apex.command(enabled=False)
    @commands.cooldown(rate=1,per=3)
    async def server(self,ctx):
        msg = await ctx.send('資料查詢中...')
        embed = ApexData.get_status().desplay()
        await msg.edit(content='查詢成功',embed=embed)

    @commands.group(invoke_without_command=True,enabled=True)
    @commands.cooldown(rate=1,per=1)
    async def DBD(self,ctx,userid=None):
        msg = await ctx.send('資料查詢中...')
        #資料庫調用
        userid = userid or ctx.author.id
        userid = await Database.get_gamedata(userid,'steam',ctx)
        
        if not userid:
            await msg.edit(content='查詢失敗:用戶尚未註冊資料庫',delete_after=5)
            return
        
        player = DBDData().get_player(userid)
        if player:
            await msg.edit(content='查詢成功',embed=player.desplay())
        else:
            await msg.edit(content='查詢失敗:查無此ID或個人資料設定私人',delete_after=5)

    @commands.group(invoke_without_command=True)
    @commands.cooldown(rate=1,per=1)
    async def steam(self,ctx,userid=None):
        msg = await ctx.send('資料查詢中...')
        #資料庫調用
        userid = userid or ctx.author.id
        userid = await Database.get_gamedata(userid,'steam',ctx)
        
        if not userid:
            await msg.edit(content='查詢失敗:用戶尚未註冊資料庫',delete_after=5)
            return

        user = SteamData().get_user(userid)
        if user:
            await msg.edit(content='查詢成功',embed=user.desplay())
        else:
            await msg.edit(content='查詢失敗:查無此ID',delete_after=5)

    @commands.group(invoke_without_command=True)
    @commands.cooldown(rate=1,per=1)
    async def hoyo(self,ctx):
        embed = BotEmbed.simple("原神(hoyo) 指令")
        embed.add_field(name="!!hoyo set <ltuid> <ltoken>", value="設定cookies(需先設定才能使用其他功能)", inline=False)
        embed.add_field(name="!!hoyo help", value="如何取得設定cookies", inline=False)
        embed.add_field(name="!!hoyo diary", value="取得每月原石來源統計", inline=False)
        await ctx.send(embed=embed)

    @hoyo.command()
    @commands.cooldown(rate=1,per=1)
    async def help(self,ctx):
        embed = BotEmbed.simple("1.前往 https://www.hoyolab.com/ 並登入\n2.複製以下代碼```script:d=document.cookie; c=d.includes('account_id') || alert('過期或無效的Cookie,請先登出帳號再重新登入!'); c && document.write(d)```\n3.在網址列打上java後直接貼上複製的代碼\n4.找到`ltuid=`跟`ltoken=`並複製其中的內容\n5.使用指令 !!hoyo set <ltuid> <ltoken>")
        await ctx.send(embed=embed)

    @hoyo.command()
    @commands.cooldown(rate=1,per=1)
    async def set(self,ctx,ltuid,ltoken):
        await ctx.message.delete()
        db = Database()
        jhoyo = db.jhoyo
        dict = {
            'ltuid': ltuid,
            'ltoken': ltoken,
        }
        jhoyo[str(ctx.author.id)] = dict
        db.write('jhoyo',jhoyo)
        await ctx.send(f'{ctx.author.mention} 設定完成')

    @hoyo.command()
    @commands.cooldown(rate=1,per=1)
    async def diary(self,ctx):
        db = Database()
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
        await ctx.send(ctx.author.mention,embed=embed)

    @hoyo.command()
    @commands.cooldown(rate=1,per=1)
    async def find(self,ctx,hoyolab_name):
        db = Database()
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
                        await ctx.send(embed=embed)

                    
            except genshin.errors.DataNotPublic:
                if e.retcode == 10102:
                    await ctx.send('用戶資訊未公開')
            except genshin.errors.GenshinException as e:
                await ctx.send(e)
        else:
            await ctx.send('用戶未找到')

def setup(bot):
    bot.add_cog(game(bot))