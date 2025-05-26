"""Endpoint module for Jamf Pro Cloud Licensing Center (CLC) operations and management."""

from requests import Request, Response
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

class AccountUsers(ClassicEndpoint):
    """Endpoing for managing users under the account endpoint in Jamf Pro"""
    _name = "users"

    _uri = "/accounts"
    _by_id_uri = _uri + "/userid"
    _by_name_uri = _uri + "/username"

    def get_all(self):
        """ Returns all group objects under /accounts """
        all_objects = super().get_all()
        groups = all_objects["users"]
        return groups

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
        suffix = self._by_id_uri + f"/0"
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

class AccountGroups(ClassicEndpoint):
    _name = "groups"

    _uri = "/accounts"
    _by_id_uri = _uri + "/groupid"
    _by_name_uri = _uri + "/groupname"

    def get_all(self):
        """ Returns all group objects under /accounts """
        all_objects = super().get_all()
        groups = all_objects["groups"]
        return groups

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
        suffix = self._by_id_uri + f"/0"
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

class Accounts(Endpoint):
    _uri = "/accounts"
    _name = "accounts"
    
    def get_all(self):
        classic_endpoint = ClassicEndpoint()
        return classic_endpoint.get_all()

    # users = AccountUsers()
    # groups = AccountGroups()
