from discord import Option, OptionChoice

from starlib.database import McssServerAction

__all__ = ["mcss_action_option", "command_option"]

mcss_server_actions = [
    OptionChoice(name="開啟", value=McssServerAction.Start.value),
    OptionChoice(name="關閉", value=McssServerAction.Stop.value),
    OptionChoice(name="強制關閉", value=McssServerAction.Kill.value),
    OptionChoice(name="重啟", value=McssServerAction.Restart.value),
]

mcss_action_option: int = Option(int, description="要執行的伺服器操作", choices=mcss_server_actions)
command_option: str = Option(str, description="指令")
