"""Unit tests for the API base behaviour via ClassicAPI / ProAPI.

Most tests use the real ``classic_api`` / ``pro_api`` from the ``tenant`` fixture, so
``API.do()`` runs against the real ``Auth`` and ``responses`` answers the wire. The TLS
tests that assert the keyword arguments reaching the adapter (``verify``, ``cert``,
``proxies``, ``timeout``) patch ``HTTPAdapter.send`` directly instead, with a stub Auth and
no ``responses`` mock: the adapter is where ``verify=None`` used to become an unverified
connection, so they pin exactly what it is called with.
"""
# pylint: disable=missing-function-docstring,protected-access,redefined-outer-name
import logging
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from requests import Request, Response, Session
from requests.adapters import HTTPAdapter
from conftest import FAKE_TOKEN, FQDN, TOKEN_URL, register_oauth_token, sent_headers

from jamfpy.client.client import ClassicAPI
from jamfpy.client.http_config import HTTPConfig
from jamfpy.client.constants import DEFAULT_HTTP_CONFIG_HEADERS
from jamfpy.client.exceptions import JamfpyConfigError

COMPUTERS_URL = f"{FQDN}/JSSResource/computers"
INVALIDATE_URL = f"{FQDN}/api/v1/auth/invalidate-token"


@pytest.fixture
def mock_auth():
    """Stub Auth for the adapter-patched TLS tests, which run without a ``responses`` mock."""
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


def _classic_real_session(auth, logger, **kwargs):
    return ClassicAPI(fqdn=FQDN, auth=auth, http_config=HTTPConfig(),
                      safe_mode=True, session=None, logger=logger, **kwargs)


def test_classic_url_ignores_target(classic_api):
    assert classic_api.url() == f"{FQDN}/JSSResource"
    assert classic_api.url("2") == f"{FQDN}/JSSResource"


def test_pro_url_formats_version(pro_api):
    assert pro_api.url("2") == f"{FQDN}/api/v2"
    assert pro_api.url("1") == f"{FQDN}/api/v1"


def test_url_raises_on_unknown_version(classic_api):
    classic_api._version = "weird"
    with pytest.raises(JamfpyConfigError):
        classic_api.url()


def test_header_returns_configured_set(classic_api):
    assert classic_api.header("read") == DEFAULT_HTTP_CONFIG_HEADERS["crud"]["read"]


def test_header_raises_on_bad_key(classic_api):
    with pytest.raises(KeyError):
        classic_api.header("does-not-exist")


def test_refresh_session_headers_sets_bearer(classic_api):
    classic_api._session.headers["X-Stale"] = "1"
    classic_api._refresh_session_headers()
    # Cleared, then only the Bearer header from the real Auth.
    assert dict(classic_api._session.headers) == {"Authorization": f"Bearer {FAKE_TOKEN}"}


def test_do_prepares_and_sends(classic_api, mocked_responses):
    mocked_responses.get(COMPUTERS_URL, json={"computers": []})

    result = classic_api.do(Request("GET", url=COMPUTERS_URL, headers={"accept": "application/json"}))

    assert result.status_code == 200
    assert result.json() == {"computers": []}
    assert len(mocked_responses.calls) == 1
    req = mocked_responses.calls[-1].request
    assert req.method == "GET"
    assert req.url == COMPUTERS_URL
    # Auth is applied before every send.
    assert req.headers["Authorization"] == f"Bearer {FAKE_TOKEN}"
    assert req.headers["accept"] == "application/json"


def test_do_drops_the_session_default_headers(classic_api, mocked_responses):
    # Characterises current behaviour: _refresh_session_headers clears the session's requests defaults, so a request
    # goes out with no User-Agent, Accept-Encoding, Accept or Connection header unless the endpoint sets one.
    mocked_responses.get(COMPUTERS_URL, json={})
    classic_api.do(Request("GET", url=COMPUTERS_URL))
    assert sent_headers(mocked_responses.calls[-1].request) == {"Authorization": f"Bearer {FAKE_TOKEN}"}


def test_do_fetches_a_new_token_when_expired(classic_api, mocked_responses):
    token = register_oauth_token(mocked_responses, token="fresh-token")
    mocked_responses.get(COMPUTERS_URL, json={"computers": []})
    classic_api.auth.token_expiry = datetime.now(timezone.utc).timestamp() - 1

    classic_api.do(Request("GET", url=COMPUTERS_URL))

    assert token.call_count == 1
    assert [call.request.url for call in mocked_responses.calls] == [TOKEN_URL, COMPUTERS_URL]
    assert mocked_responses.calls[-1].request.headers["Authorization"] == "Bearer fresh-token"


def test_close_invalidates_and_marks_closed(classic_api, mocked_responses):
    mocked_responses.post(INVALIDATE_URL, status=204)
    classic_api.close()

    req = mocked_responses.calls[-1].request
    assert req.method == "POST"
    assert req.url == INVALIDATE_URL
    assert req.headers["Authorization"] == f"Bearer {FAKE_TOKEN}"
    assert classic_api._is_closed is True


def test_close_warns_when_invalidation_fails(classic_api, mocked_responses, warning_logger, caplog):
    api = _classic_real_session(classic_api.auth, warning_logger)
    mocked_responses.post(INVALIDATE_URL, status=401)
    api.close()

    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(warnings) == 1
    assert warnings[0].levelno == logging.WARNING
    assert "Token invalidation failed" in warnings[0].getMessage()
    assert FQDN in warnings[0].getMessage()
    assert api._is_closed is True


def test_close_is_quiet_when_invalidation_succeeds(classic_api, mocked_responses, warning_logger, caplog):
    api = _classic_real_session(classic_api.auth, warning_logger)
    mocked_responses.post(INVALIDATE_URL, status=204)
    api.close()

    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


# --- TLS -------------------------------------------------------------------

def test_default_session_verifies_tls(classic_api):
    assert classic_api._session.verify is True
    assert classic_api._session.cert is None


def test_verify_and_cert_paths_land_on_session(classic_api, silent_logger, tmp_path):
    ca_bundle = tmp_path / "ca.pem"
    client_cert = tmp_path / "client.pem"
    ca_bundle.write_text("ca")
    client_cert.write_text("cert")

    api = _classic_real_session(classic_api.auth, silent_logger,
                                verify_path=str(ca_bundle), cert_path=str(client_cert))

    assert api._session.verify == str(ca_bundle)
    assert api._session.cert == str(client_cert)


def test_caller_session_gets_tls_settings(classic_api, silent_logger, tmp_path):
    ca_bundle = tmp_path / "ca.pem"
    client_cert = tmp_path / "client.pem"
    ca_bundle.write_text("ca")
    client_cert.write_text("cert")
    session = Session()

    api = ClassicAPI(fqdn=FQDN, auth=classic_api.auth, http_config=HTTPConfig(), safe_mode=True, session=session,
                     logger=silent_logger, verify_path=str(ca_bundle), cert_path=str(client_cert))

    assert api._session is session
    assert session.verify == str(ca_bundle)
    assert session.cert == str(client_cert)


def test_caller_session_with_verification_off_is_verified(classic_api, silent_logger):
    session = Session()
    session.verify = False

    ClassicAPI(fqdn=FQDN, auth=classic_api.auth, http_config=HTTPConfig(), safe_mode=True, session=session,
               logger=silent_logger)

    assert session.verify is True


def _ok_response():
    resp = Response()
    resp.status_code = 200
    return resp


def _send_kwargs(api, **do_kwargs):
    """Run do() with HTTPAdapter.send patched out and return the kwargs the adapter received."""
    with patch.object(HTTPAdapter, "send", return_value=_ok_response()) as mock_adapter_send:
        api.do(Request("GET", url=COMPUTERS_URL), **do_kwargs)
    return mock_adapter_send.call_args.kwargs


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
def test_do_times_out_after_ten_seconds_by_default(mock_auth, silent_logger):
    kwargs = _send_kwargs(_classic_real_session(mock_auth, silent_logger))

    assert kwargs["timeout"] == 10


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
    with patch.object(HTTPAdapter, "send", return_value=_ok_response()) as mock_adapter_send:
        api.do(Request("GET", url=COMPUTERS_URL))

    kwargs = mock_adapter_send.call_args.kwargs
    assert kwargs["verify"] is True
    assert kwargs["cert"] is None
