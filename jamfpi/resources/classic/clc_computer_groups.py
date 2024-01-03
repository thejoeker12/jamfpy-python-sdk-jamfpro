import requests

class ComputerGroups:
    def __init__(self, api_config):
        from ...client.api import API
        self._api: API = api_config

    def get_by_id(self, id: int):
        suffix = f"/computergroups/id/{id}"
        url = self._api.url() + suffix
        headers = self._api.header("basic_json")
        req = requests.Request("GET", url=url, headers=headers)
        call = self._api.do(req)
        return call
