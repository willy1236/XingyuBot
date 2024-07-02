import json

import mysql.connector
from mysql.connector import connection
from starlib.dataExtractor import sclient,Jsondb

DBPATH = "../database"



# 連接到 MySQL 資料庫
try:
    dbdata = sclient.get_rpg_shop_list()
    # 將查詢結果轉換為 JSON 格式
    data = []
    for i in dbdata:
        pass
    # 將資料轉換成 JSON 格式並輸出到檔案
    with open('output.json', 'w') as json_file:
        json.dump(data, json_file, indent=2)

    print('Data has been successfully exported to JSON file (output.json)')

except mysql.connector.Error as e:
    print(f'Error: {e}')

finally:
    # 確保無論如何都關閉連線
    if 'connection' in locals() and connection.is_connected():
        connection.close()
        print('MySQL connection closed')
