import json, requests
from bs4 import BeautifulSoup

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.92 Safari/537.36',
}
#r = requests.get('https://api.github.com/events')
#print(r.text)

def get_article_url_list(url):
    response = requests.get(url)
    #載入失敗測試
    #if r.status_code != requests.codes.ok:
    #    print('網頁載入失敗')
    #    return

    #文章列表
    article_url_list = []
    soup = BeautifulSoup(response.text, features='lxml')
    item_blocks = soup.select('table.b-list tr.b-list-item')
    for item_block in item_blocks:
        title_block = item_block.select_one('.b-list__main__title')
        article_url = f"https://forum.gamer.com.tw/{title_block.get('href')}"
        article_url_list.append(article_url)

    return article_url_list


if __name__ == "__main__":
    #url=input()
    url = 'https://forum.gamer.com.tw/B.php?bsn=18673'
    output = get_article_url_list(url)
    print(output)