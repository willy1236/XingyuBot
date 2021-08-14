import json, asyncio, datetime


now_time_hour = datetime.datetime.now().strftime('%H%M%S')
now_time_day = datetime.datetime.now().strftime('%Y%m%d')
print(now_time_day)
print(now_time_hour)