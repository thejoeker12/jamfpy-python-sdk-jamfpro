"""Unit tests for Tenant config validation and API wiring.

Every test runs under ``mocked_responses``. The validation paths raise before Tenant's
eager ``set_new_token()`` call, so they register nothing (a request would raise
``ConnectionError``, never leave the process). The happy paths register the token endpoint
and build a real ``Tenant`` against it.
"""
# pylint: disable=missing-function-docstring,protected-access
import base64
import logging
from unittest.mock import patch

import pytest
from conftest import FQDN, TOKEN_URL, register_oauth_token

import jamfpy
from jamfpy.client.exceptions import JamfpyConfigError

BEARER_URL = f"{FQDN}/api/v1/auth/token"

pytestmark = pytest.mark.usefixtures("mocked_responses")


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


def test_oauth_tenant_builds_both_apis(mocked_responses):
    token = register_oauth_token(mocked_responses)
    tenant = jamfpy.Tenant(fqdn=FQDN, auth_method="oauth2", client_id="c",
                           client_secret="s", log_level=logging.CRITICAL)
    assert isinstance(tenant.pro, jamfpy.ProAPI)
    assert isinstance(tenant.classic, jamfpy.ClassicAPI)
    assert tenant.fqdn == FQDN
    # Characterises current behaviour: construction fetches the token eagerly, once, for one Auth both APIs share.
    assert token.call_count == 1
    assert mocked_responses.calls[-1].request.url == TOKEN_URL
    assert tenant.pro.auth is tenant.classic.auth


def test_paths_are_stored_and_passed_on_as_str(mocked_responses, tmp_path):
    ca_bundle = tmp_path / "ca.pem"
    client_cert = tmp_path / "client.pem"
    ca_bundle.write_text("ca")
    client_cert.write_text("cert")

    register_oauth_token(mocked_responses)
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


def test_validate_path_runs_once_per_tenant(mocked_responses):
    register_oauth_token(mocked_responses)
    with patch.object(jamfpy.Tenant, "_validate_path") as mock_validate:
        jamfpy.Tenant(fqdn=FQDN, auth_method="oauth2", client_id="c", client_secret="s",
                      log_level=logging.CRITICAL)
    mock_validate.assert_called_once_with(cert_path=None, verify_path=None)


def test_basic_tenant_builds_both_apis(mocked_responses):
    mocked_responses.post(BEARER_URL, json={"token": "t", "expires": "2035-01-01T00:00:00.000Z"})
    tenant = jamfpy.Tenant(fqdn=FQDN, auth_method="basic", username="u",
                           password="p", log_level=logging.CRITICAL)
    assert isinstance(tenant.pro, jamfpy.ProAPI)
    assert isinstance(tenant.classic, jamfpy.ClassicAPI)
    req = mocked_responses.calls[-1].request
    assert req.url == BEARER_URL
    assert req.headers["Authorization"] == f"Basic {base64.b64encode(b'u:p').decode()}"
