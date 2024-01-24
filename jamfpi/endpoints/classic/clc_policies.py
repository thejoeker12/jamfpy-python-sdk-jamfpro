"""Endpoint code for Jamf Classic API Policies"""

from ..endpoint_parent import Endpoint
from requests import Request

class Policies(Endpoint):
    # // TODO docstring
    _uri = "/policies"

    def get_by_id(self, id: int, resp_type: str):
        # // TODO docstring
        url = self._api.url() + self._uri + f"/id/{id}"
        headers = self._api.header(f"basic-{resp_type}")
        req = Request("GET", url, headers=headers)
        resp = self._api.do(req)
        return resp
