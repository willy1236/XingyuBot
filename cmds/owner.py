import discord
from discord.ext import commands

from library import find,BRS
from core.classes import Cog_Extension
from BotLib.user import *
from BotLib.basic import Database

class owner(Cog_Extension):
    cdata = Database().cdata
    
    #send
    @commands.command()
    @commands.is_owner()
    async def send(self,ctx,id:int,*,msg):
        channel = self.bot.get_channel(id)
        if id == 0:
            await ctx.send(msg)
            await ctx.message.delete()
        elif channel == None:
            user = self.bot.get_user(id)
            await user.send(msg)
            await ctx.send(f'訊息發送成功',delete_after=5)
        else:
            await channel.send(msg)
            await ctx.send(f'訊息發送成功',delete_after=5)

    #all_anno
    @commands.command()
    @commands.is_owner()
    async def anno(self,ctx,*,msg):
        send_success = 0
        send_msg = await ctx.send('訊息發送中...')

        embed= BRS.all_anno(msg)
        
        for i in self.cdata['all_anno']:
            channel = self.bot.get_channel(self.cdata['all_anno'][i])
            if channel != None:
                try:
                    await channel.send(embed=embed)
                    send_success += 1
                except:
                    pass
        await ctx.message.delete()
        await send_msg.edit(f"已向{send_success}/{len(self.cdata['all_anno'])}個頻道發送公告",delete_after=5)

    #edit
    @commands.command()
    @commands.is_owner()
    async def edit(self,ctx,msgid:int,*,new_msg):
        message = await ctx.fetch_message(msgid)
        await message.edit(content=new_msg)
        await ctx.message.add_reaction('✅')

    #reaction
    @commands.command()
    @commands.is_owner()
    async def reaction(self,ctx,msgid:int,mod:str,*,emojiid):
        message = await ctx.fetch_message(msgid)
        channel = message.channel
        emoji = find.emoji(emojiid)

        if emoji == None:
            await ctx.send(f'反應添加失敗:找不到表情符號',delete_after=5)
        elif mod == 'add':
            await message.add_reaction(emoji)
            await ctx.send(f'反應添加完成,{channel.mention}',delete_after=10)
        elif mod == 'remove':
            await message.remove_reaction(emoji,member=self.bot.user)
            await ctx.send(f'反應移除完成,{channel.mention}',delete_after=10)
        else:
            ctx.send('參數錯誤:請輸入正確模式(add/remove)',delete_after=5)

    @commands.command()
    @commands.is_owner()
    async def permission(self,ctx,guild_id:int):
        guild = self.bot.get_guild(guild_id)
        member = guild.get_member(ctx.bot.user.id)
        permission = member.guild_permissions

        embed = discord.Embed(title=guild.name, color=0xc4e9ff)
        embed.add_field(name="管理員", value=permission.administrator, inline=True)
        embed.add_field(name="管理頻道", value=permission.manage_channels, inline=True)
        embed.add_field(name="管理公會", value=permission.manage_guild, inline=True)
        embed.add_field(name="管理訊息", value=permission.manage_messages, inline=True)
        embed.add_field(name="管理暱稱", value=permission.manage_nicknames, inline=True)
        embed.add_field(name="管理身分組", value=permission.manage_roles, inline=True)
        embed.add_field(name="管理webhook", value=permission.manage_webhooks, inline=True)
        embed.add_field(name="管理表情符號", value=permission.manage_emojis, inline=True)
        embed.add_field(name="踢出成員", value=permission.kick_members, inline=True)
        embed.add_field(name="封鎖成員", value=permission.ban_members, inline=True)
        embed.add_field(name="觀看審核日誌", value=permission.view_audit_log, inline=True)
        # permission.create_instant_invite
        # permission.add_reactions
        # permission.priority_speaker
        # permission.stream
        # permission.read_messages
        # permission.send_messages
        # permission.send_tts_messages
        # permission.embed_links
        # permission.attach_files
        # permission.read_message_history
        # permission.mention_everyone
        # permission.external_emojis
        # permission.view_guild_insights
        # permission.connect
        # permission.speak
        # permission.mute_members
        # permission.deafen_members
        # permission.move_members
        # permission.use_voice_activation
        # permission.change_nickname
        # permission.use_slash_commands
        # permission.request_to_speak
        await ctx.send(embed=embed)

# @bot.event
# async def on_message(message):
#     if message.content.startswith('$thumb'):
#         channel = message.channel
#         await channel.send('Send me that 👍 reaction, mate')

#         def check(reaction, user):
#             return user == message.author and str(reaction.emoji) == '👍'

#         try:
#             reaction, user = await bot.wait_for('reaction_add', timeout=60.0, check=check)
#         except asyncio.TimeoutError:
#             await channel.send('👎')
#         else:
#             await channel.send('👍')

def setup(bot):
    bot.add_cog(owner(bot))