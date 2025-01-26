from pydantic import BaseModel, Field
from datetime import datetime

class McssServer(BaseModel):
    """MCSS 伺服器設定模型"""
    server_id: str = Field(alias="serverId")
    status: int
    name: str
    description: str
    path_to_folder: str = Field(alias="pathToFolder")
    folder_name: str = Field(alias="folderName")
    type: str
    creation_date: datetime = Field(alias="creationDate")
    is_set_to_auto_start: bool = Field(alias="isSetToAutoStart")
    force_save_on_stop: bool = Field(alias="forceSaveOnStop")
    keep_online: int = Field(alias="keepOnline")
    java_allocated_memory: int = Field(alias="javaAllocatedMemory")
    java_startup_line: str = Field(alias="javaStartupLine")