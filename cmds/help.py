import discord
from discord.ext import commands
import json ,random,asyncio

from core.classes import Cog_Extension


jdata = json.load(open('setting.json','r',encoding='utf8'))

class help(Cog_Extension):
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
        print(ctx)

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

def setup(bot):
    bot.add_cog(help(bot))