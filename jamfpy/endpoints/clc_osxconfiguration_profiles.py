"""Endpoints for configuration profiles"""

from ._parent import Endpoint


class ConfigurationProfiles(Endpoint):
    """Configuration profiles object"""
    _uri = "/osxconfigurationprofiles"
    _name = "osx_configuration_profiles"

