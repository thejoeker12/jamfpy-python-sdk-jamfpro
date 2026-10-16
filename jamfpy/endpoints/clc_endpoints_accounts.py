
from typing import TYPE_CHECKING

from requests import Response, Request
from .models import ClassicEndpoint, Endpoint

if TYPE_CHECKING:
    from ..client.api import API


class AccountChild(ClassicEndpoint):
    """Base class for account-related sub-endpoints; users and groups."""

    _by_id_uri: str
    _by_name_uri: str

    def get_by_id(self, target_id: int) -> Response:  # type: ignore[override]
        """Get a single record by ID."""
        # Drops the base's xml_response argument; restoring it would change this public signature.

        suffix = self._by_id_uri + f"/{target_id}"
        return self._api.do(
            Request(
                method="GET",
                url=self._api.url() + suffix,
                headers=self._api.header("read")["json"]
            )
        )


    def update_by_id(self, target_id: int, updated_configuration: str) -> Response:  # pylint: disable=R0801
        """Update a record by ID with new configuration."""
        suffix = self._by_id_uri + f"/{target_id}"
        return self._api.do(
            Request(
                method="PUT",
                url=self._api.url() + suffix,
                headers=self._api.header("create-update")["xml"],
                data=updated_configuration
            )
        )


    def create(self, config_profile: str) -> Response:  # pylint: disable=R0801
        """Create a new record."""
        suffix = f"{self._by_id_uri}/0"
        return self._api.do(
            Request(
                method="POST",
                url=self._api.url() + suffix,
                headers=self._api.header("create-update")["xml"],
                data=config_profile
            )
        )

    def delete_by_id(self, target_id: int) -> Response:  # pylint: disable=R0801
        """Delete a record by ID."""
        suffix = self._by_id_uri + f"/{target_id}"
        return self._api.do(
            Request(
                method="DELETE",
                url=self._api.url() + suffix,
            )
        )

class AccountUsers(AccountChild):
    """Endpoing for managing users under the account endpoint in Jamf Pro"""
    _name = "users"

    _uri = "/accounts"
    _by_id_uri = _uri + "/userid"
    _by_name_uri = _uri + "/username"

    def get_all(self, suffix: str | None = None) -> Response:  # type: ignore[override]
        """Returns a Response object with its JSON content modified to only include users.

        A non-ok ``/accounts`` Response is returned as-is.
        """
        # Drops the base's xml_response argument; restoring it would change this public signature.
        original_response: Response = super().get_all(suffix=None)
        if not original_response.ok:
            return original_response
        original_json = original_response.json()

        users_data = {self._name : original_json.get('accounts', {}).get('users', [])}

        return self._repackage_response(original_response, users_data)


class AccountGroups(AccountChild):
    """Endpoing for managing groups under the account endpoint in Jamf Pro"""

    _name = "groups"

    _uri = "/accounts"
    _by_id_uri = _uri + "/groupid"
    _by_name_uri = _uri + "/groupname"

    def get_all(self, suffix: str | None = None) -> Response:  # type: ignore[override]
        """Returns all group objects under /accounts, packaged in a Response object.

        A non-ok ``/accounts`` Response is returned as-is.
        """
        # Drops the base's xml_response argument; restoring it would change this public signature.
        original_response: Response = super().get_all(suffix=None)
        if not original_response.ok:
            return original_response
        original_json = original_response.json()

        groups_data = {self._name : original_json.get('accounts', {}).get('groups', [])}
        return self._repackage_response(original_response, groups_data)


class Accounts(Endpoint):
    """Parent endpoint for accounts, containing Users and Groups as children"""
    _uri = "/accounts"
    _name = "accounts"

    def __init__(self, api_client: "API") -> None:
        super().__init__(api_client)
        self._api = api_client
        self.users = AccountUsers(self._api)
        self.groups = AccountGroups(self._api)

    def get_all(self) -> Response:
        """ Get all made to /accounts which includes groups and users """
        classic_endpoint = ClassicEndpoint(self._api)
        return classic_endpoint.get_all(self._uri)
