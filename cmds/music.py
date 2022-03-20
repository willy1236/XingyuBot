#from socket import IP_OPTIONS
import discord
from discord.ext import commands
import youtube_dl,asyncio
from library import Counter
from core.classes import Cog_Extension
from discord.ext.tasks import loop

player_list =Counter({})

FFMPEG_OPTIONS = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn'}
YDL_OPTIONS = {'format': 'bestaudio/best', 'noplaylist':'True'}
#https://stackoverflow.com/questions/60842161/discord-py-voiceclient-how-can-i-call-next-audio-file-playsource-after
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
            await ctx.send("我來了~")

    @commands.command(aliases=['dc'])
    async def disconnect(self,ctx):
        await ctx.voice_client.disconnect()
        await ctx.send("拜拜~")

    @commands.command(aliases=['p'])
    async def play(self,ctx,url):
        voice_channel = ctx.author.voice.channel
        if not ctx.voice_client:
            await voice_channel.connect()
        #await ctx.voice_client.stop()
        if ctx.author.voice.channel == ctx.voice_client.channel:
            #if player_list == {}:
                #self.auto_loop.start()
            print(player_list[voice_channel.guild.id])
            if player_list[voice_channel.guild.id]:
                player_list[voice_channel.guild.id].append(url)
            else:
                player_list[voice_channel.guild.id] = []
                player_list[voice_channel.guild.id].append(url)
                print(player_list[voice_channel.guild.id])
                await music.auto_play(self,ctx.guild)
            await ctx.send("已加入一首歌曲")
        else:
            await ctx.send("你必須要在同一個語音頻道才能新增歌曲喔")
    
    async def auto_play(self,guild):
        with youtube_dl.YoutubeDL(YDL_OPTIONS) as ydl:
            info = ydl.extract_info(player_list[guild.id][0], download=False)
            url2 = info['formats'][0]['url']
            source = await discord.FFmpegOpusAudio.from_probe(url2, **FFMPEG_OPTIONS,executable="C:/ffmpeg/bin/ffmpeg.exe")
            vc = guild.voice_client
            vc.play(source,after=music.after(self,guild=guild))

    def after(self,guild):
        try:
            player_list[guild.id].pop(0)
            if len(player_list[guild.id]) != 0:
                fut = asyncio.run_coroutine_threadsafe(music.auto_play(self,guild), self.bot.loop)
                fut.result()
            else:
                del player_list[guild.id]
        except Exception as e:
            print(e)

    @loop(seconds=3)
    async def auto_loop(self):
        for guild_id in player_list:
            guild = self.bot.get_guild(guild_id)
            if guild.voice_client:
                vc = guild.voice_client
                await music.auto_play(guild)
                # if not vc.source and len(player_list[guild_id]) != 0:
                    
                    
                # elif not vc.source and len(player_list[guild_id]) == 0:
                #     del player_list[guild_id]
                #     if player_list == {}:
                #         self.auto_loop.stop()
            else:
                del player_list[guild.id]
                if player_list == {}:
                    self.auto_loop.stop()


    @commands.command(aliases=['pa'])
    async def pause(self,ctx):
        ctx.guild.voice_client.pause()
        await ctx.send("已暫停歌曲")

    @commands.command(aliases=['rs'])
    async def resume(self,ctx):
        ctx.guild.voice_client.resume()
        await ctx.send("繼續撥放")

    @commands.command(aliases=['q'])
    async def queue(self,ctx):
        await ctx.send(f'{player_list[ctx.guild.id]},{len(player_list[ctx.guild.id])}')



def setup(bot):
  bot.add_cog(music(bot))