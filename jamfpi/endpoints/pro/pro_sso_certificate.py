from requests import Request

class SsoCertificates:
    def __init__(self, api):
        from ...client.client import API
        self._api: API = api

    def get_certificate(self):
        suffix = "/sso/cert"
        url = self._api.url("1") + suffix
        headers = self._api.header("basic-json")
        request = Request("GET", url=url, headers=headers)
        call = self._api.do(request)
        return call
