class Endpoint:
    def __init__(self, api):
        from ..client.client import API
        self._api: API = api