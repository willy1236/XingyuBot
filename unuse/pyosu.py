import json, asyncio
from pyosu import OsuApi

with open('setting.json',mode='r',encoding='utf8') as jfile:
    jdata = json.load(jfile)

api = OsuApi('1e99d316fc8fb8e630fe92b4d7cb32701713d2d2')

a = (input ('輸入比賽ID\n'))

async def get_user():

    user = await api.get_user(a)
    print(user)
    #user_id = user.user_id
    match_id = a
    match = await api.get_match(match_id)
    #match = api.get_match(match_id)
    print(match)
    #map = match.__dict__

    print(map)
    print('1')


async def main():
    bests = await api.get_user_bests('Renondedju')
    for best in bests:
        print(best.__dict__)
    print('1')


asyncio.run(get_user())
    