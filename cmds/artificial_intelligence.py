import os,discord
import openai
from core.classes import Cog_Extension
from discord.ext import commands
from bothelper import Jsondb

openai.api_key = Jsondb.get_token('openai')


class artificial_intelligence(Cog_Extension):
    @commands.cooldown(rate=1,per=5)
    @commands.slash_command(description='既然ChatGPT那麼紅，那為何不試試看跟AI聊天呢?')
    async def chat(self,ctx,content:discord.Option(str,name='訊息',description='要傳送的訊息內容')):
        await ctx.defer()
        response = openai.Completion.create(
        model="text-davinci-003",
        prompt=content,
        temperature=0.9,
        max_tokens=150,
        top_p=1,
        frequency_penalty=0.0,
        presence_penalty=0.6,
        stop=[" Human:", " AI:"]
        )
        text = response['choices'][0]['text']
        await ctx.respond(text)

def setup(bot):
    bot.add_cog(artificial_intelligence(bot))
