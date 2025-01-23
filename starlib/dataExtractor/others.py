from typing import Any
import requests
from starlib.fileDatabase import Jsondb

class McssAPI:
    PORT = 25560
    URL = f"http://localhost:{PORT}/api/v2"
    
    def __init__(self):
        self.headers = {
           'apikey': Jsondb.get_token("mcss_api")
        }

    def get_servers(self) -> list[dict] | None:
        r = requests.get('http://localhost:25560/api/v2/servers', headers=self.headers)
        r.raise_for_status()
        if r.ok:
            return r.json()
        else:
            print(r.status_code)

    def get_server_detail(self, server_id: str) -> dict | None:
        r = requests.get(f"{self.URL}/servers/{server_id}", headers=self.headers)
        r.raise_for_status()
        if r.ok:
            return r.json()
        else:
            print(r.status_code)

    def excute_action(self, server_id: str, action: int):
        params = {
            'action': action
        }
        r = requests.post(f"{self.URL}/servers/{server_id}/execute/action", params=params, headers=self.headers)
        r.raise_for_status()
        if r.ok:
            return r.text
        else:
            print(r.status_code)
    
    def excute_command(self, server_id: str, command: str):
        params = {
            'command': command
        }
        r = requests.post(f"{self.URL}/servers/{server_id}/execute/command", params=params, headers=self.headers)
        r.raise_for_status()
        if r.ok:
            return r.text
        else:
            print(r.status_code)