import json

with open('gamer_data.json',mode='r',encoding='utf8') as jfile:
    gdata = json.load(jfile)

id = 419131103836635136
print(gdata)
if not 'steam' in gdata:
    with open('gamer_data.json',mode='r+',encoding='utf8') as jfile:
        gdata[f'{id}']['steam'] = 'None'
        json.dump(gdata,jfile,indent=4)
print(gdata)
    