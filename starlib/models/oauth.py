from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

class UserConnection(BaseModel):
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