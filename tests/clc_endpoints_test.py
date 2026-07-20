"""Unit tests for the Classic endpoint registry and ClassicAPI wiring."""
# pylint: disable=missing-function-docstring,redefined-outer-name
from unittest.mock import MagicMock

import pytest
from conftest import FakeAPI, FQDN

from jamfpy.client.client import ClassicAPI
from jamfpy.client.http_config import HTTPConfig
from jamfpy.endpoints import clc_endpoints as clc

# (class, _uri, _name) for every Classic endpoint. Guards accidental URI/name drift.
CLASSIC_ENDPOINTS = [
    (clc.AdvancedComputerSearches, "/advancedcomputersearches", "advanced_computer_searches"),
    (clc.Buildings, "/buildings", "buildings"),
    (clc.Categories, "/categories", "categories"),
    (clc.ExtensionAttributes, "/computerextensionattributes", "computer_extension_attributes"),
    (clc.ComputerGroups, "/computergroups", "computer_groups"),
    (clc.Computers, "/computers", "computers"),
    (clc.Departments, "/departments", "departments"),
    (clc.ConfigurationProfiles, "/osxconfigurationprofiles", "os_x_configuration_profiles"),
    (clc.MobileDeviceConfigurationProfiles, "/mobiledeviceconfigurationprofiles", "configuration_profiles"),
    (clc.MobileDeviceGroups, "/mobiledevicegroups", "mobile_device_groups"),
    (clc.MobileDevices, "/mobiledevices", "mobile_devices"),
    (clc.Packages, "/packages", "packages"),
    (clc.Policies, "/policies", "policies"),
    (clc.RestrictedSoftware, "/restrictedsoftware", "restricted_software"),
    (clc.Scripts, "/scripts", "scripts"),
    (clc.Sites, "/sites", "sites"),
]


@pytest.mark.parametrize("cls,uri,name", CLASSIC_ENDPOINTS)
def test_uri_and_name(cls, uri, name):
    assert cls._uri == uri  # pylint: disable=protected-access
    assert cls._name == name  # pylint: disable=protected-access


@pytest.mark.parametrize("cls,uri,name", CLASSIC_ENDPOINTS)
def test_get_by_id_builds_expected_url(cls, uri, name):  # pylint: disable=unused-argument
    api = FakeAPI()
    cls(api).get_by_id(7)
    assert api.last_request.url == f"{FQDN}/JSSResource{uri}/id/7"


# Endpoint attributes ProAPI/ClassicAPI wiring must expose (client.py).
EXPECTED_ATTRS = [
    "computer_groups", "mobile_device_groups", "mobile_device_configuration_profiles",
    "policies", "configuration_profiles",
    "computer_extension_attributes", "categories", "computer_searches", "scripts",
    "buildings", "packages", "computers", "mobile_devices", "sites", "departments",
    "accounts", "restricted_software",
]


@pytest.fixture
def classic_api(silent_logger):
    auth = MagicMock()
    auth.token.return_value = "tok"
    return ClassicAPI(fqdn=FQDN, auth=auth, http_config=HTTPConfig(),
                      safe_mode=True, session=MagicMock(), logger=silent_logger)


@pytest.mark.parametrize("attr", EXPECTED_ATTRS)
def test_classic_api_wires_endpoint(classic_api, attr):
    assert hasattr(classic_api, attr)
