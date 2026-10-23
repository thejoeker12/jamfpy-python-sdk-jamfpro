"""Unit tests for the Classic endpoint registry and ClassicAPI wiring."""
# pylint: disable=missing-function-docstring
import pytest
from conftest import FQDN, sent_headers, with_bearer

from jamfpy.client.constants import DEFAULT_HTTP_CONFIG_HEADERS as H
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
def test_get_by_id_builds_expected_url(classic_api, mocked_responses, cls, uri, name):  # pylint: disable=unused-argument
    url = f"{FQDN}/JSSResource{uri}/id/7"
    mocked_responses.get(url, json={})
    cls(classic_api).get_by_id(7)
    req = mocked_responses.calls[-1].request
    assert req.method == "GET"
    assert req.url == url
    assert sent_headers(req) == with_bearer(H["crud"]["read"]["json"])


# Endpoint attributes ProAPI/ClassicAPI wiring must expose (client.py).
EXPECTED_ATTRS = [
    "computer_groups", "mobile_device_groups", "mobile_device_configuration_profiles",
    "policies", "configuration_profiles",
    "computer_extension_attributes", "categories", "computer_searches", "scripts",
    "buildings", "packages", "computers", "mobile_devices", "sites", "departments",
    "accounts", "restricted_software",
]


@pytest.mark.parametrize("attr", EXPECTED_ATTRS)
def test_classic_api_wires_endpoint(classic_api, attr):
    assert hasattr(classic_api, attr)
