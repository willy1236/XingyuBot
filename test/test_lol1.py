import discord
from discord.ext import commands
import json, random, datetime, asyncio, re, requests
import os
from bs4 import BeautifulSoup

url = 'https://lol.moa.tw/summoner/show/英雄威力'
player = "英雄威力"
response = requests.get(url)
soup = BeautifulSoup(response.text, "html.parser")
#print(soup.prettify()) #完整原始碼
#print(soup.title.string) #網頁標題


results = soup.find_all("h1",class_="row")
#print(results)
for result in results:
    if result.div.string == None:
    #print(result.div.string)
    #print('---------')
        result2 = str(result.div)[166:]
        print(result2)
        
        lvl = ''.join([x for x in result2 if x.isdigit()])
        print(lvl)


#<div class="col-xs-12">
#<img alt="" class="profiles" src="https://ddragon.leagueoflegends.com/cdn/11.15.1/img/profileicon/1229.png" style="width:64px;height:64px;"/> Lv91 英雄威力 </div>


#<div class="col-xs-12 xh-highlight">
#<img src="https://ddragon.leagueoflegends.com/cdn/11.15.1/img/profileicon/1229.png" class="profiles" style="width:64px;height:64px;" alt=""> Lv84 英雄威力 </div>


#<div class="col-xs-12">
#    <img src="https://ddragon.leagueoflegends.com/cdn/11.15.1/img/profileicon/1229.png" class="profiles" style="width:64px;height:64px;" alt="" /> Lv91 英雄威力 
#</div>



#html = requests.post(url,data=myobj)

#print(html.text)
