from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class DiscordAuthModel(BaseModel):
    """A model that represents the data from Discord Oauth API."""


class DiscordUser(DiscordAuthModel):
    """User Data from Discord Oauth API."""

    id: str
    username: str
    avatar: str
    discriminator: str
    public_flags: int
    flags: int
    banner: str | None
    accent_color: int
    global_name: str
    avatar_decoration_data: dict
    banner_color: str
    bot: bool | None = None
    system: bool | None = None
    mfa_enabled: bool
    locale: str
    verified: bool | None = None
    email: str | None = None
    premium_type: int


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
