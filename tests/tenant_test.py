"""Unit tests for Tenant config validation, API wiring, lazy auth and the timeout setting.

Every test runs under ``mocked_responses``, so a request to an unregistered URL raises
``ConnectionError`` and never leaves the process. ``Tenant()`` makes no request, so a test
registers the token endpoint only when it authenticates or sends a request (every
registration must be used).
"""
# pylint: disable=missing-function-docstring,protected-access
import base64
import logging
from importlib import metadata
from unittest.mock import patch

import pytest
import requests
from conftest import FQDN, TOKEN_URL, register_oauth_token

import jamfpy
from jamfpy.client.exceptions import JamfAuthError, JamfpyConfigError

BEARER_URL = f"{FQDN}/api/v1/auth/token"
COMPUTERS_URL = f"{FQDN}/JSSResource/computers"
SCRIPT_URL = f"{FQDN}/api/v1/scripts/1"


def _oauth_tenant(**kwargs):
    return jamfpy.Tenant(fqdn=FQDN, auth_method="oauth2", client_id="c", client_secret="s",
                         log_level=logging.CRITICAL, **kwargs)


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


def test_oauth_tenant_builds_both_apis_without_a_request(mocked_responses):
    tenant = _oauth_tenant()
    assert isinstance(tenant.pro, jamfpy.ProAPI)
    assert isinstance(tenant.classic, jamfpy.ClassicAPI)
    assert tenant.fqdn == FQDN
    assert len(mocked_responses.calls) == 0
    assert tenant.pro.auth is tenant.classic.auth is tenant._auth


def test_bare_host_fqdn_gets_https(mocked_responses):
    register_oauth_token(mocked_responses)
    mocked_responses.get(COMPUTERS_URL, json={})
    tenant = jamfpy.Tenant(fqdn=FQDN.removeprefix("https://"), auth_method="oauth2", client_id="c", client_secret="s",
                           log_level=logging.CRITICAL)
    assert tenant.fqdn == FQDN
    tenant.classic.computers.get_all()
    assert [call.request.url for call in mocked_responses.calls] == [TOKEN_URL, COMPUTERS_URL]


def test_fqdn_with_a_scheme_is_kept_as_given():
    assert jamfpy.Tenant(fqdn="http://jamf.example.com:8080", auth_method="oauth2", client_id="c",
                         client_secret="s").fqdn == "http://jamf.example.com:8080"


@pytest.mark.parametrize("kwargs, expected", [({}, 5), ({"parallelism": 1}, 1), ({"parallelism": 3}, 3)])
def test_parallelism_reaches_both_apis(kwargs, expected):
    tenant = _oauth_tenant(**kwargs)
    assert tenant.pro._parallelism == tenant.classic._parallelism == expected


def test_parallelism_zero_raises():
    with pytest.raises(ValueError, match="parallelism must be an int of at least 1, got 0"):
        _oauth_tenant(parallelism=0)


def test_authenticate_fetches_a_token_now(mocked_responses):
    token = register_oauth_token(mocked_responses)
    tenant = _oauth_tenant()

    tenant.authenticate()

    assert token.call_count == 1
    assert mocked_responses.calls[-1].request.url == TOKEN_URL


def test_first_request_fetches_the_token(mocked_responses):
    register_oauth_token(mocked_responses)
    mocked_responses.get(COMPUTERS_URL, json={"computers": []})
    tenant = _oauth_tenant()

    tenant.classic.computers.get_all()
    tenant.classic.computers.get_all()

    assert [call.request.url for call in mocked_responses.calls] == [TOKEN_URL, COMPUTERS_URL, COMPUTERS_URL]


def test_bad_credentials_raise_on_first_request_not_construction(mocked_responses):
    mocked_responses.post(TOKEN_URL, status=401, body="invalid_client")
    tenant = _oauth_tenant()
    assert len(mocked_responses.calls) == 0

    with pytest.raises(JamfAuthError):
        tenant.classic.computers.get_all()


def test_authenticate_raises_on_bad_credentials(mocked_responses):
    mocked_responses.post(TOKEN_URL, status=401, body="invalid_client")
    tenant = _oauth_tenant()

    with pytest.raises(JamfAuthError):
        tenant.authenticate()


def test_unreachable_fqdn_raises_on_first_request_not_construction(mocked_responses):
    # Nothing is registered, so the token request fails to connect, as it would against an unreachable FQDN.
    tenant = _oauth_tenant()
    assert len(mocked_responses.calls) == 0

    with pytest.raises(requests.ConnectionError):
        tenant.pro.scripts.get_by_id(1)


@pytest.mark.parametrize("timeout, expected", [({}, 30.0), ({"timeout": (3.0, 27.0)}, (3.0, 27.0))])
def test_timeout_reaches_the_token_and_api_calls(mocked_responses, timeout, expected):
    register_oauth_token(mocked_responses)
    mocked_responses.get(COMPUTERS_URL, json={"computers": []})
    tenant = _oauth_tenant(**timeout)

    tenant.classic.computers.get_all()

    token_call, api_call = mocked_responses.calls
    assert token_call.request.url == TOKEN_URL
    assert token_call.request.req_kwargs["timeout"] == expected
    assert api_call.request.req_kwargs["timeout"] == expected


def test_basic_timeout_reaches_the_bearer_token_and_pro_calls(mocked_responses):
    mocked_responses.post(BEARER_URL, json={"token": "t", "expires": "2035-01-01T00:00:00.000Z"})
    mocked_responses.get(SCRIPT_URL, json={"id": "1"})
    tenant = jamfpy.Tenant(fqdn=FQDN, auth_method="basic", username="u", password="p",
                           log_level=logging.CRITICAL, timeout=(3.0, 27.0))

    tenant.authenticate()
    tenant.pro.scripts.get_by_id(1)

    token_call, api_call = mocked_responses.calls
    assert token_call.request.url == BEARER_URL
    assert api_call.request.url == SCRIPT_URL
    assert token_call.request.req_kwargs["timeout"] == (3.0, 27.0)
    assert api_call.request.req_kwargs["timeout"] == (3.0, 27.0)


def test_oauth_timeout_reaches_the_pro_api_call(mocked_responses):
    # The Classic test above can't see a ProAPI that drops the setting: each API has its own pass-through.
    register_oauth_token(mocked_responses)
    mocked_responses.get(SCRIPT_URL, json={"id": "1"})
    tenant = _oauth_tenant(timeout=(3.0, 27.0))

    tenant.pro.scripts.get_by_id(1)

    token_call, api_call = mocked_responses.calls
    assert token_call.request.url == TOKEN_URL
    assert api_call.request.url == SCRIPT_URL
    assert token_call.request.req_kwargs["timeout"] == (3.0, 27.0)
    assert api_call.request.req_kwargs["timeout"] == (3.0, 27.0)


def test_auth_user_agent_falls_back_when_jamfpy_is_not_installed(mocked_responses):
    register_oauth_token(mocked_responses)
    # Only construction is patched: the Auth resolves its User-Agent once, then sends it on every token call.
    with patch("importlib.metadata.version", side_effect=metadata.PackageNotFoundError("jamfpy")):
        tenant = _oauth_tenant()

    tenant.authenticate()

    assert mocked_responses.calls[-1].request.url == TOKEN_URL
    assert mocked_responses.calls[-1].request.headers["User-Agent"] == "jamfpy/unknown"


def test_paths_are_stored_and_passed_on_as_str(tmp_path):
    ca_bundle = tmp_path / "ca.pem"
    client_cert = tmp_path / "client.pem"
    ca_bundle.write_text("ca")
    client_cert.write_text("cert")

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
    assert len(mocked_responses.calls) == 0

    tenant.authenticate()

    req = mocked_responses.calls[-1].request
    assert req.url == BEARER_URL
    assert req.headers["Authorization"] == f"Basic {base64.b64encode(b'u:p').decode()}"


# --- logging ---------------------------------------------------------------

KINDS = ("auth", "pro", "clc")


def _tenant_loggers(tenant):
    return {"auth": tenant._auth._logger, "pro": tenant.pro._logger, "clc": tenant.classic._logger}


def test_tenant_logs_through_three_jamfpy_children():
    tenant = _oauth_tenant()

    for kind, logger in _tenant_loggers(tenant).items():
        assert logger.name == f"jamfpy.test-{kind}"
        assert logger is logging.getLogger(f"jamfpy.test-{kind}")
        assert logger.parent is logging.getLogger("jamfpy")
        assert logger.propagate is True
        assert logger.handlers == []


def test_short_tenant_names_are_not_padded():
    tenant = jamfpy.Tenant(fqdn="https://ab.jamfcloud.com", auth_method="oauth2", client_id="c", client_secret="s")
    assert {kind: logger.name for kind, logger in _tenant_loggers(tenant).items()} == {
        kind: f"jamfpy.ab-{kind}" for kind in KINDS
    }


@pytest.mark.parametrize("kwargs, level", [({}, logging.INFO), ({"log_level": logging.DEBUG}, logging.DEBUG)])
def test_log_level_sets_all_three_loggers(kwargs, level):
    tenant = jamfpy.Tenant(fqdn=FQDN, auth_method="oauth2", client_id="c", client_secret="s", **kwargs)
    assert {kind: logger.level for kind, logger in _tenant_loggers(tenant).items()} == dict.fromkeys(KINDS, level)


@pytest.mark.parametrize("auth_method, credentials", [
    ("oauth2", {"client_id": "c", "client_secret": "s"}),
    ("basic", {"username": "u", "password": "p"}),
])
@pytest.mark.parametrize("safe_mode", [True, False])
def test_safe_mode_reaches_auth_and_both_apis(auth_method, credentials, safe_mode):
    tenant = jamfpy.Tenant(fqdn=FQDN, auth_method=auth_method, safe_mode=safe_mode, **credentials)
    assert (tenant._auth._safe_mode, tenant.pro._safe_mode, tenant.classic._safe_mode) == (safe_mode,) * 3
