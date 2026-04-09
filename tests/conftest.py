"""
Pytest 全域測試配置
包含全域 Fixture、環境變數設定、模擬工具初始化
"""

import os
import sys
from collections.abc import Generator
from datetime import datetime, timezone
from pathlib import Path

import pytest
from dotenv import load_dotenv

# 將專案根目錄加入 Python Path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 載入環境變數（測試用）
load_dotenv(dotenv_path=PROJECT_ROOT / ".env.test", override=True)

# 若沒有 .env.test，使用預設值
if not os.getenv("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "postgresql://test:test@localhost:5432/xingyu_test"


@pytest.fixture(scope="session")
def test_timezone():
    """提供測試使用的時區"""
    return timezone.utc


@pytest.fixture(scope="session")
def test_data_dir():
    """提供測試資料目錄"""
    test_data = PROJECT_ROOT / "tests" / "fixtures"
    test_data.mkdir(parents=True, exist_ok=True)
    return test_data


@pytest.fixture
def sample_datetime():
    """提供範例 datetime"""
    return datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def sample_timestamps():
    """提供一組時戳資料"""
    return {
        "now": datetime.now(timezone.utc),
        "past": datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        "future": datetime(2099, 12, 31, 23, 59, 59, tzinfo=timezone.utc),
    }


@pytest.fixture
def sample_user_ids():
    """提供範例用戶 ID"""
    return {
        "discord_id": 123456789,
        "cloud_user_id": 1,
        "twitch_id": "test_user_123",
        "osu_id": 12345,
        "riot_id": "TestName#12345",
    }


@pytest.fixture
def sample_guild_ids():
    """提供範例伺服器 ID"""
    return {
        "guild_id": 987654321,
        "channel_id": 111222333,
        "role_id": 444555666,
        "message_id": 777888999,
    }


@pytest.fixture
def sample_enum_values():
    """提供範例列舉值"""
    return {
        "platform_types": [1, 2, 3, 4, 5, 101, 102, 103, 104, 105],
        "notify_community_types": [1, 2, 3, 4, 5],
        "notify_channel_types": [1, 2, 3, 4, 5, 6, 7, 10, 11, 12, 13],
        "privilege_levels": [0, 1, 2],  # User, Mod, Admin
    }


@pytest.fixture
def sample_strings():
    """提供範例字串"""
    return {
        "short_name": "user",
        "long_text": "This is a test description that is longer than usual.",
        "special_chars": "test@example.com",
        "unicode_text": "測試文字with中文",
        "json_text": '{"key": "value"}',
    }


@pytest.fixture
def sample_numeric_values():
    """提供範例數值"""
    return {
        "positive_int": 42,
        "zero": 0,
        "negative_int": -10,
        "large_int": 10**18,
        "float_value": 3.14159,
    }


@pytest.fixture(autouse=True)
def reset_env():
    """每個測試前後重置環境變數"""
    original_env = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(original_env)


# ========== 標記定義 ==========
def pytest_configure(config):
    """註冊自定義 pytest 標記"""
    config.addinivalue_line("markers", "unit: 單元測試")
    config.addinivalue_line("markers", "integration: 整合測試")
    config.addinivalue_line("markers", "e2e: 端到端測試")
    config.addinivalue_line("markers", "slow: 執行時間較長的測試")
    config.addinivalue_line("markers", "db: 涉及資料庫的測試")
    config.addinivalue_line("markers", "external_api: 涉及外部 API 呼叫的測試")


# ========== 報告鉤子 ==========
def pytest_collection_modifyitems(config, items):
    """自動為測試添加標記"""
    for item in items:
        # 根據測試路徑添加標記
        if "unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        elif "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        elif "e2e" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)
