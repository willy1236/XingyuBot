from starlib.database import APIType, McssServerAction, sqldb

from ..base import APICaller
from .models import McssServer


class McssAPI(APICaller):
    PORT = 25560
    base_url = f"http://localhost:{PORT}/api/v2"

    def __init__(self):
        super().__init__(headers={"apikey": sqldb.get_access_token(APIType.MCSS).access_token})

    def get_servers(self):
        r = self.get("servers")
        return [McssServer(**i) for i in r.json()] if r is not None else []

    def get_server_detail(self, server_id: str):
        r = self.get(f"servers/{server_id}")
        return McssServer(**r.json()) if r is not None else None

    def excute_action(self, server_id: str, action: McssServerAction):
        data = {"action": McssServerAction(action).value}
        self.post(f"servers/{server_id}/execute/action", data=data)
        return True

    def excute_command(self, server_id: str, command: str):
        data = {"command": command}
        r = self.post(f"servers/{server_id}/execute/command", data=data)
        return r.text


class VirustotalAPI(APICaller):
    base_url = "https://www.virustotal.com/api/v3"

    def __init__(self):
        super().__init__(headers={"x-apikey": sqldb.get_access_token(APIType.Virustotal).access_token})

    def get_url_report(self, url: str):
        """取得網址的 Virustotal 報告"""
        r = self.post("urls", data={"url": url})
        return r.json()
