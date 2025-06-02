from pydantic_ai.models.gemini import GeminiModel
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStdio
from pydantic_ai.providers.google_gla import GoogleGLAProvider
import os
import inspect

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

mcp_servers = [
    MCPServerStdio("uvx", ["mcp-server-fetch"])
]

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
    def write_file(file_path: str, content: str) -> None:
        print(f"Writing to file: {file_path}")
        with open(file_path, 'w', encoding="utf-8") as file:
            file.write(content)

    # @staticmethod
    # def rename_file(old_name: str, new_name: str) -> None:
    #     print(f"Renaming {old_name} to {new_name}")
    #     os.rename(old_name, new_name)

    # @staticmethod
    # def get_sql(sql: str):
    #     """執行postgresql的sql語法並取得結果"""
    #     print(f"Executing SQL: {sql}")
    #     with connect.cursor() as cursor:
    #         cursor.execute(sql)
    #         return cursor.fetchall()
        
    # @staticmethod
    # def get_sql_colums(table_name: str, table_schema: str):
    #     """取得postgresql的資料表有哪些欄位"""
    #     print(f"Getting SQL table structure for: {table_schema}.{table_name}")
    #     with connect.cursor() as cursor:
    #         cursor.execute(f"SELECT column_name, data_type, is_nullable, column_default FROM information_schema.columns WHERE table_name = '{table_name}' AND table_schema = '{table_schema}';")
    #         return cursor.fetchall()

provider = GoogleGLAProvider(api_key=sqldb.get_bot_token(APIType.Google, 5).access_token)
model = GeminiModel(model_name="gemini-2.0-flash", provider=provider)
agent = Agent(model,
            instrument=True,
            tools=[fn for _, fn in inspect.getmembers(Tools, predicate=inspect.isfunction)],
            mcp_servers=mcp_servers)

@agent.system_prompt
async def system_prompt() -> str:
    # tables = Tools.get_sql("SELECT schemaname, tablename FROM pg_tables WHERE schemaname NOT IN ('pg_catalog', 'information_schema');")
    return f"""
    你是個富有經驗的系統管理員，請協助我完成以下任務
    """

async def main():
    history = []
    while True:
        user_input = input("Input: ")
        async with agent.run_mcp_servers():
            resp =  await agent.run(user_input, message_history=history)
        history = list(resp.all_messages())
        print(resp.output)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())