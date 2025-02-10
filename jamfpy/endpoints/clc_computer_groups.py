"""Jamf Classic API Endpoint Code for Computer Groups"""

from requests import Request, Response
from .endpoint_parent import Endpoint

class ComputerGroups(Endpoint):

    _uri = "/computergroups"

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
            )
        )

    def delete_by_id(self, target_id) -> Response:
        suffix = self._uri + f"/id/{target_id}"
        return self._api.do(
            Request(
                method="DELETE",
                url=self._api.url() + suffix,
                headers=self._api.header("delete")["xml"]
            ),
            error_on_fail=False
        )

    def create(self, xml) -> Response:
        suffix = self._uri + f"/id/0"
        return self._api.do(
            Request(
                method="POST",
                url=self._api.url() + suffix,
                headers=self._api.header("create-update")["xml"],
                data=xml
            ),
            error_on_fail=False
        )

        
