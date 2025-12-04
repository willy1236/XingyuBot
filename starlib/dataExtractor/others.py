import requests

from ..database import sqldb
from ..models.others import McssServer
from ..types import APIType, McssServerAction
from ..utils import log


class McssAPI:
    PORT = 25560
    URL = f"http://localhost:{PORT}/api/v2"

    def __init__(self):
        self.headers = {
            "apikey": sqldb.get_access_token(APIType.MCSS).access_token,
        }

    def get_servers(self):
        try:
            r = requests.get(f"{self.URL}/servers", headers=self.headers)
            r.raise_for_status()
            return [McssServer(**i) for i in r.json()]
        except Exception as e:
            log.error("McssAPI Failed to get servers: %s", e)
            raise

    def get_server_detail(self, server_id: str):
        r = requests.get(f"{self.URL}/servers/{server_id}", headers=self.headers)
        r.raise_for_status()
        if r.ok:
            return McssServer(**r.json())
        else:
            log.error("McssAPI: [%s] %s", r.status_code, r.text)

    def excute_action(self, server_id: str, action: McssServerAction):
        data = {"action": McssServerAction(action).value}
        r = requests.post(f"{self.URL}/servers/{server_id}/execute/action", json=data, headers=self.headers)
        r.raise_for_status()
        if r.ok:
            return True
        else:
            log.error("McssAPI: [%s] %s", r.status_code, r.text)
            return False

    def excute_command(self, server_id: str, command: str):
        data = {"command": command}
        r = requests.post(f"{self.URL}/servers/{server_id}/execute/command", json=data, headers=self.headers)
        r.raise_for_status()
        if r.ok:
            return r.text
        else:
            log.error("McssAPI: [%s] %s", r.status_code, r.text)

class VirustotalAPI:
    BASE_URL = "https://www.virustotal.com/api/v3"

    def __init__(self):
        self.headers = {
            "x-apikey": sqldb.get_access_token(APIType.Virustotal).access_token,
        }

    def get_url_report(self, url: str):
        """取得網址的 Virustotal 報告"""
        r = requests.post(f"{self.BASE_URL}/urls", headers=self.headers, json={"url": url})
        r.raise_for_status()
        if r.ok:
            return r.json()
        else:
            log.error("VirustotalAPI: [%s] %s", r.status_code, r.text)
