import discord
from discord.ext import commands,pages
from core.classes import Cog_Extension
from discord.commands import SlashCommandGroup
from bothelper import BotEmbed
from bothelper.utility import ChoiceList


info_option = ChoiceList.set('info_option')
help_option = ChoiceList.set('help_option')

class help(Cog_Extension):
    # @commands.command(help='原始的help指令')
    # async def assist(self,ctx,arg='help'):
    #     await ctx.send_help(arg)

    @commands.slash_command(description='關於機器人')
    async def about(self,ctx):
        embed = BotEmbed.basic(self,f"你好~我是{self.bot.user.name}，是一個discord機器人喔~\n你可以輸入`/help`來查看所有指令的用法\n\n希望我能在discord上幫助到你喔~\n有任何建議與需求可以使用`/feedback`指令")
        embed.set_footer(text="此機器人由 威立#6445 負責維護")
        await ctx.respond(embed=embed)

    @commands.slash_command(description='機器人統計')
    @commands.is_owner()
    async def count(self,ctx,guild:discord.Option(bool,name='是否列出伺服器')):
        embed = BotEmbed.basic(self,f"依據目前的資料\n目前我已服務了{len(self.bot.guilds)}個伺服器\n共包含了{len(self.bot.users)}位成員喔~")
        if guild:
            name_list = []
            for i in self.bot.guilds:
                name_list.append(i.name)
            embed2 = BotEmbed.simple(','.join(name_list))
        await ctx.respond(embeds=[embed,embed2])

    @commands.slash_command(description='一些資訊')
    async def info(self, ctx, arg:discord.Option(str,name='選項',description='',choices=info_option)):
        if arg == 'help':
            text = "總表 | info可用選項\n指令用法:!!info <參數>\nvpn類\nvpn | vpn列表\nvpn01 | vpn使用教學\n\nminecraft類\nmc | minecraft總表\nmc01 | minecraft資料夾\nmc02 | 如何裝模組\n\n共用類\nshare | 雲端共用資料夾資訊"

        elif arg == 'vpn':
            text = "vpn | vpn列表\n名稱:willy1236_1 密:123456987 | willy的房間"
        elif arg == 'vpn01':
            text = "vpn01 | vpn安裝教學\n1.下載Radmin(vpn)\nhttps://www.radmin-vpn.com/tw/\n2.選擇 加入網路 並輸入名稱及密碼(可輸入/info vpn查詢)\n3.記得 改名 讓大家知道你是誰\n\nIP依據開伺服器的方式不同分為\n區域網: xx.xxx.xx.xxx:ooooo\n伺服器: xx.xxx.xx.xxx\nx:開地圖的人的IP(VPN的IP)\no:公開至區網時會顯示的連接阜數字"
        elif arg == 'share':
            text = "雲端共用資料夾 | 94共用啦\n可以在這裡下載或共用檔案\n請洽威立以取得雲端權限"

        elif arg == 'mc':
            text = "總表 | mc可用選項\nmc01 | minecraft資料夾\nmc02 | 如何裝模"
        elif arg == 'mc01':
            text = "mc01 | minecraft資料夾\n資料夾開啟方式\n法1:\n在minecraft的選項中開啟 資源包\n選擇 開啟資料包資料夾\n法2:\n按下Ctrl+r 輸入 %AppData% 按確認\n選擇.minecraft\n\n資料夾名稱\nsaves 單人地圖存檔\nresourcepacks 資源包存檔\nscreenshots F2截圖圖片"
        elif arg == 'mc02':
            text = "mc02 | 如何裝模組\n被你發現我還沒打內容了w\n既然你這麼想知道的話\nhttps://youtu.be/8gYBo_vcZFs"
        
        else:
            raise commands.errors.ArgumentParsingError("查無資訊")
            #await ctx.send('參數錯誤，請輸入!!info help取得幫助',delete_after=5)
        await ctx.respond(text)

    # @commands.group(invoke_without_command=True)
    # @commands.cooldown(rate=1,per=3)
    # async def help(self, ctx):
    #     embed = discord.Embed(title="help 指令", color=0xc4e9ff)
    #     embed.set_author(name=self.bot.user.name,icon_url=self.bot.user.display_avatar.url)
    #     embed.add_field(name="尋求幫助", value="```!!help [指令]```", inline=False)
    #     await ctx.send(embed=embed)
    
    @commands.slash_command(name='help',description='幫助指令')
    @commands.cooldown(rate=1,per=3)
    async def help_overview(self,ctx,arg:discord.Option(str,name='選項',description='',default='help',choices=help_option,required=False)):
        if arg == 'help':
            embed = BotEmbed.basic(self,"目前可使用的指令如下:")
            embed.add_field(name="!!help <系列指令>", value="查詢系列指令", inline=False)
            embed.add_field(name="!!info <內容/help>", value="獲得相關資訊", inline=False)
            embed.add_field(name="!!feedback <內容>", value="傳送訊息給機器人擁有者", inline=False)
            #embed.add_field(name="!!find <id>", value="搜尋指定ID", inline=False)
            embed.add_field(name="!!lottery [次數]", value="抽獎試手氣", inline=False)
            embed.add_field(name="!!set", value="設定自動通知", inline=False)
            embed.add_field(name="!!about", value="關於機器人的小資訊", inline=False)
            embed.set_footer(text="輸入!!help user查詢指令用法")
            await ctx.respond(embed=embed)
        elif arg == 'use':
            embed = BotEmbed.basic(self,"帶你了解基本的概念","使用指令")
            embed.add_field(name="指令使用:前輟指令", value="前輟+指令就可以使用了，例如`!!help`\n如果有參數，則需要把每個參數用空格隔開", inline=False)
            embed.add_field(name="指令使用:斜槓指令", value="打上/後，會有dc的提示幫助你`\n如果有參數，在輸入過程中都有提示", inline=False)
            embed.add_field(name="括號", value="`<參數>`表示這個參數必填 `[參數]`表示不一定要填\n`<參數1/參數2>`為選擇一個參數填寫即可\n範例：", inline=False)
            embed.set_footer(text="輸入!!help use查詢指令用法")
            await ctx.respond(embed=embed)
        elif arg == 'pt':
            embed = BotEmbed.simple("點數系統(Pt) 指令")
            embed.add_field(name="!!pt check [用戶]", value="查詢Pt數", inline=False)
            embed.add_field(name="!!pt give <用戶> <數量>", value="將Pt轉給指定用戶", inline=False)
            embed.add_field(name="!!sign", value="每日簽到", inline=False)
            embed.add_field(name="!!shop", value="商城(敬請期待)", inline=False)
            embed.set_footer(text="輸入!!help use查詢指令用法")
            await ctx.respond(embed=embed)
        elif arg == 'game':
            embed = BotEmbed.simple("遊戲(Game) 指令")
            embed.add_field(name="!!game set <遊戲> <資料>", value="設定你在資料庫內的遊戲名稱\n目前支援:steam,lol,osu,apex(pc版)", inline=False)
            embed.add_field(name="!!game find [用戶] [遊戲]", value="查詢用戶在資料庫內的遊戲名稱(目前僅能查詢自己的資料)", inline=False)
            embed.add_field(name="!!lol player <玩家名稱>", value="查詢LOL戰績(更多功能敬請期待)", inline=False)
            embed.add_field(name="!!osu player <玩家名/id>", value="查詢osu玩家", inline=False)
            embed.add_field(name="!!osu map <圖譜id>", value="查詢osu圖譜", inline=False)
            embed.add_field(name="!!apex player <玩家名/id>", value="查詢apex玩家", inline=False)
            embed.add_field(name="!!apex map", value="查詢apex地圖輪替", inline=False)
            embed.add_field(name="!!apex creafting", value="查詢apex合成台內容", inline=False)
            embed.add_field(name="!!dbd player <id>", value="查詢DBD玩家", inline=False)
            embed.add_field(name="!!hoyo", value="查詢原神相關指令", inline=False)
            embed.set_footer(text="輸入!!help use查詢指令用法")
            await ctx.respond(embed=embed)
        elif arg == 'set':
            embed = BotEmbed.simple("設定(Set) 指令:")
            embed.add_field(name="!!set crass_chat [頻道]", value="設定跨群聊天頻道", inline=False)
            embed.add_field(name="!!set all_anno [頻道]", value="設定全群公告頻道", inline=False)
            embed.add_field(name="!!set apex_crafting [頻道]", value="設定apex合成器內容頻道", inline=False)
            embed.add_field(name="!!set apex_map [頻道]", value="設定apex地圖輪替頻道", inline=False)
            embed.add_field(name="!!set earthquake [頻道]", value="設定地震通知頻道", inline=False)
            embed.add_field(name="!!set covid_update [頻道]", value="設定台灣疫情通知頻道", inline=False)
            embed.add_field(name="!!set forecast [頻道]", value="設定台灣各縣市天氣預報頻道", inline=False)
            embed.add_field(name="!!set bot [頻道]", value="設定機器人更新通知頻道", inline=False)
            embed.set_footer(text="輸入!!help use查詢指令用法")
            await ctx.respond(embed=embed)
        elif arg == 'role':
            embed = BotEmbed.simple("身分組(Role) 指令:")
            embed.add_field(name="!!role count <用戶>", value="取得用戶的身分組數量(可批量輸入多個用戶)", inline=False)
            embed.add_field(name="!!role add <名稱> [用戶]", value="取得用戶的身分組數量(可批量輸入多個用戶)", inline=False)
            embed.add_field(name="!!role nick <名稱/顏色代碼>", value="更改稱號(顏色請輸入HEX格式)", inline=False)
            embed.set_footer(text="輸入!!help use查詢指令用法")
            await ctx.respond(embed=embed)
        elif arg == 'bet':
            embed = BotEmbed.simple("賭盤(Bet) 指令:")
            embed.add_field(name="!!bet <賭盤ID> <blue/pink> <下注金額>", value="賭盤下注", inline=False)
            embed.add_field(name="!!bet create <賭盤標題> <粉紅幫標題> <藍藍幫標題> <下注時間>", value="創建賭盤(時間格式為'10s''1m20s'等，不可超過600s)", inline=False)
            embed.add_field(name="!!bet end <blue/pink>",value="結算賭盤",inline=False)
            embed.set_footer(text="輸入!!help use查詢指令用法")
            await ctx.respond(embed=embed)
        elif arg == 'music':
            page = [BotEmbed.simple("音樂(music) 指令:"),BotEmbed.simple("音樂(music) 指令:")]
            page[0].add_field(name="!!play <歌曲>", value="播放歌曲", inline=False)
            page[0].add_field(name="!!queue", value="歌曲列表", inline=False)
            page[0].add_field(name="!!nowplaying", value="現在播放的歌曲", inline=False)
            #page[0].add_field(name="!!skip", value="投票跳過歌曲，需三個人才可跳過，點歌者可強制跳過", inline=False)
            page[0].add_field(name="!!skip", value="跳過歌曲", inline=False)
            page[0].add_field(name="!!pause", value="暫停/繼續播放", inline=False)
            #page[0].add_field(name="!!resume", value="繼續播放", inline=False)
            page[0].add_field(name="!!join", value="讓機器人加入你的語音", inline=False)
            #page[0].add_field(name="!!summon [頻道]", value="讓機器人加入指定語音", inline=False)
            #page[0].add_field(name="!!leave", value="讓機器人離開你的語音\n別名:disconnect,dc", inline=False)
            #page[0].add_field(name="!!volume <音量>", value="設定音量", inline=False)
            page[1].add_field(name="!!stop", value="停止播放歌曲", inline=False)
            #page[1].add_field(name="!!shuffle", value="隨機撥放\n別名:random,r", inline=False)
            #page[1].add_field(name="!!loop", value="循環歌曲", inline=False)
            #page[1].add_field(name="!!remove <歌曲位置>", value="移除歌曲\n別名:rm", inline=False)
            paginator = pages.Paginator(pages=page, use_default_buttons=True)
            #await paginator.send(ctx, target=ctx.channel)
            await paginator.respond(ctx.interaction, ephemeral=False)
        elif arg == 'weather':
            embed = BotEmbed.simple("天氣(weather) 指令:")
            embed.add_field(name="!!earthquake", value="查詢最新的顯著有感地震報告", inline=False)
            embed.add_field(name="!!covid", value="查詢最新的台灣疫情", inline=False)
            embed.add_field(name="!!forecast ", value="查詢天氣預報", inline=False)
            embed.set_footer(text="輸入!!help use查詢指令用法")
            await ctx.respond(embed=embed)
        # elif arg == 'math':
        #     embed = BotEmbed.simple("數學(math) 指令:")
        #     embed.add_field(name="!!ma <A列數> <A行數>  <A> <B列數> <B行數> <B>", value='A*B矩陣乘法\n矩陣打法 : "數字1 數字2.... "\n前後加引號 每個數字用空格隔開 數字順序為 一列數字打完 再打下一列數字', inline=False)
        #     embed.set_footer(text="輸入!!help use查詢指令用法")
        #     await ctx.respond(embed=embed)
        elif arg == 'user':
            embed = BotEmbed.simple("用戶(user) 指令:")
            embed.add_field(name="!!ui", value="關於你自己", inline=False)
            embed.add_field(name="!!bag", value="查看背包", inline=False)
            embed.add_field(name="!!pet [用戶]", value='查詢寵物', inline=False)
            embed.add_field(name="!!pet add <物種> <名稱>", value='領養寵物\n可用物種:shark,dog,cat,fox', inline=False)
            embed.add_field(name="!!pet remove", value='放生寵物', inline=False)
            embed.add_field(name="!!advance", value='進行冒險', inline=False)
            embed.set_footer(text="輸入!!help use查詢指令用法")
            await ctx.respond(embed=embed)
        elif arg == 'twitch':
            embed = BotEmbed.simple("圖奇(twitch) 指令:")
            embed.add_field(name="!!twitch set <twitch用戶> <頻道> [身分組]", value="設定twitch的開台通知", inline=False)
            embed.add_field(name="!!twitch remove <twitch用戶>", value="移除twitch的開台通知", inline=False)
            embed.add_field(name="!!twitch notice <twitch用戶>", value="檢查twitch的開台通知頻道", inline=False)
            embed.set_footer(text="輸入!!help use查詢指令用法")
            await ctx.respond(embed=embed)
        elif arg == 'admin':
            embed = BotEmbed.utility(self,"目前可使用的指令如下(admin):")
            embed.add_field(name="!!clean <數字>", value="清除訊息(需求管理訊息)", inline=False)
            embed.set_footer(text="輸入!!help use查詢指令用法")
            await ctx.respond(embed=embed)
    
    @commands.slash_command(description='owner幫助指令')
    @commands.is_owner()
    async def help_owner(self,ctx):
        embed = BotEmbed.basic(self,"目前可使用的指令如下(onwer):")
        embed.add_field(name="!!send <頻道ID/用戶ID/0> <內容>", value="發送指定訊息", inline=False)
        embed.add_field(name="!!anno <內容>", value="對所有伺服器進行公告", inline=False)
        embed.add_field(name="!!bupdate <內容>", value="對所有伺服器發送機器人更新", inline=False)
        embed.add_field(name="!!edit <訊息ID> <新訊息>", value="編輯訊息", inline=False)
        embed.add_field(name="!!reaction <訊息ID> <add/remove> <表情/表情ID>", value="添加/移除反應", inline=False)
        embed.add_field(name="!!ptset <用戶ID> <+/-/set> <數量>", value="更改指定用戶Pt數", inline=False)
        embed.add_field(name="!!reset", value="簽到重置", inline=False)
        embed.add_field(name="!!role save <用戶/all>", value="儲存身分組", inline=False)
        embed.add_field(name="!!about <server/count>", value="about系列指令", inline=False)
        embed.add_field(name="!!jset <option> <value>", value="設定jdata數值", inline=False)
        embed.set_footer(text="輸入!!help use查詢指令用法")
        await ctx.respond(embed=embed)


def setup(bot):
    bot.add_cog(help(bot))