"""Module for Endpoint parent class"""

# pylint: disable=import-outside-toplevel
from requests import Request, Response

class Endpoint:
    """Endpoint parent class"""
    _uri = None
    _name = None
    def __init__(self, api):
        from ..client.client import API
        api: API
        self._api = api

    def get_all(self) -> Response:
        print("RUN GET ALL")
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

    def update_by_id(self, target_id: int, updated_configuration: str) -> Response:
        suffix = self._uri + f"/id/{target_id}"
        return self._api.do(
            Request(
                method="PUT",
                url=self._api.url() + suffix,
                headers=self._api.header("create-update")["xml"],
                data=updated_configuration
            )
        )

    def create(self, config_profile: str) -> Response:
        suffix = self._uri + "/id/0"
        return self._api.do(
            Request(
                method="POST",
                url=self._api.url() + suffix,
                headers=self._api.header("create-update")["xml"],
                data=config_profile
            )
        )

    def delete_by_id(self, target_id: int) -> Response:
        print("RUN DELETE BY ID")
        suffix = self._uri + f"/id/{target_id}"
        return self._api.do(
            Request(
                method="DELETE",
                url=self._api.url() + suffix,
            )
        )


