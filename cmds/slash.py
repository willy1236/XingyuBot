import discord
from discord.ext import commands,pages
import random,asyncio
from discord.commands import SlashCommandGroup

from BotLib.funtions import find,converter,random_color,BRS
from core.classes import Cog_Extension
from BotLib.database import Database
from BotLib.basic import BotEmbed

class slash(Cog_Extension):
    picdata = Database().picdata
    rsdata = Database().rsdata

    role = SlashCommandGroup("role", "身分組管理指令",guild_only=True,guild_ids=[566533708371329024])

    @role.command(description='查詢身分組數')
    async def count(self,ctx,user_list:discord.Option(str,required=False,name='要查詢的用戶',description='多個用戶請用空格隔開，或可輸入default查詢常用人選')):
        await ctx.defer()
        if 'default' in user_list:
            user_list = (419131103836635136,528935362199027716,465831362168094730,539405949681795073,723435216244572160,490136735557222402)
        embed=BotEmbed.general("身分組計算結果")
        rsdata = Database().rsdata
        for i in user_list:
            user = await find.user(ctx,i)
            if user:
                role_count = len(rsdata[str(user.id)])
                embed.add_field(name=user.name, value=f"{role_count}", inline=False)
        await ctx.respond(embed=embed)

    @role.command(description='加身分組')
    @commands.cooldown(rate=1,per=5)
    async def add(self,
                ctx:discord.ApplicationContext,
                name:discord.Option(str,name='身分組名',description='新身分組名稱'),
                user_list:discord.Option(str,required=False,name='要加身份組的用戶',description='多個用戶請用空格隔開')
                ):
        await ctx.defer()
        permission = discord.Permissions.none()
        r,g,b=random_color(200)
        color = discord.Colour.from_rgb(r,g,b)
        new_role = await ctx.guild.create_role(name=name,permissions=permission,color=color)
        added_role = []
        if user_list:
            user_list = user_list.split()
            for user in user_list:
                user = await find.user(ctx,user)
                if user and user != self.bot.user:
                    await user.add_roles(new_role,reason='指令:加身分組')
                    added_role.append(user)
                    print(added_role)
                elif user == self.bot.user:
                    await ctx.respond("請不要加我身分組好嗎")
                elif user and user.bot:
                    await ctx.respond("請不要加機器人身分組好嗎")
        
        if added_role != []:
            all_user = ''
            for user in added_role:
                all_user += f' {user.mention}'
            await ctx.respond(f"已添加 {new_role.name} 給{all_user}")
        else:
            await ctx.respond(f"已創建 {new_role.name} 身分組")


    @role.command(description='儲存身分組')
    @commands.cooldown(rate=1,per=5)
    @commands.is_owner()
    async def save(self,
                    ctx:discord.ApplicationContext,
                    user:discord.Option(str,name='用戶名',description='輸入all可儲存所有身分組')
                    ):
        def save_role(user):
            rsdata = self.rsdata
            roledata = rsdata.get(str(user.id),{})
            for role in user.roles:
                if role.id == 877934319249797120:
                    break
                if role.name == '@everyone':
                    continue
                if str(role.id) not in roledata:
                    print(f'新增:{role.name}')
                roledata[str(role.id)] = [role.name,role.created_at.strftime('%Y%m%d')]
                rsdata[str(user.id)] = roledata
            Database().write('rsdata',rsdata)
        
        await ctx.defer()
        jdata = Database().jdata
        guild = self.bot.get_guild(jdata['guild']['001'])
        add_role = guild.get_role(877934319249797120)
        if user == 'all':
            for user in add_role.members:
                save_role(user)
            await ctx.respond('身分組儲存完成',delete_after=5)
        else:
            user = await find.user(ctx,user)
            if user != None and add_role in user.roles:
                save_role(user)
                await ctx.respond('身分組儲存完成',delete_after=5)
            elif add_role not in user.roles:
                await ctx.respond('錯誤:此用戶沒有"加身分組"')

    @role.command(description='清除身分組')
    @commands.is_owner()
    async def rsmove(self,ctx):
        await ctx.defer()
        for user in ctx.guild.get_role(877934319249797120).members:
            print(user.name)
            for role in user.roles:
                if role.id == 877934319249797120:
                    break
                if role.name == '@everyone':
                    continue
                print(f'已移除:{role.name}')
                await role.delete()
                asyncio.sleep(0.5)
        await ctx.respond('身分組清理完成',delete_after=5)

    @role.command(description='更改暱稱')
    async def nick(self, ctx, arg:discord.Option(str,name='欲更改的內容',description='可輸入新暱稱或輸入以#開頭的6位顏色代碼')):
        await ctx.defer()
        user = ctx.author
        role = user.roles[-1]
        if role.name.startswith('稱號 | '):
            if arg.startswith('#'):
                await role.edit(colour=arg,reason='稱號:顏色改變')
            else:
                await role.edit(name=f'稱號 | {arg}',reason='稱號:名稱改變')
            await ctx.respond('暱稱更改完成',delete_after=5)
        else:
            await ctx.respond(f'錯誤:{ctx.author.mention}沒有稱號可更改',delete_after=5)

    @role.command(description='身分組紀錄')
    async def record(self, ctx, user:discord.Option(discord.Member,name='欲查詢的成員',description='可不輸入以查詢自己',default=None)):
        await ctx.defer()
        user = user or ctx.author
        db = Database()
        rsdata = db.rsdata
        if str(user.id) in rsdata:
            id = str(user.id)
            page = []
            i = 0
            page_now = 0
            page.append(BotEmbed.simple(f"{user.name} 身分組紀錄"))
            for role in rsdata[id]:
                if i >= 10:
                    page.append(BotEmbed.simple(f"{user.name} 身分組紀錄"))
                    i = 0
                    page_now += 1
                name = rsdata[id][role][0]
                time = rsdata[id][role][1]
                page[page_now].add_field(name=name, value=time, inline=False)
                i += 1

            paginator = pages.Paginator(pages=page, use_default_buttons=True)
            await paginator.respond(ctx.interaction, ephemeral=False)
            
        else:
            raise commands.errors.ArgumentParsingError('沒有此用戶的紀錄')

    @commands.slash_command(description='向大家說哈瞜')
    async def hello(self,ctx, name: str = None):
        await ctx.defer()
        name = name or ctx.author.name
        await ctx.respond(f"Hello {name}!")


    @commands.user_command(guild_ids=[566533708371329024])  # create a user command for the supplied guilds
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

    @commands.slash_command(description='傳送訊息給伺服器擁有者',guild_ids=[566533708371329024])
    @commands.cooldown(rate=1,per=10)
    async def feedback( self,
                        ctx:discord.ApplicationContext,
                        text:discord.Option(str,name='訊息',description='要傳送的訊息內容'),
                        ):
        await ctx.defer()
        await BRS.feedback(self,ctx,text)
        await ctx.respond(f"訊息已發送!",ephemeral=True,delete_after=3)

    @staticmethod
    def Autocomplete(self: discord.AutocompleteContext):
        return ['test']

    @commands.slash_command(description='讓機器人選擇一樣東西',guild_ids=[566533708371329024])
    async def choice(self,ctx,args:discord.Option(str,required=False,name='選項',description='多個選項請用空格隔開')):
        args = args.split()
        result = random.choice(args)
        await ctx.respond(f'我選擇:{result}')

def setup(bot):
    bot.add_cog(slash(bot))
    