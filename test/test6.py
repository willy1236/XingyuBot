import urllib.request as req
url = "https://lol.moa.tw/summoner/show/英雄威力"
with req.urlopen(url) as response:
    data=response.read().decode("utf-8")
print(data)