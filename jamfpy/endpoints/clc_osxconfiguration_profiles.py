"""Endpoints for configuration profiles"""

from requests import Request, Response
from ._parent import Endpoint


class ConfigurationProfiles(Endpoint):
    """Configuration profiles object"""
    _uri = "/osxconfigurationprofiles"

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
        suffix = self._uri + f"/id/{target_id}"
        return self._api.do(
            Request(
                method="DELETE",
                url=self._api.url() + suffix,
                headers=self._api.header("delete")["xml"]
            )
        )

