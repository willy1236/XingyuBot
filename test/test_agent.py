from pydantic_ai.models.gemini import GeminiModel
from pydantic_ai import Agent
from pydantic_ai.providers.google_gla import GoogleGLAProvider
import os

from starlib import Jsondb, sqldb
from starlib.types import APIType

import psycopg2
SQLsettings:dict = Jsondb.config.get('SQLsettings')
connect = psycopg2.connect(
    host=SQLsettings['host'],
    database=SQLsettings['database'],
    user=SQLsettings['user'],
    password=SQLsettings['password'],
    port=SQLsettings['port']
)

class Tools:
    @staticmethod
    def read_file(file_path: str) -> str:
        print(f"Reading file: {file_path}")
        with open(file_path, 'r', encoding="utf-8") as file:
            return file.read()

    @staticmethod
    def list_files(directory: str) -> list:
        print(f"Listing files in {directory}")
        return os.listdir(directory)

    @staticmethod
    def rename_file(old_name: str, new_name: str) -> None:
        print(f"Renaming {old_name} to {new_name}")
        os.rename(old_name, new_name)

    @staticmethod
    def get_sql(sql: str):
        """執行postgresql的sql語法並取得結果"""
        print(f"Executing SQL: {sql}")
        with connect.cursor() as cursor:
            cursor.execute(sql)
            return cursor.fetchall()
        
    @staticmethod
    def get_sql_colums(table_name: str, table_schema: str):
        """取得postgresql的資料表有哪些欄位"""
        print(f"Getting SQL table structure for: {table_schema}.{table_name}")
        with connect.cursor() as cursor:
            cursor.execute(f"SELECT column_name, data_type, is_nullable, column_default FROM information_schema.columns WHERE table_name = '{table_name}' AND table_schema = '{table_schema}';")
            return cursor.fetchall()

provider = GoogleGLAProvider(api_key=sqldb.get_bot_token(APIType.Google, 5).access_token)
model = GeminiModel(model_name="gemini-2.0-flash", provider=provider)
agent = Agent(model,
            instrument=True,
            tools=[Tools.read_file, Tools.list_files, Tools.rename_file, Tools.get_sql, Tools.get_sql_colums])

@agent.system_prompt
async def system_prompt() -> str:
    tables = Tools.get_sql("SELECT schemaname, tablename FROM pg_tables WHERE schemaname NOT IN ('pg_catalog', 'information_schema');")
    return f"""
    你是個富有經驗的系統管理員，請協助我完成以下任務
    資料庫中有以下資料表
    {tables}
    在查詢資料前可以先查詢資料的欄位確保正確的名稱
    """


if __name__ == "__main__":
    history = []
    while True:
        user_input = input("Input: ")
        resp = agent.run_sync(user_input,
                                message_history=history)
        history = list(resp.all_messages())
        print(resp.output)