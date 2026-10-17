from starlib.database import APIType, McsmServerAction, McssServerAction, sqldb

from ..base import APICaller
from .models import McsmInstance, McssServer


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


class McsManagerAPI(APICaller):
    PORT = 23333
    base_url = f"http://localhost:{PORT}/api"

    _action_endpoint = {
        McsmServerAction.Start: "open",
        McsmServerAction.Stop: "stop",
        McsmServerAction.Restart: "restart",
        McsmServerAction.Kill: "kill",
    }

    def __init__(self):
        super().__init__(headers={"X-Requested-With": "XMLHttpRequest"})
        self.apikey = sqldb.get_access_token(APIType.MCSMANAGER).access_token
        self._daemon_id: str | None = None

    @property
    def daemon_id(self):
        if self._daemon_id is None:
            r = self.get("auth", params={"apikey": self.apikey})
            instances = r.json()["data"]["instances"] if r is not None else []
            daemon_ids = {instance["daemonId"] for instance in instances}
            if len(daemon_ids) != 1:
                raise RuntimeError(f"預期只有一個 MCSManager 節點，但實際找到 {len(daemon_ids)} 個，請確認節點設定")
            self._daemon_id = daemon_ids.pop()
        return self._daemon_id

    def _get_daemon_ids_from_remote_services(self):
        """保留管理員端點的查詢方式，供未來需要服務資訊時使用。

        一般使用者沒有此端點權限；取得目前使用者可操作的 daemon 時，
        請改用 ``daemon_id``，它會透過 ``GET /api/auth`` 的 instances 判斷。
        """
        r = self.get("service/remote_services_list", params={"apikey": self.apikey})
        daemons = r.json()["data"] if r is not None else []
        return {daemon["uuid"] for daemon in daemons}

    def get_servers(self):
        r = self.get("auth", params={"apikey": self.apikey, "advanced": "true"})
        if r is None:
            return []
        return [McsmInstance(**instance) for instance in r.json()["data"]["instances"]]

    def get_server_detail(self, server_id: str):
        r = self.get("instance", params={"apikey": self.apikey, "uuid": server_id, "daemonId": self.daemon_id})
        return McsmInstance(**{**r.json()["data"], "daemonId": self.daemon_id}) if r is not None else None

    def excute_action(self, server_id: str, action: McsmServerAction):
        endpoint = self._action_endpoint[McsmServerAction(action)]
        self.get(f"protected_instance/{endpoint}", params={"apikey": self.apikey, "uuid": server_id, "daemonId": self.daemon_id})
        return True

    def excute_command(self, server_id: str, command: str):
        r = self.get(
            "protected_instance/command",
            params={"apikey": self.apikey, "uuid": server_id, "daemonId": self.daemon_id, "command": command},
        )
        return r.text if r is not None else None


class VirustotalAPI(APICaller):
    base_url = "https://www.virustotal.com/api/v3"

    def __init__(self):
        super().__init__(headers={"x-apikey": sqldb.get_access_token(APIType.Virustotal).access_token})

    def get_url_report(self, url: str):
        """取得網址的 Virustotal 報告"""
        r = self.post("urls", data={"url": url})
        return r.json()
