from pydantic import BaseModel


class PlatformUser(BaseModel):
    """Common base for OAuth `get_me()` results across platforms."""

    id: str


class DiscordAuthModel(PlatformUser):
    """A model that represents the data from Discord Oauth API."""


class DiscordUser(DiscordAuthModel):
    """User Data from Discord Oauth API.

    除了 id、username，其他欄位 Discord 都可能是 null 或不回傳（沒設頭像、顯示名稱的帳號），一律給預設值。
    """

    id: str
    username: str
    avatar: str | None = None
    discriminator: str | None = None
    public_flags: int | None = None
    flags: int | None = None
    banner: str | None = None
    accent_color: int | None = None
    global_name: str | None = None
    banner_color: str | None = None
    bot: bool | None = None
    system: bool | None = None
    mfa_enabled: bool | None = None
    locale: str | None = None
    verified: bool | None = None
    email: str | None = None
    premium_type: int | None = None


class UserConnection(DiscordAuthModel):
    """Connection Data from Discord Oauth API."""

    id: str
    name: str
    type: str
    friend_sync: bool
    metadata_visibility: int
    show_activity: bool
    two_way_link: bool
    verified: bool
    visibility: bool
