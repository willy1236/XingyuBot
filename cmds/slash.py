import discord
from discord.ext import commands
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

    @role.command(description='加身分組')
    @commands.cooldown(rate=1,per=5)
    async def add(self,
                ctx:discord.ApplicationContext,
                name:discord.Option(str,name='身分組名',description='新身分組名稱'),
                user_list:discord.Option(str,required=False,name='要加身份組的用戶',description='多個用戶請用空格隔開，若無則留空')
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
                elif user == self.bot.user:
                    await ctx.send("請不要加我身分組好嗎")
                elif user.bot:
                    await ctx.send("請不要加機器人身分組好嗎")
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
            dict = self.rsdata
            roledata = dict.get(str(user.id),{})
            for role in user.roles:
                if role.id == 877934319249797120:
                    break
                if role.name == '@everyone':
                    continue
                if str(role.id) not in roledata:
                    print(f'新增:{role.name}')
                roledata[str(role.id)] = [role.name,role.created_at.strftime('%Y%m%d')]
                dict[str(user.id)] = roledata
            Database().write('rsdata',dict)
        
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
        await ctx.respond(embed=embed)

    @commands.slash_command(description='傳送訊息給伺服器擁有者',guild_ids=[566533708371329024])
    @commands.cooldown(rate=1,per=10)
    async def feedback( self,
                        ctx:discord.ApplicationContext,
                        text:discord.Option(str,name='訊息',description='要傳送的訊息內容'),
                        ):
        await ctx.defer()
        await BRS.feedback(self,ctx,text)
        await ctx.respond(f"訊息已發送!",ephemeral=True,delete_after=3)

def setup(bot):
    bot.add_cog(slash(bot))
    