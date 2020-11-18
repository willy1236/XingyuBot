import json

#with open('setting.json',mode='r',encoding='utf8') as jfile:
#    jdata = json.load(jfile)

#b = jdata['crass_chat']
#for a in b:
#    print(a)
#import asyncio
#import pyosu
#from pyosu import OsuApi

#print(pyosu.__version__)

#async def test():
    
    #api = OsuApi('1e99d316fc8fb8e630fe92b4d7cb32701713d2d2')

    #bests = await api.get_user_bests('willy1236')
    #for best in bests:
        #print(best.__dict__)

#if __name__ == '__test__':
#    asyncio.run(test())

with open('setting.json',mode='r',encoding='utf8') as jfile:
    jdata = json.load(jfile)

@commands.command()
async def a(self, ctx, msg):
    await ctx.send(jdata[f'{ctx.author.id}_test'])
    jdata[f'{ctx.author.id}_test'] = msg
    with open('setting.json',mode='w',encoding='utf8') as jfile:
        json.dump(jdata,jfile,indent=4)
    await ctx.send(jdata[f'{ctx.author.id}_test'])
    
    result = 0
    for a in jdata['test']:
        if a == f'{ctx.author.id}_test':
            result = result +1

    if result == 0:
        jdata['test'].append(f'{ctx.author.id}_test')
        with open('setting.json',mode='w',encoding='utf8') as jfile:
            json.dump(jdata,jfile,indent=4)
    
    else:
        await ctx.send('no')