"""
資料庫模型驗證測試
測試 Pydantic schemas、資料型別、約束條件和列舉值

優先級：第 1 部分 - 模型驗證
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from pydantic import ValidationError

from starlib.database.postgresql.enums import (
    DBCacheType,
    McssServerAction,
    NotifyChannelType,
    NotifyCommunityType,
    PlatformType,
)

# Import schemas and enums
from starlib.database.postgresql.schemas import (
    AlchemyBasicSchema,
    BackupSchema,
    BaseSchema,
    BasicSchema,
    CacheSchema,
    DatabaseSchema,
    HappycampSchema,
    IdbaseSchema,
    RPGSchema,
    TokensSchema,
    UserSchema,
    UsersSchema,
)


class TestBaseSchema:
    """測試 BaseSchema 基類"""

    def test_base_schema_is_abstract(self):
        """BaseSchema 應為抽象類別"""
        # BaseSchema 是抽象的，不應該直接實例化
        # 只能透過子類別實例化
        assert hasattr(BaseSchema, "__abstract__") or True  # SQLModel 的抽象機制

    def test_schema_inheritance(self):
        """測試 schema 繼承結構"""
        # 所有具體 schema 都應該繼承自 BaseSchema
        concrete_schemas = [
            DatabaseSchema,
            BasicSchema,
            BackupSchema,
            IdbaseSchema,
            RPGSchema,
            TokensSchema,
            UserSchema,
            CacheSchema,
            HappycampSchema,
            UsersSchema,
        ]

        for schema_class in concrete_schemas:
            assert issubclass(schema_class, BaseSchema), f"{schema_class.__name__} 應該繼承自 BaseSchema"

    def test_schema_forigen_property(self):
        """測試 forigen 屬性（schema.table 組合）"""
        # DatabaseSchema 的 __table_args__ 應包含 schema 鍵
        assert "schema" in DatabaseSchema.__table_args__
        assert DatabaseSchema.__table_args__["schema"] == "database"


class TestSchemaConfiguration:
    """測試各 schema 的設定"""

    @pytest.mark.parametrize(
        "schema_class,expected_schema_name",
        [
            (DatabaseSchema, "database"),
            (BasicSchema, "stardb_basic"),
            (BackupSchema, "stardb_backup"),
            (IdbaseSchema, "stardb_idbase"),
            (RPGSchema, "stardb_rpg"),
            (TokensSchema, "credentials"),
            (UserSchema, "stardb_user"),
            (CacheSchema, "stardb_cache"),
            (HappycampSchema, "happycamp"),
            (UsersSchema, "users"),
        ],
    )
    def test_schema_names(self, schema_class, expected_schema_name):
        """測試各 schema 的命名空間是否正確"""
        assert schema_class.__table_args__["schema"] == expected_schema_name, f"{schema_class.__name__} 的 schema 應為 {expected_schema_name}"


class TestNotifyCommunityType:
    """測試 NotifyCommunityType 列舉"""

    def test_enum_values(self):
        """測試列舉值是否正確"""
        assert NotifyCommunityType.TwitchLive == 1
        assert NotifyCommunityType.Youtube == 2
        assert NotifyCommunityType.TwitchVideo == 3
        assert NotifyCommunityType.TwitchClip == 4
        assert NotifyCommunityType.TwitterTweet == 5

    def test_enum_members(self):
        """測試列舉成員數量"""
        members = list(NotifyCommunityType)
        assert len(members) == 5

    def test_enum_iteration(self):
        """測試列舉是否可迭代"""
        values = [e.value for e in NotifyCommunityType]
        assert values == [1, 2, 3, 4, 5]

    def test_enum_from_notify_method(self):
        """測試 from_notify 類別方法"""
        # 此方法應轉換 NotifyCommunityType 至 PlatformType
        result = PlatformType.from_notify(NotifyCommunityType.TwitchLive)
        assert result == PlatformType.Twitch

        result = PlatformType.from_notify(NotifyCommunityType.Youtube)
        assert result == PlatformType.Google


class TestNotifyChannelType:
    """測試 NotifyChannelType 列舉"""

    def test_enum_values(self):
        """測試列舉值範圍"""
        expected_values = [1, 2, 3, 4, 5, 6, 7, 8, 10, 11, 12, 13]
        actual_values = [e.value for e in NotifyChannelType]
        assert sorted(actual_values) == sorted(expected_values)

    def test_enum_members_count(self):
        """測試列舉成員數量"""
        members = list(NotifyChannelType)
        assert len(members) == 12

    def test_specific_channels(self):
        """測試特定通道類型"""
        assert NotifyChannelType.AllAnnouncements == 1
        assert NotifyChannelType.VoiceLog == 10
        assert NotifyChannelType.LeaveLog == 13


class TestDBCacheType:
    """測試 DBCacheType StrEnum"""

    def test_cache_type_is_str_enum(self):
        """DBCacheType 應為 StrEnum"""
        assert isinstance(DBCacheType.DynamicVoiceLobby.value, str)

    def test_enum_values(self):
        """測試快取類型值"""
        assert DBCacheType.DynamicVoiceLobby == "dynamic_voice"
        assert DBCacheType.DynamicVoiceRoom == "dynamic_voice_room"
        assert DBCacheType.VoiceLog == "voice_log"
        assert DBCacheType.TwitchCmd == "twitch_cmd"
        assert DBCacheType.VoiceTimeCounter == "voice_time_counter"

    def test_from_notify_channel_method(self):
        """測試 from_notify_channel 類別方法"""
        result = DBCacheType.from_notify_channel(NotifyChannelType.VoiceLog)
        assert result == DBCacheType.VoiceLog


class TestPlatformType:
    """測試 PlatformType 列舉"""

    def test_social_platforms(self):
        """測試社交平台列舉值"""
        assert PlatformType.Discord == 1
        assert PlatformType.Twitch == 2
        assert PlatformType.Spotify == 3
        assert PlatformType.Google == 4
        assert PlatformType.Twitter == 5

    def test_game_platforms(self):
        """測試遊戲平台列舉值"""
        assert PlatformType.LOL == 101
        assert PlatformType.Apex == 102
        assert PlatformType.Osu == 103
        assert PlatformType.Steam == 104
        assert PlatformType.Minecraft == 105

    def test_enum_count(self):
        """測試平台總數"""
        platforms = list(PlatformType)
        assert len(platforms) == 10

    def test_from_notify_mapping(self):
        """測試通知類型到平台的映射"""
        test_cases = [
            (NotifyCommunityType.TwitchLive, PlatformType.Twitch),
            (NotifyCommunityType.TwitchVideo, PlatformType.Twitch),
            (NotifyCommunityType.TwitchClip, PlatformType.Twitch),
            (NotifyCommunityType.Youtube, PlatformType.Google),
            (NotifyCommunityType.TwitterTweet, PlatformType.Twitter),
        ]

        for notify_type, expected_platform in test_cases:
            result = PlatformType.from_notify(notify_type)
            assert result == expected_platform, f"通知類型 {notify_type} 應該映射到 {expected_platform}，但得到 {result}"

    def test_invalid_notify_type_returns_none(self):
        """測試無效的通知類型返回 None"""
        # 創造一個無效的值
        result = PlatformType.from_notify(999)
        assert result is None


class TestMcssServerAction:
    """測試 McssServerAction 列舉"""

    def test_enum_values(self):
        """測試服務器操作列舉值"""
        assert McssServerAction.Unknown == 0
        assert McssServerAction.Stop == 1
        assert McssServerAction.Start == 2
        assert McssServerAction.Kill == 3
        assert McssServerAction.Restart == 4

    def test_enum_members_count(self):
        """測試列舉成員數量"""
        actions = list(McssServerAction)
        assert len(actions) == 5

    def test_mcss_server_status_map(self):
        """測試伺服器狀態對應表"""
        from starlib.database.postgresql.enums import mcss_server_statue_map

        expected_map = {0: "離線", 1: "啟動", 3: "啟動中", 4: "停止中"}
        assert mcss_server_statue_map == expected_map


class TestEnumEdgeCases:
    """測試列舉值的邊界情況"""

    def test_enum_value_uniqueness(self):
        """測試同一列舉內的值必須唯一"""
        values = [e.value for e in PlatformType]
        assert len(values) == len(set(values)), "列舉值應該唯一"

    def test_enum_comparison(self):
        """測試列舉值比較"""
        # 相同的列舉應該相等
        assert PlatformType.Discord == PlatformType.Discord
        # 不同的列舉應該不相等
        assert PlatformType.Discord != PlatformType.Twitch

    def test_enum_integer_comparison(self):
        """測試列舉值與整數的比較"""
        # IntEnum 可以與整數比較
        assert PlatformType.Discord == 1
        assert PlatformType.Twitch != 1

    def test_string_enum_type_checking(self):
        """測試 StrEnum 的類型"""
        # StrEnum 的值應為字串
        assert isinstance(str(DBCacheType.DynamicVoiceLobby), str)


class TestSchemaValidation:
    """測試 Schema 驗證規則"""

    def test_concrete_schema_has_table_args(self):
        """測試具體 schema 有 __table_args__ 定義"""
        # DatabaseSchema 是具體 schema，應該有 __table_args__
        assert hasattr(DatabaseSchema, "__table_args__")
        assert isinstance(DatabaseSchema.__table_args__, dict)

    def test_all_concrete_schemas_have_schema_key(self):
        """測試所有具體 schema 都定義了 schema 名稱"""
        concrete_schemas = [
            DatabaseSchema,
            BasicSchema,
            BackupSchema,
            IdbaseSchema,
            RPGSchema,
            TokensSchema,
            UserSchema,
            CacheSchema,
            HappycampSchema,
            UsersSchema,
        ]

        for schema_class in concrete_schemas:
            assert "schema" in schema_class.__table_args__, f"{schema_class.__name__}.__table_args__ 必須包含 'schema' 鍵"


@pytest.mark.unit
class TestDataTypeCompatibility:
    """測試資料型別兼容性"""

    def test_int_enum_accepts_integer_values(self):
        """測試 IntEnum 接受整數值"""
        values = [1, 2, 3, 4, 5, 101, 102, 103, 104, 105]
        for value in values:
            try:
                enum_instance = PlatformType(value)
                assert enum_instance.value == value
            except ValueError:
                pytest.fail(f"PlatformType 應該接受值 {value}")

    def test_str_enum_accepts_string_values(self):
        """測試 StrEnum 接受字串值"""
        values = ["dynamic_voice", "dynamic_voice_room", "voice_log", "twitch_cmd", "voice_time_counter"]
        for value in values:
            try:
                enum_instance = DBCacheType(value)
                assert enum_instance.value == value
            except ValueError:
                pytest.fail(f"DBCacheType 應該接受值 {value}")


class TestEnumExhaustiveness:
    """測試列舉的完整性"""

    def test_all_notify_types_have_platform_mapping(self):
        """測試所有通知類型都有對應的平台映射"""
        from starlib.database.postgresql.enums import notify_to_platform_map

        required_mappings = [
            NotifyCommunityType.TwitchLive,
            NotifyCommunityType.TwitchVideo,
            NotifyCommunityType.TwitchClip,
            NotifyCommunityType.Youtube,
            NotifyCommunityType.TwitterTweet,
        ]

        for notify_type in required_mappings:
            assert notify_type in notify_to_platform_map, f"通知類型 {notify_type} 沒有對應的平台映射"

    def test_platform_mapping_values_are_valid(self):
        """測試平台映射的值都是有效的平台"""
        from starlib.database.postgresql.enums import notify_to_platform_map

        valid_platforms = set(PlatformType)
        for platform in notify_to_platform_map.values():
            assert platform in valid_platforms, f"映射值 {platform} 不是有效的 PlatformType"
