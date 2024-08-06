import time
from urllib.parse import urlencode

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

params = {
    "school": 397,
    "searchtype": 3,
    "other": "newPost",
    "order": "posttime",
    "orderType": "desc",
	"rentprice": ",13000"
}
# headers = {
#     "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
# }
# r = requests.get("https://rent.591.com.tw/", params=params, headers=headers)

# if r.status_code == 200:
#     soup = BeautifulSoup(r.text, 'html.parser')
#     tags = soup.find_all('div', class_='switch-list-content tablescraper-selected-table')
#     for tag in tags:
#         print(tag.text)


# 設置 ChromeDriver 路徑
chrome_driver_path = 'D:\chromedriver-win64\chromedriver.exe'  # 替換為你的 ChromeDriver 路徑

# 設置 Chrome 選項
chrome_options = Options()
# chrome_options.add_argument('--headless')  # 啟用無頭模式（無界面）

# 初始化 WebDriver
service = Service(chrome_driver_path)
driver = webdriver.Chrome(service=service, options=chrome_options)

try:
	# 打開指定的 URL
	url = "https://rent.591.com.tw/"
	full_url = f"{url}?{urlencode(params)}"
	driver.get(full_url)
	time.sleep(5)

	# 等待 class 為 'switch-list-content tablescraper-selected-table' 的 div 出現
	WebDriverWait(driver, 30).until(
		EC.presence_of_element_located((By.CLASS_NAME, 'switch-list-content'))
	)

	# 找到所有 class 為 'switch-list-content tablescraper-selected-table' 的 div
	div_tags = driver.find_elements(By.CLASS_NAME, 'switch-list-content')

	section_tags = div_tags[0].find_elements(By.TAG_NAME, 'section')
	for section in section_tags:
		print(section.text)
            
		school_tag = section.find_elements(By.CLASS_NAME, 'item-tip school')
		if school_tag:
			print(school_tag[0].text)

		a_tags = section.find_elements(By.TAG_NAME, 'a')
		for a in a_tags:
			href = a.get_attribute('href')
			print(href)
		print("="*50)

finally:
    # 關閉瀏覽器
    driver.quit()
