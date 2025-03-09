import discord
from discord.ext import commands,pages
from discord.commands import SlashCommandGroup
from starlib import BotEmbed,ChoiceList
from ..extension import Cog_Extension

info_option = ChoiceList.set('info_option')
help_option = ChoiceList.set('help_option')

info_data = {
    "help": "總表 | info可用選項\n指令用法:/info <參數>\nvpn類\nvpn | vpn列表\nvpn01 | vpn使用教學\n\nminecraft類\nmc | minecraft總表\nmc01 | minecraft資料夾\nmc02 | 如何裝模組\n\n共用類\nshare | 雲端共用資料夾資訊",
    "vpn": "vpn | vpn列表\nRadmin VPN\n名稱：`willy1236_1` 密：`123456987` | 一號房間\n\nzerotier\nID：`b15644912ed8306b` | 一號房間\n申請進入zerotier的房間後記得通知房間的管理員幫你認證喔",
    "vpn01": "vpn01 | vpn安裝教學\nWindow版\n1.下載Radmin vpn\nhttps://www.radmin-vpn.com/tw/\n2.選擇 加入網路 並輸入名稱及密碼（如果不知道要輸入什麼可以使用/info vpn查詢）\n3.記得 改名 讓大家知道你是誰\n\nMacOS/Window版\n下載zerotier並安裝\nhttps://www.zerotier.com/download/\n2.右下角小工具中找到zerotier並右鍵點擊\n3.選擇Join New Network\n4.輸入房間ID\n\nIP依據開伺服器的方式不同分為\n區域網: xxx.xxx.xxx.xxx:ooooo\n伺服器: xxx.xxx.xxx.xxx\nx:開地圖的人的IP（VPN的IP）\no:公開至區網時會顯示的連接埠數字\n如果埠號為25565（Minecraft預設）則可以省略，伺服器不用連接埠數字同理，但若伺服器不是開在25565上一樣需要輸入數字喔",
    "share": "雲端共用資料夾 | 94共用啦\n可以在這裡下載或共用檔案\n請洽威立以取得雲端權限",
    "mc": "總表 | mc可用選項\nmc01 | minecraft資料夾\nmc02 | 如何裝模組",
    "mc01": "mc01 | minecraft資料夾\n資料夾開啟方式\n法1：\n在minecraft的選項中開啟 資源包\n選擇 開啟資料包資料夾\n法2：\n按下Ctrl+r 輸入 %AppData% 按確認\n選擇.minecraft\n\n資料夾名稱\nsaves 單人地圖存檔\nresourcepacks 資源包存檔\nscreenshots F2截圖圖片",
    "mc02": "mc02 | 如何裝模組\n被你發現我還沒打內容了w\n既然你這麼想知道的話\nhttps://youtu.be/8gYBo_vcZFs",
    "trpg01": "trpg01 | 參加房間\nhttps://trpgline.com/zh-TW/admin\n房間管理->參與房間->輸入房號與密碼",
    "trpg02": "trpg02 | 放入角色\n左邊五個按鈕 選擇物件控制台 -> 點+ -> 新物件 -> 收藏夾 -> 選擇角色匯入物件\n右方點擊自己的齒輪 -> 操作角色 -> 選擇角色 -> 最後將角色拖到地圖上"
}

class help(Cog_Extension):
    @commands.slash_command(description='關於機器人')
    async def about(self,ctx):
        await ctx.respond(embed=self.bot.about_embed())

    @commands.slash_command(description='一些資訊')
    async def info(self, ctx, arg:discord.Option(str,name='選項',description='資訊名稱',choices=info_option)):
        title,text = info_data[arg].split('\n',1)
        await ctx.respond(embed=BotEmbed.bot(self.bot, title=title, description=text))

    # @commands.group(invoke_without_command=True)
    # @commands.cooldown(rate=1,per=3)
    # async def help(self, ctx):
    #     embed = discord.Embed(title="help 指令", color=0xc4e9ff)
    #     embed.set_author(name=self.bot.user.name,icon_url=self.bot.user.display_avatar.url)
    #     embed.add_field(name="尋求幫助", value="```/help [指令]```", inline=False)
    #     await ctx.send(embed=embed)
    
    @commands.slash_command(name='help',description='幫助指令')
    @commands.cooldown(rate=1,per=3)
    async def help_overview(self,ctx,arg:discord.Option(str,name='選項',description='指令類別（非必填）',default='help',choices=help_option,required=False)):
        if arg == 'help':
            embed = BotEmbed.bot(self.bot,"目前可使用的指令如下:")
            embed.add_field(name="/help <系列指令>", value="查詢指令", inline=False)
            embed.add_field(name="/info <內容/help>", value="獲得相關資訊", inline=False)
            embed.add_field(name="/feedback <內容>", value="傳送訊息給機器人擁有者", inline=False)
            #embed.add_field(name="/find <id>", value="搜尋指定ID", inline=False)
            embed.add_field(name="/draw [次數]", value="抽獎試手氣", inline=False)
            embed.add_field(name="/channel set", value="設定自動通知", inline=False)
            embed.add_field(name="/about", value="關於機器人的小資訊", inline=False)
            embed.set_footer(text="輸入/help user查詢指令用法")
            await ctx.respond(embed=embed)
        elif arg == 'use':
            embed = BotEmbed.bot(self.bot,"帶你了解基本的概念","使用指令")
            embed.add_field(name="指令使用:斜槓指令", value="打上/後，會有dc的提示幫助你`\n如果有參數，在輸入過程中都有提示", inline=False)
            embed.add_field(name="指令使用:前輟指令", value="前輟+指令就可以使用了，例如`/help`\n如果有參數，則需要把每個參數用空格隔開\n（此為舊版Discord使用指令的方式，本機器人目前全面採用斜槓指令）", inline=False)
            embed.add_field(name="括號", value="`<參數>`表示這個參數必填 `[參數]`表示不一定要填\n`<參數1/參數2>`為選擇一個參數填寫即可", inline=False)
            embed.set_footer(text="輸入/help use查詢指令用法")
            await ctx.respond(embed=embed)
        elif arg == 'pt':
            embed = BotEmbed.simple("點數系統(PT) 指令","點數系統尚在開發中，許多功能尚未完整")
            embed.add_field(name="/point", value="PT點數相關指令", inline=False)
            embed.add_field(name="/sign", value="每日簽到並領取點數", inline=False)
            embed.add_field(name="/shop", value="商城(敬請期待)", inline=False)
            embed.set_footer(text="輸入/help use查詢指令用法")
            await ctx.respond(embed=embed)
        elif arg == 'game':
            embed = BotEmbed.simple("遊戲(Game) 指令","可查詢遊戲資料")
            embed.add_field(name="/game set <遊戲> [資料]", value="設定遊戲名稱到資料庫中，設定後可在使用部分指令時讓機器人自動幫你輸入", inline=False)
            embed.add_field(name="/game find [用戶] [遊戲]", value="查詢用戶在資料庫內的遊戲名稱(目前僅能查詢自己的資料)", inline=False)
            embed.add_field(name="/lol", value="LOL相關指令", inline=False)
            embed.add_field(name="/osu player <玩家名/id>", value="查詢osu玩家", inline=False)
            embed.add_field(name="/osu map <圖譜id>", value="查詢osu圖譜", inline=False)
            embed.add_field(name="/apex player <玩家名/id>", value="查詢apex玩家", inline=False)
            embed.add_field(name="/apex map", value="查詢apex地圖輪替", inline=False)
            embed.add_field(name="/apex creafting", value="查詢apex合成台內容", inline=False)
            embed.add_field(name="/dbd player <steamid>", value="查詢DBD玩家", inline=False)
            #embed.add_field(name="/hoyo", value="查詢原神相關指令", inline=False)
            embed.set_footer(text="輸入/help use查詢指令用法")
            await ctx.respond(embed=embed)
        elif arg == 'channel':
            embed = BotEmbed.simple("通知設定(Channel) 指令","設定機器人自動通知\n若為定時通知，記得將機器人的訊息保持在頻道的最新訊息，以免機器人找不到訊息而重複發送")
            embed.add_field(name="/channel set", value="設定自動通知", inline=False)
            embed.add_field(name="/channel list", value="確認通知設定的頻道", inline=False)
            embed.add_field(name="/channel voice", value="設定動態語音", inline=False)
            embed.add_field(name="通知選項", value="- 全群公告：機器人的綜合通知\n- 機器人更新通知：告訴你機器人更新了什麼\n- Apex合成器與地圖輪替：(定時通知)\n- 地震通知/天氣預報(定時通知)：中央氣象局發布的地震報告與天氣預報\n- 管理員專用：新成員若有警告紀錄則會發訊息通知\n- 成員加入/離開：讓機器人告訴大家成員進出\n- 語音進出紀錄：紀錄伺服器內的語音進出", inline=False)
            embed.set_footer(text="輸入/help use查詢指令用法")
            await ctx.respond(embed=embed)
        elif arg == 'role':
            embed = BotEmbed.simple("身分組(Role) 指令")
            embed.add_field(name="/role count <用戶>", value="取得用戶的身分組數量(可批量輸入多個用戶)", inline=False)
            embed.add_field(name="/role add <名稱> [用戶]", value="取得用戶的身分組數量(可批量輸入多個用戶)", inline=False)
            embed.add_field(name="/role nick <名稱/顏色代碼>", value="更改稱號(顏色請輸入HEX格式)", inline=False)
            embed.set_footer(text="輸入/help use查詢指令用法")
            await ctx.respond(embed=embed)
        elif arg == 'bet':
            embed = BotEmbed.simple("賭盤(Bet) 指令","所有人可自由開類似Twitch的賭盤或使用PT點數下注")
            embed.add_field(name="/bet <賭盤ID> <blue/pink> <下注金額>", value="賭盤下注", inline=False)
            embed.add_field(name="/bet create <賭盤標題> <粉紅幫標題> <藍藍幫標題> <下注時間>", value="創建賭盤(時間格式為'10s''1m20s'等，不可超過600s)", inline=False)
            embed.add_field(name="/bet end <blue/pink>",value="結算賭盤",inline=False)
            embed.set_footer(text="輸入/help use查詢指令用法")
            await ctx.respond(embed=embed)
        elif arg == 'music':
            page = [BotEmbed.simple("音樂(music) 指令:")]
            page[0].add_field(name="/play <歌曲>", value="播放歌曲", inline=False)
            page[0].add_field(name="/queue", value="歌曲列表", inline=False)
            page[0].add_field(name="/nowplaying", value="現在播放的歌曲", inline=False)
            #page[0].add_field(name="/skip", value="投票跳過歌曲，需三個人才可跳過，點歌者可強制跳過", inline=False)
            page[0].add_field(name="/skip", value="跳過歌曲", inline=False)
            page[0].add_field(name="/pause", value="暫停/繼續播放", inline=False)
            #page[0].add_field(name="/resume", value="繼續播放", inline=False)
            page[0].add_field(name="/join", value="讓機器人加入你的語音", inline=False)
            #page[0].add_field(name="/summon [頻道]", value="讓機器人加入指定語音", inline=False)
            #page[0].add_field(name="/leave", value="讓機器人離開你的語音\n別名:disconnect,dc", inline=False)
            #page[0].add_field(name="/volume <音量>", value="設定音量", inline=False)
            page[0].add_field(name="/stop", value="停止播放歌曲並讓機器人離開頻道", inline=False)
            page[0].add_field(name="/shuffle", value="隨機撥放", inline=False)
            page[0].add_field(name="/loop", value="循環歌曲", inline=False)
            #page[1].add_field(name="/remove <歌曲位置>", value="移除歌曲\n別名:rm", inline=False)
            paginator = pages.Paginator(pages=page, use_default_buttons=True)
            #await paginator.send(ctx, target=ctx.channel)
            await paginator.respond(ctx.interaction, ephemeral=False)
        elif arg == 'weather':
            embed = BotEmbed.simple("天氣(weather) 指令")
            embed.add_field(name="/earthquake", value="查詢最新的顯著有感地震報告", inline=False)
            #embed.add_field(name="/covid", value="查詢最新的台灣疫情", inline=False)
            embed.add_field(name="/forecast ", value="查詢天氣預報", inline=False)
            embed.set_footer(text="輸入/help use查詢指令用法")
            await ctx.respond(embed=embed)
        # elif arg == 'math':
        #     embed = BotEmbed.simple("數學(math) 指令:")
        #     embed.add_field(name="/ma <A列數> <A行數>  <A> <B列數> <B行數> <B>", value='A*B矩陣乘法\n矩陣打法 : "數字1 數字2.... "\n前後加引號 每個數字用空格隔開 數字順序為 一列數字打完 再打下一列數字', inline=False)
        #     embed.set_footer(text="輸入/help use查詢指令用法")
        #     await ctx.respond(embed=embed)
        elif arg == 'user':
            embed = BotEmbed.simple("用戶(user) 指令")
            embed.add_field(name="/ui", value="關於你自己", inline=False)
            embed.add_field(name="/bag", value="查看背包", inline=False)
            embed.add_field(name="/pet", value='寵物相關指令', inline=False)
            embed.add_field(name="/advance", value='進行冒險', inline=False)
            embed.set_footer(text="輸入/help use查詢指令用法")
            await ctx.respond(embed=embed)
        elif arg == 'twitch':
            embed = BotEmbed.simple("圖奇(twitch) 指令")
            embed.add_field(name="/twitch set <twitch用戶> <頻道> [身分組]", value="設定twitch的開台通知", inline=False)
            embed.add_field(name="/twitch remove <twitch用戶>", value="移除twitch的開台通知", inline=False)
            embed.add_field(name="/twitch notify <twitch用戶>", value="檢查twitch的開台通知頻道", inline=False)
            embed.add_field(name="/twitch list", value="檢查群組所有的twitch開台通知頻道", inline=False)
            embed.add_field(name="/twitch user <twitch用戶>", value="查詢twitch用戶", inline=False)
            embed.set_footer(text="輸入/help use查詢指令用法")
            await ctx.respond(embed=embed)
        elif arg == 'admin':
            embed = BotEmbed.bot(self.bot,"目前可使用的指令如下(admin)")
            embed.add_field(name="/clean <訊息數/訊息ID>", value="清除訊息(需求管理訊息)", inline=False)
            embed.add_field(name="/warning add", value="給予用戶警告(需求踢出成員)", inline=False)
            embed.add_field(name="/timeout", value="禁言用戶(需求禁言成員)", inline=False)
            embed.add_field(name="/kick", value="踢除用戶(需求踢除成員)", inline=False)
            embed.add_field(name="/ban", value="停權用戶(需求停權成員)", inline=False)
            embed.set_footer(text="輸入/help use查詢指令用法")
            await ctx.respond(embed=embed)
    
    @commands.slash_command(description='owner幫助指令')
    @commands.is_owner()
    async def help_owner(self,ctx):
        embed = BotEmbed.bot(self.bot,"目前可使用的指令如下(onwer):")
        embed.add_field(name="/sendmessage", value="發送指定訊息", inline=False)
        embed.add_field(name="/anno", value="對所有伺服器進行公告", inline=False)
        embed.add_field(name="/botupdate", value="對所有伺服器發送機器人更新", inline=False)
        embed.add_field(name="/editmessage <訊息ID> <新訊息>", value="編輯訊息", inline=False)
        #embed.add_field(name="/reaction <訊息ID> <add/remove> <表情/表情ID>", value="添加/移除反應", inline=False)
        embed.add_field(name="/ptset <用戶ID> <+/-/set> <數量>", value="更改指定用戶Pt數", inline=False)
        embed.add_field(name="/role save", value="儲存身分組", inline=False)
        embed.add_field(name="/panel", value="機器人面板", inline=False)
        embed.add_field(name="/getcommand", value="獲取指令ID", inline=False)
        embed.add_field(name="/find", value="獲取ID的資訊", inline=False)
        embed.add_field(name="/findmember", value="找尋指定伺服器與主伺服器的共通成員", inline=False)
        embed.set_footer(text="輸入/help use查詢指令用法")
        await ctx.respond(embed=embed)


def setup(bot):
    bot.add_cog(help(bot))