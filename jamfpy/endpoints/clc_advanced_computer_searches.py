"""computer advanced searches"""

from requests import Request, Response
from ._parent import Endpoint

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
    
    def delete_by_id(self, target_id: int | str):
        suffix = f"/id/{target_id}"
        return self._api.do(
            Request(
                "DELETE",
                url = self._uri + suffix
            )
        )
