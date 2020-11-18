import json

with open('setting.json',mode='r',encoding='utf8') as jfile:
    jdata = json.load(jfile)

print(jdata['data']["a"])

