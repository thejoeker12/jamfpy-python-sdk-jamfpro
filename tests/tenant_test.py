"""Unit tests for Tenant config validation and API wiring.

The validation paths raise before Tenant's live ``set_new_token()`` call, so they
need no mocking. The happy-path construction patches ``set_new_token`` to a no-op.
"""
# pylint: disable=missing-function-docstring
import logging
from unittest.mock import patch

import pytest
from conftest import FQDN

import jamfpy
from jamfpy.client.exceptions import JamfpyConfigError


def test_invalid_auth_method_raises():
    with pytest.raises(JamfpyConfigError):
        jamfpy.Tenant(fqdn=FQDN, auth_method="bogus", client_id="c", client_secret="s")


def test_oauth_missing_credentials_raises():
    with pytest.raises(JamfpyConfigError):
        jamfpy.Tenant(fqdn=FQDN, auth_method="oauth2", client_id=None, client_secret=None)


def test_basic_missing_credentials_raises():
    with pytest.raises(JamfpyConfigError):
        jamfpy.Tenant(fqdn=FQDN, auth_method="basic", username=None, password=None)


def test_missing_cert_path_raises(tmp_path):
    missing = tmp_path / "missing.pem"
    with pytest.raises(JamfpyConfigError):
        jamfpy.Tenant(fqdn=FQDN, auth_method="oauth2", client_id="c", client_secret="s",
                      cert_path=str(missing))


def test_directory_cert_path_raises(tmp_path):
    with pytest.raises(JamfpyConfigError):
        jamfpy.Tenant(fqdn=FQDN, auth_method="oauth2", client_id="c", client_secret="s",
                      cert_path=str(tmp_path))


def test_oauth_tenant_builds_both_apis():
    with patch.object(jamfpy.OAuth, "set_new_token", return_value=None):
        tenant = jamfpy.Tenant(fqdn=FQDN, auth_method="oauth2", client_id="c",
                               client_secret="s", log_level=logging.CRITICAL)
    assert isinstance(tenant.pro, jamfpy.ProAPI)
    assert isinstance(tenant.classic, jamfpy.ClassicAPI)
    assert tenant.fqdn == FQDN


def test_basic_tenant_builds_both_apis():
    with patch.object(jamfpy.BasicAuth, "set_new_token", return_value=None):
        tenant = jamfpy.Tenant(fqdn=FQDN, auth_method="basic", username="u",
                               password="p", log_level=logging.CRITICAL)
    assert isinstance(tenant.pro, jamfpy.ProAPI)
    assert isinstance(tenant.classic, jamfpy.ClassicAPI)
