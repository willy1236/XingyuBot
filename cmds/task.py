import discord,json, asyncio, datetime
from discord.ext import commands
from core.classes import Cog_Extension
from BotLib.basic import Database
from cmds.weather import EarthquakeReport
from library import BRS,find

class task(Cog_Extension):
    def __init__(self,*args,**kwargs):
        jevent = Database().jevent

        super().__init__(*args,**kwargs)
        
        async def time_task():
            await self.bot.wait_until_ready()
            task_report_channel = self.bot.get_channel(self.jdata['task_report'])
            while not self.bot.is_closed():
                now_time_hour = datetime.datetime.now().strftime('%H%M%S')
                now_time_day = datetime.datetime.now().strftime('%Y%m%d')

                if now_time_hour == '040000':
                    reset = []
                    Database().write('jdsign',reset)

                    await task_report_channel.send('簽到已重置')    

                if now_time_hour[3:] == '000' or now_time_hour[3:] == '500':
                    jdata = Database().jdata
                    timefrom = jdata['timefrom']
                    data = EarthquakeReport.get_report_auto(timefrom)
                    if data:
                        embed = BRS.simple(f'編號第{data.earthquakeNo}號地震報告')
                        embed.add_field(name='發生時間',value=data.originTime)
                        embed.add_field(name='震央',value=data.location)
                        embed.add_field(name='震源深度',value=f'{data.depth} km')
                        embed.add_field(name='芮氏規模',value=f'{data.magnitude}')
                        embed.set_image(url=data.reportImageURI)
                        jdata['timefrom'] = data.originTime
                        Database().write('jdata',jdata)
                        
                        ch_list = Database().cdata['earthquake']
                        for i in ch_list:
                            channel = self.bot.get_channel(ch_list[i])
                            if channel:
                                await channel.send('地震報告',embed=embed)
                
                await asyncio.sleep(1)
        self.bg_task = self.bot.loop.create_task(time_task())

def setup(bot):
    bot.add_cog(task(bot))