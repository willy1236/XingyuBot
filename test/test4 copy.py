import json
rsdata = json.load(open('C:/Google drive/GitHub/DiscordBot/database/role_save.json',mode='r',encoding='utf8'))
for user in rsdata:
    for role in rsdata[user]:
        print(rsdata[user][role])
        rsdata[user][role].pop(1)
with open('C:/Google drive/GitHub/DiscordBot/database/role_save.json',mode='w',encoding='utf8') as jfile:
    json.dump(rsdata,jfile,indent=4)