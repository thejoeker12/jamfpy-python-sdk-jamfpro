"""Endpoint module for Jamf Pro Cloud Licensing Center (CLC) operations and management."""
from .models import ClassicEndpoint


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
    _name = "os_x_configuration_profiles"


class MobileDeviceGroups(ClassicEndpoint):
    """Endpoint for managing mobile device groups in Jamf Pro."""
    _uri = "/mobiledevicegroups"
    _name = "mobile_device_groups"


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
