# pyright: reportArgumentType=false, reportCallIssue=false
from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.google import GoogleModel, GoogleModelSettings
from pydantic_ai.providers.google import GoogleProvider

from starlib import Jsondb, agent_log, sqldb
from starlib.types import APIType


safety_settings = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_ONLY_HIGH"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_ONLY_HIGH"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_ONLY_HIGH"},
]

provider = GoogleProvider(api_key=sqldb.get_bot_token(APIType.Google, 5).access_token)
model_settings = GoogleModelSettings(gemini_safety_settings=safety_settings)
model = GoogleModel(model_name="gemini-2.5-flash", provider=provider)
line_agent = Agent(model)


@line_agent.system_prompt
async def system_prompt(ctx: RunContext) -> str:
    text = f"""
    任務：
    - 現在請你做為專業的詐騙防治專員，協助使用者分析與評估他們提供的網址是否具有詐騙風險，並給予簡易的說明與建議報告。
    - 你會獲得一份文字資料報告，內容包含該網址的重定向鏈、網域資訊、WHOIS 註冊資料與 SSL 證書資訊等，請根據這些資訊來評估網址的安全性。並告訴使用者該網址來自於哪個來源與來源可不可信。
    - 請注意，你的回答應該簡潔明瞭，重點突出，避免冗長的解釋。請考慮使用者的角度，提供簡潔實用且易於理解的建議。並且不要提供長篇大論的背景知識說明。
    
    輸出格式：
    - 你的回答應該分成以下幾個部分：
      1. 該網址的安全評估結果（安全、可疑、危險等，在標題列出）
      2. 來源可信度
      3. 主要的風險因素（如可疑的重定向鏈、WHOIS 註冊地點異常、SSL 證書問題等）
      4. 簡短的建議（如避免訪問該網址、使用安全工具檢查、或者指出最相近的詐騙手法等）
    """  # noqa: W293

    return text


async def main():
    history = []
    while True:
        user_input = input("Input: ")
        # async with agent.run_mcp_servers():
        resp = await line_agent.run(user_input, message_history=history)
        history = list(resp.all_messages())
        print(resp.output)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
