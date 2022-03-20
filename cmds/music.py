#from socket import IP_OPTIONS
import discord
from discord.ext import commands
import youtube_dl
from core.classes import Cog_Extension

class music(Cog_Extension):
    @commands.command()
    async def join(self,ctx):
        if not ctx.author.voice:
            await ctx.send("你必須要先進入一個語音頻道")
        else:
            voice_channel = ctx.author.voice.channel
            if not ctx.voice_client:
                await voice_channel.connect()
            else:
                await ctx.voice_client.move_to(voice_channel)

    @commands.command(aliases=['dc'])
    async def disconnect(self,ctx):
        await ctx.voice_client.disconnect()

    @commands.command(aliases=['p'])
    async def play(self,ctx,url):
        voice_channel = ctx.author.voice.channel
        if not ctx.voice_client:
            await voice_channel.connect()
        #await ctx.voice_client.stop()
        FFMPEG_OPTIONS = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn'}
        #YDL_OPTIONS = {'format':"bestaudio"}
        YDL_OPTIONS = {'format': 'bestaudio/best', 'noplaylist':'True'}
        
        vc = ctx.voice_client
        #voice = get(client.voice_clients, guild=ctx.guild)
        with youtube_dl.YoutubeDL(YDL_OPTIONS) as ydl:
            info = ydl.extract_info(url, download=False)
            url2 = info['formats'][0]['url']
            #print(url2,'\n',info,'\n',info['formats'])
            source = await discord.FFmpegOpusAudio.from_probe(url2, **FFMPEG_OPTIONS)
            vc.play(source)
            vc.is_playing()

    @commands.command(aliases=['pa'])
    async def pause(self,ctx):
        await ctx.voice_client.pause()
        await ctx.send("已暫停歌曲")

    @commands.command(aliases=['rs'])
    async def resume(self,ctx):
        await ctx.voice_client.resume()
        await ctx.send("繼續撥放")



def setup(bot):
  bot.add_cog(music(bot))