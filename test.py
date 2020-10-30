import json

with open('setting.json',mode='r',encoding='utf8') as jfile:
    jdata = json.load(jfile)

b = jdata['crass_chat']
for a in b:
    print(a)

