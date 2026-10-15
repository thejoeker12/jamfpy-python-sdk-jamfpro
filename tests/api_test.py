"""Unit tests for the API base behaviour via ClassicAPI / ProAPI.

The one wire call (``API.do`` -> ``session.send``) and the auth refresh are
mocked; construction itself does no network.
"""
# pylint: disable=missing-function-docstring,protected-access,redefined-outer-name
import logging
from unittest.mock import MagicMock, patch

import pytest
from requests import Request, Session
from requests.adapters import HTTPAdapter
from conftest import FQDN, make_response

from jamfpy.client.client import ClassicAPI, ProAPI
from jamfpy.client.http_config import HTTPConfig
from jamfpy.client.constants import DEFAULT_HTTP_CONFIG_HEADERS
from jamfpy.client.exceptions import JamfpyConfigError


@pytest.fixture
def mock_auth():
    auth = MagicMock()
    auth.token.return_value = "tok"
    return auth


@pytest.fixture
def warning_logger():
    """A logger at WARNING that propagates, so caplog sees exactly what a WARNING-level user would."""
    logger = logging.getLogger("jamfpy-test-api-warnings")
    logger.handlers.clear()
    logger.setLevel(logging.WARNING)
    logger.propagate = True
    return logger


@pytest.fixture
def clean_env(monkeypatch):
    """Clear the CA bundle and proxy env vars requests reads, so the developer's shell can't change the outcome."""
    for var in ("REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"):
        monkeypatch.delenv(var, raising=False)
        monkeypatch.delenv(var.lower(), raising=False)


def _classic(auth, logger):
    return ClassicAPI(fqdn=FQDN, auth=auth, http_config=HTTPConfig(),
                      safe_mode=True, session=MagicMock(), logger=logger)


def _pro(auth, logger):
    return ProAPI(fqdn=FQDN, auth=auth, http_config=HTTPConfig(),
                  safe_mode=True, session=MagicMock(), logger=logger)


def test_classic_url_ignores_target(mock_auth, silent_logger):
    api = _classic(mock_auth, silent_logger)
    assert api.url() == f"{FQDN}/JSSResource"
    assert api.url("2") == f"{FQDN}/JSSResource"


def test_pro_url_formats_version(mock_auth, silent_logger):
    api = _pro(mock_auth, silent_logger)
    assert api.url("2") == f"{FQDN}/api/v2"
    assert api.url("1") == f"{FQDN}/api/v1"


def test_url_raises_on_unknown_version(mock_auth, silent_logger):
    api = _classic(mock_auth, silent_logger)
    api._version = "weird"
    with pytest.raises(JamfpyConfigError):
        api.url()


def test_header_returns_configured_set(mock_auth, silent_logger):
    api = _classic(mock_auth, silent_logger)
    assert api.header("read") == DEFAULT_HTTP_CONFIG_HEADERS["crud"]["read"]


def test_header_raises_on_bad_key(mock_auth, silent_logger):
    api = _classic(mock_auth, silent_logger)
    with pytest.raises(KeyError):
        api.header("does-not-exist")


def test_refresh_session_headers_sets_bearer(mock_auth, silent_logger):
    api = _classic(mock_auth, silent_logger)
    api._refresh_session_headers()
    api._session.headers.clear.assert_called_once()
    api._session.headers.update.assert_called_once_with({"Authorization": "Bearer tok"})


def test_do_prepares_and_sends(mock_auth, silent_logger):
    api = _classic(mock_auth, silent_logger)
    prepped = MagicMock()
    api._session.prepare_request.return_value = prepped
    sent_response = MagicMock(status_code=200, url=f"{FQDN}/x")
    api._session.send.return_value = sent_response

    result = api.do(Request("GET", url=f"{FQDN}/JSSResource/computers"))

    assert result is sent_response
    api._session.prepare_request.assert_called_once()
    api._session.send.assert_called_once()
    # Auth is refreshed before every send.
    mock_auth.token.assert_called()


def test_close_invalidates_and_marks_closed(mock_auth, silent_logger):
    api = _classic(mock_auth, silent_logger)
    mock_auth.invalidate.return_value = True
    api.close()
    mock_auth.invalidate.assert_called_once()
    assert api._is_closed is True


def test_close_warns_when_invalidation_fails(mock_auth, warning_logger, caplog):
    api = _classic(mock_auth, warning_logger)
    mock_auth.invalidate.return_value = False
    api.close()

    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(warnings) == 1
    assert warnings[0].levelno == logging.WARNING
    assert "Token invalidation failed" in warnings[0].getMessage()
    assert FQDN in warnings[0].getMessage()
    assert api._is_closed is True


def test_close_is_quiet_when_invalidation_succeeds(mock_auth, warning_logger, caplog):
    api = _classic(mock_auth, warning_logger)
    mock_auth.invalidate.return_value = True
    api.close()

    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


# --- TLS -------------------------------------------------------------------

def _classic_real_session(auth, logger, **kwargs):
    return ClassicAPI(fqdn=FQDN, auth=auth, http_config=HTTPConfig(),
                      safe_mode=True, session=None, logger=logger, **kwargs)


def test_default_session_verifies_tls(mock_auth, silent_logger):
    api = _classic_real_session(mock_auth, silent_logger)
    assert api._session.verify is True
    assert api._session.cert is None


def test_verify_and_cert_paths_land_on_session(mock_auth, silent_logger, tmp_path):
    ca_bundle = tmp_path / "ca.pem"
    client_cert = tmp_path / "client.pem"
    ca_bundle.write_text("ca")
    client_cert.write_text("cert")

    api = _classic_real_session(mock_auth, silent_logger,
                                verify_path=str(ca_bundle), cert_path=str(client_cert))

    assert api._session.verify == str(ca_bundle)
    assert api._session.cert == str(client_cert)


def test_caller_session_gets_tls_settings(mock_auth, silent_logger, tmp_path):
    ca_bundle = tmp_path / "ca.pem"
    client_cert = tmp_path / "client.pem"
    ca_bundle.write_text("ca")
    client_cert.write_text("cert")
    session = Session()

    api = ClassicAPI(fqdn=FQDN, auth=mock_auth, http_config=HTTPConfig(), safe_mode=True, session=session,
                     logger=silent_logger, verify_path=str(ca_bundle), cert_path=str(client_cert))

    assert api._session is session
    assert session.verify == str(ca_bundle)
    assert session.cert == str(client_cert)


def test_caller_session_with_verification_off_is_verified(mock_auth, silent_logger):
    session = Session()
    session.verify = False

    ClassicAPI(fqdn=FQDN, auth=mock_auth, http_config=HTTPConfig(), safe_mode=True, session=session,
               logger=silent_logger)

    assert session.verify is True


def _send_kwargs(api, **do_kwargs):
    """Run do() with Session.send patched out and return the kwargs send received."""
    with patch.object(Session, "send", return_value=make_response({})) as mock_send:
        api.do(Request("GET", url=f"{FQDN}/JSSResource/computers"), **do_kwargs)
    return mock_send.call_args.kwargs


@pytest.mark.usefixtures("clean_env")
@pytest.mark.parametrize("bundle_source", ["none", "env", "verify_path", "env and verify_path"])
def test_do_never_sends_unverified(mock_auth, silent_logger, tmp_path, monkeypatch, bundle_source):
    bundle = tmp_path / "ca.pem"
    bundle.write_text("ca")
    if "env" in bundle_source:
        monkeypatch.setenv("REQUESTS_CA_BUNDLE", str(bundle))
    verify_path = str(bundle) if "verify_path" in bundle_source else None

    kwargs = _send_kwargs(_classic_real_session(mock_auth, silent_logger, verify_path=verify_path))

    assert kwargs["verify"] is not None
    assert kwargs["verify"] is not False


@pytest.mark.usefixtures("clean_env")
def test_do_verifies_by_default(mock_auth, silent_logger):
    kwargs = _send_kwargs(_classic_real_session(mock_auth, silent_logger), timeout=7)

    assert kwargs["verify"] is True
    assert kwargs["cert"] is None
    assert kwargs["timeout"] == 7


@pytest.mark.usefixtures("clean_env")
@pytest.mark.parametrize("env_var", ["REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"])
def test_do_uses_env_ca_bundle(mock_auth, silent_logger, tmp_path, monkeypatch, env_var):
    env_bundle = tmp_path / "env-ca.pem"
    env_bundle.write_text("ca")
    monkeypatch.setenv(env_var, str(env_bundle))

    kwargs = _send_kwargs(_classic_real_session(mock_auth, silent_logger))

    assert kwargs["verify"] == str(env_bundle)


@pytest.mark.usefixtures("clean_env")
def test_do_explicit_verify_path_beats_env_ca_bundle(mock_auth, silent_logger, tmp_path, monkeypatch):
    env_bundle = tmp_path / "env-ca.pem"
    explicit_bundle = tmp_path / "ca.pem"
    env_bundle.write_text("env")
    explicit_bundle.write_text("explicit")
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", str(env_bundle))

    kwargs = _send_kwargs(_classic_real_session(mock_auth, silent_logger, verify_path=str(explicit_bundle)))

    assert kwargs["verify"] == str(explicit_bundle)


@pytest.mark.usefixtures("clean_env")
def test_do_uses_env_https_proxy(mock_auth, silent_logger, monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:3128")

    kwargs = _send_kwargs(_classic_real_session(mock_auth, silent_logger))

    assert kwargs["proxies"]["https"] == "http://proxy.example:3128"


@pytest.mark.usefixtures("clean_env")
def test_do_skips_env_proxy_when_no_proxy_covers_host(mock_auth, silent_logger, monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:3128")
    monkeypatch.setenv("NO_PROXY", ".jamfcloud.com")

    kwargs = _send_kwargs(_classic_real_session(mock_auth, silent_logger))

    assert kwargs["proxies"] == {}


@pytest.mark.usefixtures("clean_env")
def test_do_passes_cert_path_as_cert(mock_auth, silent_logger, tmp_path):
    client_cert = tmp_path / "client.pem"
    client_cert.write_text("cert")

    kwargs = _send_kwargs(_classic_real_session(mock_auth, silent_logger, cert_path=str(client_cert)))

    assert kwargs["cert"] == str(client_cert)


@pytest.mark.usefixtures("clean_env")
def test_do_reaches_adapter_with_verification_on(mock_auth, silent_logger):
    # The adapter is where verify=None turned into an unverified connection, so assert what reaches it.
    api = _classic_real_session(mock_auth, silent_logger)
    with patch.object(HTTPAdapter, "send", return_value=make_response({})) as mock_adapter_send:
        api.do(Request("GET", url=f"{FQDN}/JSSResource/computers"))

    kwargs = mock_adapter_send.call_args.kwargs
    assert kwargs["verify"] is True
    assert kwargs["cert"] is None
