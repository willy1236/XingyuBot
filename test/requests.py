import time
import requests
from datetime import datetime
from bs4 import BeautifulSoup


HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.92 Safari/537.36',
}


def get_article_url_list(forum_url):
    """爬取文章列表"""
    r = requests.get(forum_url, headers=HEADERS)
    if r.status_code != requests.codes.ok:
        print('網頁載入失敗')
        return []
    
    # 爬取每一篇文章網址
    article_url_list = []
    soup = BeautifulSoup(r.text, features='lxml')
    item_blocks = soup.select('table.b-list tr.b-list-item')
    for item_block in item_blocks:
        title_block = item_block.select_one('.b-list__main__title')
        article_url = f"https://forum.gamer.com.tw/{title_block.get('href')}"
        article_url_list.append(article_url)

    return article_url_list


def get_article_info(article_url):
    """爬取文章資訊(包含回覆)"""
    r = requests.get(article_url, headers=HEADERS)
    if r.status_code != requests.codes.ok:
        print('網頁載入失敗')
        return {}

    soup = BeautifulSoup(r.text, features='lxml')
    article_title = soup.select_one('h1.c-post__header__title').text

    # 抓取回覆總頁數
    article_total_page = get_article_total_page(soup)

    # 爬取每一頁回覆
    reply_info_list = []
    for page in range(article_total_page):
        crawler_url = f"{article_url}&page={page + 1}"
        reply_list = get_reply_info_list(crawler_url)
        reply_info_list.extend(reply_list)
        time.sleep(1)

    article_info = {
        'title': article_title,
        'url': article_url,
        'reply': reply_info_list
    }
    return article_info


def get_reply_info_list(url):
    """爬取回覆列表"""
    r = requests.get(url, headers=HEADERS)
    if r.status_code != requests.codes.ok:
        print('網頁載入失敗')
        return {}

    reply_info_list = []
    soup = BeautifulSoup(r.text, features='lxml')
    reply_blocks = soup.select('section[id^="post_"]')

    # 對每一則回覆解析資料
    for reply_block in reply_blocks:
        reply_info = {}

        reply_info['floor'] = int(reply_block.select_one('.floor').get('data-floor'))
        reply_info['user_name'] = reply_block.select_one('.username').text
        reply_info['user_id'] = reply_block.select_one('.userid').text

        publish_time = reply_block.select_one('.edittime').get('data-mtime')
        reply_info['publish_time'] = datetime.strptime(publish_time, '%Y-%m-%d %H:%M:%S')

        reply_info['content'] = reply_block.select_one('.c-article__content').text

        gp_count = reply_block.select_one('.postgp span').text
        if gp_count == '-':
            gp_count = 0
        elif gp_count == '爆':
            gp_count = 1000
        reply_info['gp_count'] = int(gp_count)

        bp_count = reply_block.select_one('.postbp span').text
        if bp_count == '-':
            bp_count = 0
        elif bp_count == 'X':
            bp_count = 500
        reply_info['bp_count'] = int(bp_count)

        reply_info_list.append(reply_info)

    return reply_info_list


def get_article_total_page(soup):
    """取得文章總頁數"""
    article_total_page = soup.select_one('.BH-pagebtnA > a:last-of-type').text
    return int(article_total_page)


if __name__ == "__main__":
    # 欲爬取板塊：荒野亂鬥 哈拉板
    url = 'https://forum.gamer.com.tw/B.php?bsn=32407'
    article_url_list = get_article_url_list(url)
    print(f"共爬取 {len(article_url_list)} 篇文章")
    print('=' * 30)

    # for article_url in article_url_list:
    #     article_info = get_article_info(article_url)
    #     print(article_info['title'])
    #     print(article_info['url'])
    #     print(f"共 {len(article_info['reply'])} 則回覆")

    # 測試第一篇
    article_info = get_article_info(article_url_list[0])
    print(article_info['title'])
    print(article_info['url'])
    print(f"共 {len(article_info['reply'])} 則回覆")