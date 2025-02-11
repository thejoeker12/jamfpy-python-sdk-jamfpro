"""computer advanced searches"""

from requests import Request, Response
from ._parent import Endpoint
from ..client.client import API

class AdvancedComputerSearches(Endpoint):
    _uri = "/advancedcomputersearches"

    def get_all(self) -> Response:
        suffix = self._uri
        return self._api.do(
            Request(
                "GET",
                url = self._api.url() + suffix,
                headers = self._api.header("read")["json"]
            )
        )