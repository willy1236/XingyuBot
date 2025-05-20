from discord import Option, OptionChoice

from starlib import instance
from starlib.types import McssServerAction

__all__ = [
    "mcss_server_option",
    "mcss_action_option",
    "command_option"
]

mcss_server_actions = [
    OptionChoice(name="開啟", value=McssServerAction.Start.value),
    OptionChoice(name="關閉", value=McssServerAction.Stop.value),
    OptionChoice(name="強制關閉", value=McssServerAction.Kill.value),
    OptionChoice(name="重啟", value=McssServerAction.Restart.value)
]

try:
    mcss_server_options = [OptionChoice(name=i.name, value=i.server_id) for i in instance.mcss_api.get_servers()] # type: ignore
except:
    mcss_server_options = []

mcss_server_option: str = Option(str, description="麥塊伺服器", choices=mcss_server_options)
mcss_action_option: int = Option(int, description="要執行的伺服器操作", choices=mcss_server_actions)
command_option: str = Option(str, description="指令")
