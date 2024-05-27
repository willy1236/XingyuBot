import discord,datetime
from discord.ext import commands
from discord.commands import SlashCommandGroup
from starcord.DataExtractor import TwitchAPI,YoutubeAPI,YoutubeRSS
from starcord.ui_element.view import ReactionRole1, WelcomeView
from starcord import Cog_Extension,BotEmbed,sclient,Jsondb,ChoiceList

twitch_notify_option = ChoiceList.set("twitch_notify_option")

class system_community(Cog_Extension):
    twitch = SlashCommandGroup("twitch", "Twitch相關指令")
    youtube = SlashCommandGroup("youtube", "youtube相關指令")
    
    @twitch.command(description='設置twitch開台通知')
    async def set(self,ctx,
                  twitch_user:discord.Option(str,required=True,name='twitch用戶',description='當此用戶開台時會發送通知'),
                  channel:discord.Option(discord.TextChannel,required=True,name='頻道',description='通知發送頻道'),
                  role:discord.Option(discord.Role,required=False,default=None,name='身分組',description='發送通知時tag的身分組')):
        guildid = ctx.guild.id
        channelid = channel.id
        roleid = role.id if role else None

        user = TwitchAPI().get_user(twitch_user)
        if user:
            sclient.sqldb.set_notify_community('twitch',twitch_user,guildid,channelid,roleid)
            if role:
                await ctx.respond(f'設定成功：{user.display_name}({user.login})的開台通知將會發送在{channel.mention}並會通知{role.mention}')
            else:
                await ctx.respond(f'設定成功：{user.display_name}({user.login})的開台通知將會發送在{channel.mention}')
                
            sclient.scheduler.add_job(sclient.init_NoticeClient,"date",args=["twitch"])
        else:
            await ctx.respond(f'錯誤：找不到用戶{twitch_user}')

    @twitch.command(description='設置twitch影片通知')
    async def video(self,ctx,
                  twitch_user:discord.Option(str,required=True,name='twitch用戶',description='當此用戶有新影片時會發送通知'),
                  channel:discord.Option(discord.TextChannel,required=True,name='頻道',description='通知發送頻道'),
                  role:discord.Option(discord.Role,required=False,default=None,name='身分組',description='發送通知時tag的身分組')):
        guildid = ctx.guild.id
        channelid = channel.id
        roleid = role.id if role else None
        api = TwitchAPI()
        user = api.get_user(twitch_user)
        if user:
            sclient.sqldb.set_notify_community('twitch_v',user.id,guildid,channelid,roleid,user.login)
            if role:
                await ctx.respond(f'設定成功：{user.display_name}({user.login})的影片通知將會發送在{channel.mention}並會通知{role.mention}')
            else:
                await ctx.respond(f'設定成功：{user.display_name}({user.login})的影片通知將會發送在{channel.mention}')
                
            sclient.scheduler.add_job(sclient.init_NoticeClient,"date",args=["twitch_v"])

            cache = Jsondb.read_cache('twitch_v')
            cache[user.id] = api.get_videos(user.id)[0].created_at.isoformat()
            Jsondb.write_cache('twitch_v',cache)

        else:
            await ctx.respond(f'錯誤：找不到用戶{twitch_user}')

    @twitch.command(description='設置twitch剪輯通知')
    async def clip(self,ctx,
                  twitch_user:discord.Option(str,required=True,name='twitch用戶',description='當此用戶有新影片時會發送通知'),
                  channel:discord.Option(discord.TextChannel,required=True,name='頻道',description='通知發送頻道'),
                  role:discord.Option(discord.Role,required=False,default=None,name='身分組',description='發送通知時tag的身分組')):
        guildid = ctx.guild.id
        channelid = channel.id
        roleid = role.id if role else None
        api = TwitchAPI()
        user = api.get_user(twitch_user)
        if user:
            sclient.sqldb.set_notify_community('twitch_c',user.id,guildid,channelid,roleid,user.login)
            if role:
                await ctx.respond(f'設定成功：{user.display_name}({user.login})的剪輯通知將會發送在{channel.mention}並會通知{role.mention}')
            else:
                await ctx.respond(f'設定成功：{user.display_name}({user.login})的剪輯通知將會發送在{channel.mention}')
                
            sclient.scheduler.add_job(sclient.init_NoticeClient,"date",args=["twitch_c"])

            cache = Jsondb.read_cache('twitch_c')
            cache[user.id] = datetime.datetime.now().isoformat()
            Jsondb.write_cache('twitch_c',cache)

        else:
            await ctx.respond(f'錯誤：找不到用戶{twitch_user}')
    
    @twitch.command(description='移除twitch開台通知')
    async def remove(self,ctx,
                     twitch_user:discord.Option(str,required=True,name='twitch用戶'),
                     notify_type:discord.Option(str,required=False,name='通知種類',description='通知種類，留空為移除全部',choices=twitch_notify_option)):
        guildid = ctx.guild.id
        user = TwitchAPI().get_user(twitch_user)
        if not notify_type or notify_type == "1":
            sclient.sqldb.remove_notify_community('twitch',twitch_user,guildid)
        if not notify_type or notify_type == "2":
            sclient.sqldb.remove_notify_community('twitch_v',twitch_user,guildid)
            
            cache = Jsondb.read_cache('twitch_v')
            del cache[user.id]
            Jsondb.write_cache('twitch_v',cache)

        if not notify_type or notify_type == "3":
            sclient.sqldb.remove_notify_community('twitch_c',twitch_user,guildid)

            cache = Jsondb.read_cache('twitch_c')
            del cache[user.id]
            Jsondb.write_cache('twitch_c',cache)
        
        await ctx.respond(f'已移除 {twitch_user} 的通知')
        
        sclient.scheduler.add_job(sclient.init_NoticeClient,"date",args=["twitch","twitch_v","twitch_c"])

    @twitch.command(description='確認twitch開台通知')
    async def notify(self,ctx,twitch_user:discord.Option(str,required=True,name='twitch用戶')):
        guildid = ctx.guild.id
        record = sclient.sqldb.get_notify_community_user('twitch',twitch_user,guildid)
        if record:
            channel = self.bot.get_channel(record[0]['channel_id'])
            role = channel.guild.get_role(record[0]['role_id'])
            if role:
                await ctx.respond(f'TwitchID: {twitch_user} 的開台通知在 {channel.mention} 並通知 {role.mention}')
            else:
                await ctx.respond(f'TwitchID: {twitch_user} 的開台通知在 {channel.mention}')
        else:
            await ctx.respond(f'TwitchID: {twitch_user} 在此群組沒有設開台通知')
    
    @twitch.command(description='確認群組內所有的twitch開台通知')
    async def list(self,ctx):
        guildid = ctx.guild.id
        embed = BotEmbed.general("twitch開台通知",ctx.guild.icon.url if ctx.guild.icon else None)
        dbdata = sclient.sqldb.get_notify_community_list('twitch',guildid) + sclient.sqldb.get_notify_community_list('twitch_v',guildid) + sclient.sqldb.get_notify_community_list('twitch_c',guildid)
        for data in dbdata:
            display_name = data['display_name'] if data['display_name'] else data['notify_name']
            channel_id = data['channel_id']
            role_id = data['role_id']
            
            if data['notify_type'] == "twitch_v":
                display_name += "（影片）"

            if data['notify_type'] == "twitch_c":
                display_name += "（剪輯）"

            channel = self.bot.get_channel(channel_id)
            if role_id:
                role = ctx.guild.get_role(role_id)
            else:
                role = None

            text = "找不到頻道"
            if channel:
                text = channel.mention
                if role:
                    text += f" {role.mention}"
            embed.add_field(name=display_name, value=text)
        await ctx.respond(embed=embed)

    @twitch.command(description='取得twitch頻道的相關資訊')
    async def user(self,ctx,twitch_username:discord.Option(str,required=True,name='twitch用戶')):
        user = TwitchAPI().get_user(twitch_username)
        if user:
            await ctx.respond(embed=user.desplay())
        else:
            await ctx.respond(f"查詢不到用戶：{twitch_username}",ephemeral=True)

    @youtube.command(description='取得youtube頻道的相關資訊')
    async def channel(self,ctx,youtube_handle:discord.Option(str,required=True,name='youtube帳號代碼',description="youtube頻道中以@開頭的代號")):
        ytapi = YoutubeAPI()
        channel = ytapi.get_channel(handle=youtube_handle)
        if channel:
            await ctx.respond("查詢成功",embed=channel.embed())
        else:
            await ctx.respond("查詢失敗",ephemeral=True)

    @youtube.command(description='設置youtube開台通知')
    async def set(self,ctx,
                  ythandle:discord.Option(str,required=True,name='youtube帳號代碼',description="youtube頻道中以@開頭的代號"),
                  channel:discord.Option(discord.TextChannel,required=True,name='頻道',description='通知發送頻道'),
                  role:discord.Option(discord.Role,required=False,default=None,name='身分組',description='發送通知時tag的身分組')):
        guildid = ctx.guild.id
        channelid = channel.id
        roleid = role.id if role else None

        ytchannel = YoutubeAPI().get_channel(handle=ythandle)
        if ytchannel:
            sclient.sqldb.set_notify_community('youtube',ytchannel.id,guildid,channelid,roleid,ytchannel.title)
            if role:
                await ctx.respond(f'設定成功：{ytchannel.title}的通知將會發送在{channel.mention}並會通知{role.mention}')
            else:
                await ctx.respond(f'設定成功：{ytchannel.title}的通知將會發送在{channel.mention}')
                
            sclient.scheduler.add_job(sclient.init_NoticeClient,"date",args=["youtube"])

            feed = YoutubeRSS().get_videos(ytchannel.id)
            updated_at = feed[0].updated_at.isoformat() if feed else None
            cache = Jsondb.read_cache("youtube")
            cache[ytchannel.id] = updated_at
            Jsondb.write_cache('youtube',cache)
        else:
            await ctx.respond(f'錯誤：找不到帳號代碼 {ythandle} 的頻道')

    @youtube.command(description='移除youtube通知')
    async def remove(self,ctx,ythandle:discord.Option(str,required=True,name='youtube帳號代碼',description="youtube頻道中以@開頭的代號")):
        guildid = ctx.guild.id

        ytchannel = YoutubeAPI().get_channel(handle=ythandle)
        if not ytchannel:
            await ctx.respond(f'錯誤：找不到帳號代碼 {ythandle} 的頻道')
            return

        sclient.sqldb.remove_notify_community('youtube',ytchannel.id,guildid)
        await ctx.respond(f'已移除頻道 {ytchannel.title} 的通知')
        
        sclient.scheduler.add_job(sclient.init_NoticeClient,"date",args=["youtube"])

        cache = Jsondb.read_cache("youtube")
        del cache[ytchannel.id]
        Jsondb.write_cache('youtube',cache)

    @youtube.command(description='確認youtube通知')
    async def notify(self,ctx,ythandle:discord.Option(str,required=True,name='youtube帳號代碼',description="youtube頻道中以@開頭的代號")):
        guildid = ctx.guild.id
        
        ytchannel = YoutubeAPI().get_channel(handle=ythandle)
        if not ytchannel:
            await ctx.respond(f'錯誤：找不到帳號代碼 {ythandle} 的頻道')
            return
        
        record = sclient.sqldb.get_notify_community_user('youtube',ytchannel.id,guildid)
        if record:
            channel = self.bot.get_channel(record[0]['channel_id'])
            role = channel.guild.get_role(record[0]['role_id'])
            if role:
                await ctx.respond(f'Youtube頻道: {ytchannel.title} 的通知在 {channel.mention} 並通知 {role.mention}')
            else:
                await ctx.respond(f'Youtube頻道: {ytchannel.title} 的通知在 {channel.mention}')
        else:
            await ctx.respond(f'Youtube頻道: {ytchannel.title} 在此群組沒有設通知')
    
    @youtube.command(description='確認群組內所有的youtube通知')
    async def list(self,ctx):
        guildid = ctx.guild.id
        embed = BotEmbed.general("youtube通知",ctx.guild.icon.url if ctx.guild.icon else discord.Embed.Empty)
        dbdata = sclient.sqldb.get_notify_community_list('youtube',guildid)
        for data in dbdata:
            notify_name = data['display_name'] if data.get("display_name") else data['notify_name']
            channel_id = data['channel_id']
            role_id = data['role_id']
            
            channel = self.bot.get_channel(channel_id)
            if role_id:
                role = ctx.guild.get_role(role_id)
            else:
                role = None

            text = "找不到頻道"
            if channel:
                text = channel.mention
                if role:
                    text += f" {role.mention}"
            embed.add_field(name=notify_name, value=text)
        await ctx.respond(embed=embed)

    @commands.slash_command(description='加入伺服器按鈕',debug_guilds=[1058234922076217415])
    @commands.has_permissions(manage_channels=True)
    async def welcome(self, ctx):
        view = WelcomeView()
        await ctx.channel.send(view=view)
        await ctx.respond("按鈕創建完成",ephemeral=True)

    @commands.slash_command(description='反應身分組按鈕',debug_guilds=[1058234922076217415])
    @commands.has_permissions(manage_channels=True)
    async def reactionrole(self, ctx):
        view = ReactionRole1()
        await ctx.channel.send("請依自身喜好點選身分組",view=view)
        await ctx.respond("按鈕創建完成",ephemeral=True)

def setup(bot):
    bot.add_cog(system_community(bot))
