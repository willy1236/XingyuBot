import discord
from discord.ext import commands
import youtube_dl
from core.classes import Cog_Extension

class music(Cog_Extension):
  @commands.command()
  async def join(self,ctx):
   if ctx.author.voice is None:
     await ctx.send("I Cannont detect you within the void, Mortal.")
   voice_channel = ctx.author.voice.channel
   if ctx.voice_client is None:
     await voice_channel.connect()
   else:
     await ctx.voice_client.move_to(voice_channel)

  @commands.command()
  async def disconnect(self,ctx):
     await ctx.voice_client.disconnect()

  @commands.command()
  async def play(self,ctx,url):
   await ctx.voice_client.stop()
   FFMPEG_OPTIONS = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn'}
   YDL_OPTIONS = {'format':"bestaudio"}
   vc = ctx.voice_client

   with youtube_dl.YoutubeDL(YPL_OPTIONS) as ydl:
     info = ydl.extract_info(url, download=False)
     url2 = info['formats'][0]['url']
     source = await discord.FFmpegOpusAudio.from_probe(url2, **FFMPEG_OPTIONS)
     vc.play(source)

  @commands.command()
  async def pause(self,ctx):
   await ctx.voice_client.pause()
   await ctx.send("If you wish it, Mortal, i shall hold.")

  @commands.command()
  async def resume(self,ctx):
   await ctx.voice_client.resume()
   await ctx.send("I shall continue my song then, Mortal.")



def setup(bot):
  bot.add_cog(music(bot))