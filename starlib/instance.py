"""
此處提供bot在初始化與執行時所需的設定與物件（如api等）
"""

from .dataExtractor import *
from .dataExtractor.others import McssAPI

__all__ = [
    "mcss_api"
]

# 初始化api
mcss_api = McssAPI()
