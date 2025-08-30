
import json

from requests import Response, Request
from .models import ClassicEndpoint, Endpoint


class AccountChild(ClassicEndpoint):
    """Base class for account-related sub-endpoints; users and groups."""

    _by_id_uri: str = None
    _by_name_uri: str = None

    def pass_response(self, original_response: Response, new_data) -> Response:
        """Packages new_data into a Response object based on original_response."""
        new_response = Response()

        new_response.status_code = original_response.status_code
        new_response.headers = original_response.headers.copy()
        new_response.encoding = original_response.encoding
        new_response.url = original_response.url
        new_response.request = original_response.request

        modified_json_string = json.dumps(new_data)

        response_encoding = new_response.encoding if new_response.encoding else 'utf-8'
        # This is acknowledging that accessing protected members is frowned upon, but nececcary for this use case.
        new_response._content = modified_json_string.encode(response_encoding)  # pylint: disable=protected-access

        new_response.headers['Content-Length'] = str(len(new_response._content))  # pylint: disable=protected-access

        return new_response


    def get_by_id(self, target_id: int) -> Response:
        """Get a single record by ID."""

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

    def get_all(self, suffix=None) -> Response:
        """Returns a Response object with its JSON content modified to only include users."""
        original_response: Response = super().get_all(suffix=None)
        original_response.raise_for_status()
        original_json = original_response.json()

        users_data = {self._name : original_json.get('accounts', {}).get('users', [])}

        return self.pass_response(original_response, users_data)


class AccountGroups(AccountChild):
    """Endpoing for managing groups under the account endpoint in Jamf Pro"""

    _name = "groups"

    _uri = "/accounts"
    _by_id_uri = _uri + "/groupid"
    _by_name_uri = _uri + "/groupname"

    def get_all(self, suffix=None) -> Response:
        """ Returns all group objects under /accounts, packaged in a Response object. """
        original_response: Response = super().get_all(suffix=None)
        original_response.raise_for_status()
        original_json = original_response.json()

        groups_data = {self._name : original_json.get('accounts', {}).get('groups', [])}
        return self.pass_response(original_response, groups_data)


class Accounts(Endpoint):
    """Parent endpoint for accounts, containing Users and Groups as children"""
    _uri = "/accounts"
    _name = "accounts"

    def __init__(self, api_client):
        super().__init__(api_client)
        self._api = api_client
        self.users = AccountUsers(self._api)
        self.groups = AccountGroups(self._api)

    def get_all(self):
        """ Get all made to /accounts which includes groups and users """
        classic_endpoint = ClassicEndpoint(self._api)
        return classic_endpoint.get_all(self._uri)
