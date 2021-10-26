import json


#(*args) 傳入多個參數
#(**kwargs) 傳入多個參數並轉變為dict
#'value' in dict 偵測dict內是否有value
#len(list) 查詢list內的個數

def is_number(n):
    try:  
        float(n)
        return True
    except ValueError:
        pass
    try:
        import unicodedata
        unicodedata.numeric(n)
        return True
    except (TypeError, ValueError):
        pass
    return False

def check_point(menber):
    with open('point.json',mode='r',encoding='utf8') as jfile:
        jpt2 = json.load(jfile)
        jpt = Counter(jpt2)
    #json內資料格為str形式
    pt = jpt[str(menber)]
    return pt

#如果讀不到資料補0避免keyerror
class Counter(dict):
    def __missing__(self,key): 
        return 0
