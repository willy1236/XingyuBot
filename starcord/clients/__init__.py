'''
網路交互相關
'''

from .client import *
from .community import *
from .game import *
from .weather import *
from .user import *

__all__ =[
    'NoticeClient',
    'GameClient',
    'StarClient',
    'TwitchAPI',
    'YoutubeAPI',
    'NotionAPI',
    'RiotClient',
    'OsuInterface',
    'ApexInterface',
    'SteamInterface',
    'DBDInterface',
    'CWBClient',
    'UserClient',
]