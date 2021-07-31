import asyncio
from pyosu import OsuApi

async def main():
    
    api = OsuApi('1e99d316fc8fb8e630fe92b4d7cb32701713d2d2')

    match_id = int('88331529')
    match = await api.get_match(match_id)

    return match

    #bests = await api.get_user_bests('willy1236')
    #for best in bests:
    #    print(best.__dict__)

#if __name__ == '__main__':
asyncio.run(main())
#https://github.com/Renondedju/Osu.py