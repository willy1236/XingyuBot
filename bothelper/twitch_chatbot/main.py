import twitchio
from twitchio.ext import commands,eventsub
from bothelper.database import Jsondb

tokens = Jsondb.get_token('twitch_chatbot')
initial_channels = Jsondb.cache.get('twitch_initial_channels')


class Bot(commands.Bot):
    def __init__(self):
        super().__init__(token=tokens.get('token'), prefix='!!', initial_channels=initial_channels,client_id=tokens.get('id'),nick='bot')

        
    async def event_ready(self):
        print(f'Logged in as | {self.nick}')
        print(f'User id is | {self.user_id}')
        #await bot.connected_channels[0].send('...')

    async def event_reconnect(self):
        print(f'reconnect as | {self.nick}')

    @commands.command()
    async def hi(self, ctx: commands.Context):
        await ctx.send(f'Hello {ctx.author.name}!')

    @commands.command(name='ping')
    async def ping(self, ctx):
        await ctx.send('pong')

    async def event_message(self,message:twitchio.Message):
        if hasattr(message.author, 'name'):
            print(message.content)
            await bot.handle_commands(message)


if __name__ == '__main__':
    bot = Bot()
    bot.run()
# bot.run() is blocking and will stop execution of any below code here until stopped or closed.
