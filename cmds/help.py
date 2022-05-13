import discord
from discord.ext import commands,pages
from core.classes import Cog_Extension
from library import BRS
from BotLib.basic import Database


class help_page:
    def music():
        page = [BRS.simple("音樂(music) 指令:"),BRS.simple("音樂(music) 指令:")]
        page[0].add_field(name="!!play <歌曲>", value="播放歌曲\n別名:p", inline=False)
        page[0].add_field(name="!!queue", value="歌曲列表\n別名:q", inline=False)
        page[0].add_field(name="!!now", value="現在播放的歌曲\n別名:current,playing,np", inline=False)
        page[0].add_field(name="!!skip", value="投票跳過歌曲，需三個人才可跳過，點歌者可強制跳過\n別名:s", inline=False)
        page[0].add_field(name="!!pause", value="暫停播放\n別名:pa", inline=False)
        page[0].add_field(name="!!resume", value="繼續播放\n別名:re", inline=False)
        page[0].add_field(name="!!join", value="讓機器人加入你的語音", inline=False)
        page[0].add_field(name="!!summon [頻道]", value="讓機器人加入指定語音", inline=False)
        page[0].add_field(name="!!leave", value="讓機器人離開你的語音\n別名:disconnect,dc", inline=False)
        page[0].add_field(name="!!volume <音量>", value="設定音量", inline=False)
        page[1].add_field(name="!!stop", value="停止播放歌曲", inline=False)
        page[1].add_field(name="!!shuffle", value="隨機撥放\n別名:random,r", inline=False)
        page[1].add_field(name="!!loop", value="循環歌曲", inline=False)
        page[1].add_field(name="!!remove <歌曲位置>", value="移除歌曲\n別名:rm", inline=False)
        paginator = pages.Paginator(pages=page, use_default_buttons=True)
        return paginator

    def help():
        pass
    
    def use():
        pass
    
    def pt():
        pass

    def game():
        pass
    
    def set():
        pass
    
    def role():
        pass
    
    def bet():
        pass
    
    def weather():
        pass
    
    def owner():
        pass
    
    def admin():
        pass

class help(Cog_Extension):
    @commands.command(help='原始的help指令')
    async def assist(self,ctx,arg='help'):
        await ctx.send_help(arg)


    @commands.group(invoke_without_command=True)
    async def about(self,ctx):
        embed = BRS.basic(self,f"你好~\n我是{self.bot.user.name}，是一個discord機器人喔~\n我的前輟是`!!`\n你可以輸入`!!help`來查看所有指令的用法\n\n希望我能在discord上幫助到你喔~")
        await ctx.send(embed=embed)


    @about.command()
    async def server(self,ctx):
        text = ''
        for i in self.bot.guilds:
            text = text + i.name + ','
        text = text[:-2]
        await ctx.send(text)
    
    
    @about.command()
    @commands.is_owner()
    async def count(self,ctx):
        embed = BRS.basic(self,f"依據目前的資料\n目前我已服務了{len(self.bot.guilds)}個伺服器\n共包含了{len(self.bot.users)}位成員喔~")
        await ctx.send(embed=embed)


    @commands.command()
    async def info(self, ctx, arg='help'):
        if arg == 'help':
            await ctx.send("vpn類\nvpn | vpn列表\nvpn01 | vpn使用教學\n\n共用類\nshare | 雲端共用資料夾資訊")

        #elif arg == 'crass_chat':
        #    await ctx.send("crass_chat | 跨群聊天列表\n1.別人都在硬啦! 我偏偏要軟啦!!\n2.我就讚owob\n\n在跨群聊天頻道直接發送訊息即可\n想在自己群加入此系統，可找機器人擁有者")
        
        elif arg == 'vpn':
            await ctx.send("vpn | vpn列表\n名稱:willy1236_1 密:123456987 | willy的房間")
        elif arg == 'vpn01':
            await ctx.send("vpn01 | vpn安裝教學\n1.下載Radmin(vpn)\nhttps://www.radmin-vpn.com/tw/\n2.選擇 加入網路 並輸入名稱及密碼(可輸入!!info vpn查詢)\n3.記得 改名 讓大家知道你是誰\n\nIP為 xx.xxx.xx.xxx:ooooo\nx:開地圖的人的IP(VPN的IP)\no:公開至區網時會顯示")
        elif arg == 'share':
            await ctx.send("雲端共用資料夾 | 94共用啦\n可以在這裡下載或共用檔案\n請洽威立以取得雲端權限")
        
        else:
            raise commands.errors.ArgumentParsingError("info:參數錯誤")
            #await ctx.send('參數錯誤，請輸入!!info help取得幫助',delete_after=5)

    # @commands.group(invoke_without_command=True)
    # @commands.cooldown(rate=1,per=3)
    # async def help(self, ctx):
    #     embed = discord.Embed(title="help 指令", color=0xc4e9ff)
    #     embed.set_author(name=self.bot.user.name,icon_url=self.bot.user.display_avatar.url)
    #     embed.add_field(name="尋求幫助", value="```!!help [指令]```", inline=False)
    #     await ctx.send(embed=embed)
    
    @commands.group(invoke_without_command=True)
    @commands.cooldown(rate=1,per=3)
    async def help(self,ctx):
        embed = BRS.basic(self,"目前可使用的指令如下:")
        embed.add_field(name="!!help <系列指令>", value="查詢系列指令\n目前支援:admin,pt,game,set,role,bet,music,weather", inline=False)
        embed.add_field(name="!!info <內容/help>", value="獲得相關資訊", inline=False)
        embed.add_field(name="!!feedback <內容>", value="傳送訊息給機器人擁有者", inline=False)
        embed.add_field(name="!!find <id>", value="搜尋指定ID", inline=False)
        embed.add_field(name="!!lottery [次數]", value="抽獎", inline=False)
        embed.add_field(name="!!about", value="關於機器人的小資訊", inline=False)
        embed.add_field(name="!!help use", value="如何使用指令", inline=False)
        embed.add_field(name="!!ui", value="關於你自己(敬請期待)", inline=False)
        await ctx.send(embed=embed)

    @help.command()
    async def use(self,ctx):
        embed = BRS.basic(self,"帶你了解基本的概念","使用指令")
        embed.add_field(name="指令使用:前輟指令", value="前輟+指令就可以使用了，例如`!!help`\n如果有參數，則需要把每個參數用空格隔開", inline=False)
        embed.add_field(name="括號", value="`<參數>`表示這個參數必填 `[參數]`表示不一定要填\n`<參數1/參數2>`為選擇一個參數填寫即可", inline=False)
        await ctx.send(embed=embed)

    @help.command()
    async def pt(self,ctx):
        embed = BRS.simple("點數系統(Pt) 指令")
        embed.add_field(name="!!pt [用戶]", value="查詢Pt數", inline=False)
        embed.add_field(name="!!pt give <用戶> <數量>", value="將Pt轉給指定用戶", inline=False)
        embed.add_field(name="!!sign", value="每日簽到", inline=False)
        embed.add_field(name="!!shop", value="商城(敬請期待)", inline=False)
        await ctx.send(embed=embed)

    @help.command()
    async def game(self,ctx):
        embed = BRS.simple("遊戲(Game) 指令")
        embed.add_field(name="!!game <set> <遊戲> <資料>", value="設定你在資料庫內的遊戲名稱", inline=False)
        embed.add_field(name="!!game <find> <用戶>", value="查詢用戶在資料庫內的遊戲名稱(目前僅能查詢自己的資料)", inline=False)
        embed.add_field(name="!!lol <player> <玩家名稱>", value="查詢LOL戰績(更多功能敬請期待)", inline=False)
        embed.add_field(name="!!osu <玩家名/id>", value="查詢osu玩家", inline=False)
        embed.add_field(name="!!osu <map> <圖譜id>", value="查詢osu圖譜", inline=False)
        embed.add_field(name="!!apex <玩家名/id>", value="查詢apex玩家(未完成)", inline=False)
        await ctx.send(embed=embed)

    @help.command()
    async def set(self,ctx):
        embed = BRS.simple("設定(Set) 指令:")
        embed.add_field(name="!!set <crass_chat> [頻道]", value="設定跨群聊天頻道", inline=False)
        embed.add_field(name="!!set <all_anno> [頻道]", value="設定全群公告頻道", inline=False)
        await ctx.send(embed=embed)

    @help.command()
    async def role(self,ctx):
        embed = BRS.simple("身分組(Role) 指令:")
        embed.add_field(name="!!role <用戶>", value="取得用戶的身分組數量(可批量輸入多個用戶)", inline=False)
        embed.add_field(name="!!role add <名稱> [用戶]", value="取得用戶的身分組數量(可批量輸入多個用戶)", inline=False)
        embed.add_field(name="!!role nick <名稱/顏色代碼>", value="更改稱號(顏色請輸入HEX格式)", inline=False)
        await ctx.send(embed=embed)

    @help.command()
    async def bet(self,ctx):
        embed = BRS.simple("賭盤(Bet) 指令:")
        embed.add_field(name="!!bet <賭盤ID> <blue/pink> <下注金額>", value="賭盤下注", inline=False)
        embed.add_field(name="!!bet create <賭盤標題> <粉紅幫標題> <藍藍幫標題> <下注時間>", value="創建賭盤(時間格式為'10s''1m20s'等，不可超過600s)", inline=False)
        embed.add_field(name="!!bet end <blue/pink>",value="結算賭盤",inline=False)
        await ctx.send(embed=embed)
    
    @help.command()
    async def music(self,ctx):
        #embed = help_page.music()
        #await ctx.send(embed=embed)
        paginator = help_page.music()
        await paginator.send(ctx, target=ctx.channel)

    @help.command()
    async def weather(self,ctx):
        embed = BRS.simple("天氣(weather) 指令:")
        embed.add_field(name="!!earthquake", value="查詢最新的顯著有感地震報告", inline=False)
        embed.add_field(name="!!covid", value="查詢最新的台灣疫情\n(資料可能會有時間差，請注意資料日期)", inline=False)
        await ctx.send(embed=embed)

    @help.command()
    @commands.is_owner()
    async def owner(self,ctx):
        embed = BRS.basic(self,"目前可使用的指令如下(onwer):")
        embed.add_field(name="!!send <頻道ID/用戶ID/0> <內容>", value="發送指定訊息", inline=False)
        embed.add_field(name="!!anno <內容>", value="對所有伺服器進行公告", inline=False)
        embed.add_field(name="!!edit <訊息ID> <新訊息>", value="編輯訊息", inline=False)
        embed.add_field(name="!!reaction <訊息ID> <add/remove> <表情/表情ID>", value="添加/移除反應", inline=False)
        embed.add_field(name="!!ptset <用戶ID> <+/-/set> <數量>", value="更改指定用戶Pt數", inline=False)
        embed.add_field(name="!!reset", value="簽到重置", inline=False)
        embed.add_field(name="!!role save <用戶/all>", value="儲存身分組", inline=False)
        embed.add_field(name="!!about <server/count>", value="about系列指令", inline=False)
        await ctx.send(embed=embed)

    @help.command()
    async def admin(self,ctx):
        embed = BRS.basic(self,"目前可使用的指令如下(admin):")
        embed.add_field(name="!!clean <數字>", value="清除訊息(需求管理訊息)", inline=False)
        await ctx.send(embed=embed)

def setup(bot):
    bot.add_cog(help(bot))