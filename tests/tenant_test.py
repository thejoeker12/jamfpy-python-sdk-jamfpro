"""Unit tests for Tenant config validation and API wiring.

The validation paths raise before Tenant's live ``set_new_token()`` call, so they
need no mocking. The happy-path construction patches ``set_new_token`` to a no-op.
"""
# pylint: disable=missing-function-docstring,protected-access
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


def test_paths_are_stored_and_passed_on_as_str(tmp_path):
    ca_bundle = tmp_path / "ca.pem"
    client_cert = tmp_path / "client.pem"
    ca_bundle.write_text("ca")
    client_cert.write_text("cert")

    with patch.object(jamfpy.OAuth, "set_new_token", return_value=None):
        tenant = jamfpy.Tenant(fqdn=FQDN, auth_method="oauth2", client_id="c", client_secret="s",
                               log_level=logging.CRITICAL, verify_path=str(ca_bundle), cert_path=str(client_cert))

    assert isinstance(tenant.verify_path, str)
    assert isinstance(tenant.cert_path, str)
    assert tenant.verify_path == str(ca_bundle)
    assert tenant.cert_path == str(client_cert)
    assert tenant.pro.auth.verify_path == str(ca_bundle)
    for api in (tenant.pro, tenant.classic):
        assert api._session.verify == str(ca_bundle)
        assert api._session.cert == str(client_cert)


def test_validate_path_runs_once_per_tenant():
    with patch.object(jamfpy.OAuth, "set_new_token", return_value=None), \
            patch.object(jamfpy.Tenant, "_validate_path") as mock_validate:
        jamfpy.Tenant(fqdn=FQDN, auth_method="oauth2", client_id="c", client_secret="s",
                      log_level=logging.CRITICAL)
    mock_validate.assert_called_once_with(cert_path=None, verify_path=None)


def test_basic_tenant_builds_both_apis():
    with patch.object(jamfpy.BasicAuth, "set_new_token", return_value=None):
        tenant = jamfpy.Tenant(fqdn=FQDN, auth_method="basic", username="u",
                               password="p", log_level=logging.CRITICAL)
    assert isinstance(tenant.pro, jamfpy.ProAPI)
    assert isinstance(tenant.classic, jamfpy.ClassicAPI)
