import requests
from ..fileDatabase import Jsondb
from ..database import sqldb
from ..types import McssServerAction, APIType
from ..models.others import McssServer

class McssAPI:
    PORT = 25560
    URL = f"http://localhost:{PORT}/api/v2"
    
    def __init__(self):
        self.headers = {
           'apikey': sqldb.get_bot_token(APIType.MCSS).access_token,
        }

    def get_servers(self):
        r = requests.get(f'{self.URL}/servers', headers=self.headers)
        r.raise_for_status()
        if r.ok:
            return [McssServer(**i)for i in r.json()]
        else:
            print(f"[{r.status_code}] {r.text}")

    def get_server_detail(self, server_id: str):
        r = requests.get(f"{self.URL}/servers/{server_id}", headers=self.headers)
        r.raise_for_status()
        if r.ok:
            return McssServer(**r.json())
        else:
            print(f"[{r.status_code}] {r.text}")

    def excute_action(self, server_id: str, action: McssServerAction):
        data = {
            'action': McssServerAction(action).value
        }
        r = requests.post(f"{self.URL}/servers/{server_id}/execute/action", json=data, headers=self.headers)
        r.raise_for_status()
        if r.ok:
            return True
        else:
            print(f"[{r.status_code}] {r.text}")
            return False
    
    def excute_command(self, server_id: str, command: str):
        data = {
            'command': command
        }
        r = requests.post(f"{self.URL}/servers/{server_id}/execute/command", json=data, headers=self.headers)
        r.raise_for_status()
        if r.ok:
            return r.text
        else:
            print(f"[{r.status_code}] {r.text}")