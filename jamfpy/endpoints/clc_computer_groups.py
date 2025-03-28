"""Jamf Classic API Endpoint Code for Computer Groups"""

from requests import Request, Response
from ._parent import Endpoint

class ComputerGroups(Endpoint):

    _uri = "/computergroups"
    _name = "computer_groups"


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
    
    def get_by_name(self, target_id: int) -> Response:
        suffix = self._uri + f"/name/{target_id}"
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
            ),
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
        )

        
