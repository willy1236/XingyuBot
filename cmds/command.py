import discord
from discord.ext import commands
import json
from core.classes import Cog_Extension


jdata = json.load(open('setting.json','r',encoding='utf8'))


class command(Cog_Extension):
    # command
    @commands.command()
    async def info(self, ctx, arg):
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
            await ctx.send('參數錯誤，請輸入!!info help取得幫助',delete_after=5)

    @commands.group(invoke_without_command=True)
    @commands.cooldown(rate=1,per=3)
    async def help(self,ctx):
        bot_name = self.bot.user.name

        embed = discord.Embed(title=bot_name, description="目前可使用的指令如下:", color=0xc4e9ff)
        embed.add_field(name="!!info <內容/help>", value="獲得相關資訊", inline=False)
        embed.add_field(name="!!sign", value="每日簽到(更多功能敬請期待)", inline=False)
        embed.add_field(name="!!lol <player> <玩家名稱>", value="查詢LOL戰績(更多功能敬請期待)", inline=False)
        #embed.add_field(name="!!osu <player> <玩家名稱>", value="查詢Osu玩家(更多功能敬請期待)", inline=False)
        embed.add_field(name="!!pt [用戶ID]", value="查詢Pt數", inline=False)
        embed.add_field(name="!!pt give <用戶ID> <數量>", value="將Pt轉給指定用戶", inline=False)
        embed.add_field(name="!!find <id>", value="搜尋指定用戶", inline=False)
        embed.add_field(name="!!feedback <內容>", value="傳送訊息給機器人擁有者", inline=False)
        embed.add_field(name="!!game <遊戲> <資料>", value="設定你在資料庫內的遊戲名稱", inline=False)
        

        await ctx.send(embed=embed)
    
    @help.command()
    @commands.is_owner()
    async def owner(self,ctx):
        bot_name = self.bot.user.name

        embed = discord.Embed(title=bot_name, description="目前可使用的指令如下(onwer):", color=0xc4e9ff)
        embed.add_field(name="!!send <頻道ID/用戶ID/0> <內容>", value="發送指定訊息", inline=False)
        embed.add_field(name="!!all_anno <內容>", value="對所有伺服器進行公告", inline=False)
        embed.add_field(name="!!edit <訊息ID> <新訊息>", value="編輯訊息", inline=False)
        embed.add_field(name="!!reaction <訊息ID> <add/remove> <表情/表情ID>", value="添加/移除反應", inline=False)
        embed.add_field(name="!!ptset <用戶ID> <+/-/set> <數量>", value="更改指定用戶Pt數", inline=False)
        embed.add_field(name="!!reset", value="簽到重置", inline=False)
        
        await ctx.send(embed=embed)

    @help.command()
    async def admin(self,ctx):
        bot_name = self.bot.user.name

        embed = discord.Embed(title=bot_name, description="目前可使用的指令如下(admin):", color=0xc4e9ff)
        embed.add_field(name="!!clean <數字>", value="清除訊息(需求管理訊息)", inline=False)
        
        await ctx.send(embed=embed)

    @commands.command()
    async def find(self,ctx,user_id:int):
        member = ctx.guild.get_member(user_id)
        if member != None:
            embed = discord.Embed(title=f'{member.name}#{member.discriminator}', description="此用戶的資訊如下", color=0xc4e9ff)
            embed.add_field(name="暱稱", value=member.nick, inline=False)
            embed.add_field(name="是否為機器人", value=member.bot, inline=False)
            embed.add_field(name="最高身分組", value=member.top_role.mention, inline=True)
            embed.add_field(name="目前狀態", value=member.status, inline=True)
            embed.add_field(name="帳號創建日期", value=member.created_at, inline=False)
            embed.set_thumbnail(url=member.avatar_url)
            await ctx.send(embed=embed)
        else:
            user = await self.bot.fetch_user(user_id)
            embed = discord.Embed(title=f'{user.name}#{user.discriminator}', description="此用戶的資訊如下", color=0xc4e9ff)
            embed.add_field(name="是否為機器人", value=user.bot, inline=False)
            embed.add_field(name="是否為Discord官方", value=user.system, inline=False)
            embed.add_field(name="帳號創建日期", value=user.created_at, inline=False)
            embed.set_thumbnail(url=user.avatar_url)
            await ctx.send(embed=embed)

    @commands.command()
    @commands.cooldown(rate=1,per=10)
    async def feedback(self,ctx,text):
        user = ctx.author
        guild = ctx.guild
        channel = ctx.channel
        feedback_channel = self.bot.get_channel(jdata['feedback_channel'])
        embed = discord.Embed(color=0xc4e9ff)
        embed.add_field(name='廣播電台 | 回饋訊息', value=text, inline=False)
        embed.set_author(name=f'{user}',icon_url=f'{user.avatar_url}')
        embed.set_footer(text=f'來自: {guild}, {channel}')

        await feedback_channel.send(embed=embed)

    @commands.command(enabled=True)
    async def test(self,ctx,user:commands.MemberConverter):
        await ctx.send(user)
        

def setup(bot):
    bot.add_cog(command(bot))