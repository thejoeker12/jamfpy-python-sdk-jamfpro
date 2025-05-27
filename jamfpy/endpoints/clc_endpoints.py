"""Endpoint module for Jamf Pro Cloud Licensing Center (CLC) operations and management."""

from requests import Request, Response
import json
from .models import ClassicEndpoint, Endpoint


class AdvancedComputerSearches(ClassicEndpoint):
    """Endpoint for managing advanced computer search configurations in Jamf Pro."""
    _uri = "/advancedcomputersearches"
    _name = "advanced_computer_searches"



class Buildings(ClassicEndpoint):
    """Endpoint for managing building locations in Jamf Pro."""
    _uri = "/buildings"
    _name = "buildings"



class Categories(ClassicEndpoint):
    """Endpoint for managing categories in Jamf Pro."""
    _uri = "/categories"
    _name = "categories"



class ExtensionAttributes(ClassicEndpoint):
    """Endpoint for managing computer extension attributes in Jamf Pro."""
    _uri = "/computerextensionattributes"
    _name = "computer_extension_attributes"


class ComputerGroups(ClassicEndpoint):
    """Endpoint for managing computer groups in Jamf Pro."""
    _uri = "/computergroups"
    _name = "computer_groups"


class Computers(ClassicEndpoint):
    """Endpoint for managing computers in Jamf Pro."""
    _uri = "/computers"
    _name = "computers"


class Departments(ClassicEndpoint):
    """Endpoint for managing departments in Jamf Pro."""
    _uri = "/departments"
    _name = "departments"


class ConfigurationProfiles(ClassicEndpoint):
    """Endpoint for managing macOS configuration profiles in Jamf Pro."""
    _uri = "/osxconfigurationprofiles"
    _name = "osx_configuration_profiles"


class Packages(ClassicEndpoint):
    """Endpoint for managing software packages in Jamf Pro."""
    _uri = "/packages"
    _name = "packages"


class Policies(ClassicEndpoint):
    """Endpoint for managing policies in Jamf Pro."""
    _uri = "/policies"
    _name = "policies"


class RestrictedSoftware(ClassicEndpoint):
    """Endpoint for managing restricted software configurations in Jamf Pro."""
    _uri = "/restrictedsoftware"
    _name = "restricted_software"


class Scripts(ClassicEndpoint):
    """Endpoint for managing scripts in Jamf Pro."""
    _uri = "/scripts"
    _name = "scripts"


class Sites(ClassicEndpoint):
    """Endpoint for managing sites in Jamf Pro."""
    _uri = "/sites"
    _name = "sites"

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

    def update_by_id(self, target_id: int, updated_configuration: str) -> Response:
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

    def create(self, config_profile: str) -> Response:
        """Create a new record."""
        suffix = self._by_id_uri + "/0"
        return self._api.do(
            Request(
                method="POST",
                url=self._api.url() + suffix,
                headers=self._api.header("create-update")["xml"],
                data=config_profile
            )
        )

    def delete_by_id(self, target_id: int) -> Response:
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
        try:
            original_json = original_response.json()
        except json.JSONDecodeError:
            raise

        users_data = original_json.get('accounts', {}).get('users', [])

        return self.pass_response(original_response, users_data)

class AccountGroups(AccountChild):
    _name = "groups"

    _uri = "/accounts"
    _by_id_uri = _uri + "/groupid"
    _by_name_uri = _uri + "/groupname"

    def get_all(self, suffix=None) -> Response:
        """ Returns all group objects under /accounts, packaged in a Response object. """
        original_response: Response = super().get_all(suffix=None)
        original_response.raise_for_status()
        try:
            original_json = original_response.json()
        except json.JSONDecodeError:
            raise

        groups_data = original_json.get('accounts', {}).get('groups', [])
        return self.pass_response(original_response, groups_data)

class Accounts(Endpoint):
    """Parent endpoint for accounts, containing Users and Groups as children"""
    _uri = "/accounts"
    _name = "accounts"

    def __init__(self, api_client):
        self._api = api_client
        self.users = AccountUsers(self._api)
        self.groups = AccountGroups(self._api)

    def get_all(self):
        classic_endpoint = ClassicEndpoint(self._api)
        return classic_endpoint.get_all(self._uri)
