import discord
from discord.ext import commands
import json
from core.classes import Cog_Extension

with open('setting.json',mode='r',encoding='utf8') as jfile:
    jdata = json.load(jfile)

class reaction(Cog_Extension):
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        #新增
        if int(payload.message_id) == int(jdata['mg.reaction_role.message']):
            guild = self.bot.get_guild(payload.guild_id)
            if str(payload.emoji) == '🎮':
                    role = guild.get_role(727805704492023827)
                    await payload.member.add_roles(role)
                    await payload.member.send(f'你取得了 {role} 身分組!')

            if str(payload.emoji) == '🍍':
                    role = guild.get_role(707213815460397057)
                    await payload.member.add_roles(role)
                    await payload.member.send(f'你取得了 {role} 身分組!')

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        #遊戲區 移除
        if int(payload.message_id) == int(jdata['mg.reaction_role.message']):
            guild = self.bot.get_guild(payload.guild_id)
            user = guild.get_member(payload.user_id)
            if str(payload.emoji) == '🎮':
                    role = guild.get_role(727805704492023827)
                    await user.remove_roles(role)
                    await user.send(f'你移除了 {role} 身分組!')

            if str(payload.emoji) == '🍍':
                    role = guild.get_role(707213815460397057)
                    await user.remove_roles(role)
                    await user.send(f'你移除了 {role} 身分組!')


def setup(bot):
    bot.add_cog(reaction(bot))