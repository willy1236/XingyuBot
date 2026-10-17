from starlib.providers.general.others import McsManagerAPI


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


def test_daemon_id_comes_from_visible_auth_instances(monkeypatch):
    api = McsManagerAPI.__new__(McsManagerAPI)
    api.apikey = "test-key"
    api._daemon_id = None
    requests = []

    def fake_get(endpoint, params):
        requests.append((endpoint, params))
        return FakeResponse(
            {
                "data": {
                    "instances": [
                        {"instanceUuid": "instance-a", "daemonId": "daemon-1"},
                        {"instanceUuid": "instance-b", "daemonId": "daemon-1"},
                    ]
                }
            }
        )

    monkeypatch.setattr(api, "get", fake_get)

    assert api.daemon_id == "daemon-1"
    assert api.daemon_id == "daemon-1"
    assert requests == [("auth", {"apikey": "test-key"})]
