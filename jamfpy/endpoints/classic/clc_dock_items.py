"""Jamf Classic API Endpoint functions for Dock Items"""

from requests import Request
from ..endpoint_parent import Endpoint

class DockItems(Endpoint):

    _uri = "/dockitems"

    def create(self):
        suffix = self._uri
        url = self._api.url() + suffix
        headers = self._api.header("basic-xml")
        req = Request("POST", url=url, headers=headers)
        resp = self._api.do(req)
        return resp
