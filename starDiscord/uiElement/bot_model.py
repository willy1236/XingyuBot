import discord
from pydantic import BaseModel


# class ErrorReportModel(BaseModel):
#     """錯誤回報模型。"""

#     ctx: discord.ApplicationContext
#     error: str


# class ReportModel(BaseModel):
#     """一般回報模型。"""

#     msg: str
#     refer_msg: discord.Message | None = None


# class FeedbackModel(BaseModel):
#     """回饋模型。"""

#     ctx: discord.ApplicationContext
#     msg: discord.Message


# class DMModel(BaseModel):
#     """私訊模型。"""

#     msg: discord.Message


# class mentionModel(BaseModel):
#     """提及模型。"""

#     msg: discord.Message
