"""Jamf Classic API Endpoint functions for Dock Items"""

from requests import Request, Response
from .endpoint_parent import Endpoint

class DockItems(Endpoint):

    _uri = "/dockitems"

def create(self, payload: str) -> Response:
    suffix = self._uri
    return self._api.do(
        Request(
            method="POST",
            url=self._api.url() + suffix,
            headers=self._api.header("create-update")["xml"],
            data=payload
        )
    )

