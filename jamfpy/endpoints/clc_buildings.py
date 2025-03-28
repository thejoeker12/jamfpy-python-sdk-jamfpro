"""Jamf Classic API Endpoint for Buildings"""

from requests import Request, Response
from ._parent import Endpoint

class Buildings(Endpoint):
    _uri = "/buildings"
    _name = "buildings"

    def get_all(self) -> Response:
        suffix = self._uri
        return self._api.do(
            Request(
                method = "GET",
                url = self._api.url() + suffix,
                headers = self._api.header("read")["json"]
            )
        )
    
    def delete_by_id(self, target_id) -> Response:
        suffix = self._uri + f"/id/{target_id}"
        return self._api.do(
            Request(
                method = "DELETE",
                url=self._api.url()+ suffix,
                headers = self._api.header("delete")["xml"]
            )
        )