"""Endpoint code for Jamf Classic API Policies"""

from requests import Request, Response
from ._parent import Endpoint


class Policies(Endpoint):
    
    _uri = "/policies"

    def get_all(self) -> Response:
        suffix = self._uri
        return self._api.do(
            Request(
                method="GET",
                url=self._api.url() + suffix,
                headers=self._api.header("read")["json"]
            )
        )

    def get_by_id(self, target_id: int) -> Response:
        suffix = self._uri + f"/id/{target_id}"
        return self._api.do(
            Request(
                method="GET",
                url=self._api.url() + suffix,
                headers=self._api.header("read")["json"]
            ),
            error_on_fail=False
        )

    def create(self, policy_xml: str) -> Response:
        suffix = self._uri + "/id/0"
        return self._api.do(
            Request(
                method="POST",
                url=self._api.url() + suffix,
                headers=self._api.header("create-update")["xml"],
                data=policy_xml
            ),
            error_on_fail=False
        )

    def delete_by_id(self, target_id) -> Response:
        suffix = self._uri + f"/id/{target_id}"
        return self._api.do(
            Request(
                method="DELETE",
                url=self._api.url() + suffix,
            ),
        )
