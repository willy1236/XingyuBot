import json

#dict_data = {"1":1,"2":2}
with open('DiscordBot\weeksignin.json',mode='r',encoding='utf8') as jfile:
    dict_data = json.load(jfile)

with open('DiscordBot\weeksignin.json','w+',encoding='utf8') as jfile:
    dict_data['1'] = dict_data['1']+1
    dict_data['3'] = 1
    json.dump(dict_data,jfile)
    
print(dict_data)


#with open('DiscordBot\weeksignin.json',mode='r+',encoding='utf8') as jfile:
    #jwsign = json.load(jfile)
    #dic.update(new_dictionary)
    #json.dump(dic, jfile)

#book_dict = {"price": 500, "bookName": "Python设计", "weight": "250g"}
#book_dict["owner"] = "tyson" 
#print(book_dict)

#input = 1
#sign = jwsign["sign"]

#jwsign['sign'].append(input)
#sign["input"] = 1
#with open('DiscordBot\weeksignin.json',mode='w',encoding='utf8') as jfile:
#    json.dumps(sign,indent=4)

