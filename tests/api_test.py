"""Unit tests for the API base behaviour via ClassicAPI / ProAPI.

Most tests use the real ``classic_api`` / ``pro_api`` from the ``tenant`` fixture, so
``API.do()`` runs against the real ``Auth`` and ``responses`` answers the wire. The TLS
tests that assert the keyword arguments reaching the adapter (``verify``, ``cert``,
``proxies``, ``timeout``) patch ``HTTPAdapter.send`` directly instead, with a stub Auth and
no ``responses`` mock: the adapter is where ``verify=None`` used to become an unverified
connection, so they pin exactly what it is called with.

The concurrency tests run ``do()`` from ``THREADS`` threads released together by a barrier
(``run_together``); the token endpoint answers slowly, so without the ``Auth`` lock several
threads would refresh.
"""
# pylint: disable=missing-function-docstring,protected-access,redefined-outer-name,too-many-lines
import json
import logging
from datetime import datetime, timezone
from importlib import metadata
from unittest.mock import MagicMock, patch

import pytest
from requests import Request, Response, Session
from requests.adapters import HTTPAdapter
from requests.exceptions import ConnectTimeout
from conftest import (
    FAKE_TOKEN, FQDN, THREADS, TOKEN_URL, register_oauth_token, register_slow_oauth_token, run_together, sent_headers,
    with_bearer,
)

from jamfpy.client.client import ClassicAPI
from jamfpy.client.http_config import HTTPConfig
from jamfpy.client.constants import DEFAULT_HTTP_CONFIG_HEADERS
from jamfpy.client.exceptions import JamfpyConfigError
from jamfpy.client.retry import RetryConfig

COMPUTERS_URL = f"{FQDN}/JSSResource/computers"
INVALIDATE_URL = f"{FQDN}/api/v1/auth/invalidate-token"
CLASSIC_LOGGER = "jamfpy.test-clc"


@pytest.fixture
def mock_auth():
    """Stub Auth for the adapter-patched TLS tests, which run without a ``responses`` mock."""
    auth = MagicMock()
    auth.token.return_value = "tok"
    return auth


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


def test_do_sends_requests_defaults_with_the_jamfpy_user_agent(classic_api, mocked_responses):
    mocked_responses.get(COMPUTERS_URL, json={})
    classic_api.do(Request("GET", url=COMPUTERS_URL))

    req = mocked_responses.calls[-1].request
    assert req.headers["User-Agent"] == f"jamfpy/{metadata.version('jamfpy')}"
    # The session keeps requests' Accept-Encoding, Accept and Connection defaults alongside it.
    assert sent_headers(req) == with_bearer({})


def test_endpoint_accept_wins_over_the_session_default(classic_api, mocked_responses):
    mocked_responses.get(COMPUTERS_URL, body="<computers/>")
    classic_api.do(Request("GET", url=COMPUTERS_URL, headers={"accept": "text/xml"}))

    req = mocked_responses.calls[-1].request
    assert req.headers["Accept"] == "text/xml"
    assert [name for name in req.headers if name.lower() == "accept"] == ["accept"]


def test_user_agent_falls_back_when_jamfpy_is_not_installed(classic_api, mocked_responses, silent_logger):
    with patch("importlib.metadata.version", side_effect=metadata.PackageNotFoundError("jamfpy")):
        api = _classic_real_session(classic_api.auth, silent_logger)
    mocked_responses.get(COMPUTERS_URL, json={})

    api.do(Request("GET", url=COMPUTERS_URL))

    assert mocked_responses.calls[-1].request.headers["User-Agent"] == "jamfpy/unknown"


def test_do_puts_authorization_on_the_request_not_the_session(classic_api, mocked_responses):
    mocked_responses.get(COMPUTERS_URL, json={})
    endpoint_headers = {"accept": "application/json"}

    classic_api.do(Request("GET", url=COMPUTERS_URL, headers=endpoint_headers))

    assert mocked_responses.calls[-1].request.headers["Authorization"] == f"Bearer {FAKE_TOKEN}"
    assert "Authorization" not in classic_api._session.headers
    # The endpoint's dict is the shared config header set in real code; the token must not land in it.
    assert endpoint_headers == {"accept": "application/json"}


def test_do_authorization_beats_a_session_default(classic_api, mocked_responses):
    classic_api._session.headers["Authorization"] = "Bearer stale"
    mocked_responses.get(COMPUTERS_URL, json={})

    classic_api.do(Request("GET", url=COMPUTERS_URL))

    assert mocked_responses.calls[-1].request.headers["Authorization"] == f"Bearer {FAKE_TOKEN}"


def test_do_uses_the_configured_timeout(classic_api, mocked_responses):
    mocked_responses.get(COMPUTERS_URL, json={})
    classic_api.do(Request("GET", url=COMPUTERS_URL))
    assert mocked_responses.calls[-1].request.req_kwargs["timeout"] == 30.0


def test_do_timeout_overrides_for_that_call_only(classic_api, mocked_responses):
    mocked_responses.get(COMPUTERS_URL, json={})

    classic_api.do(Request("GET", url=COMPUTERS_URL), timeout=7)
    classic_api.do(Request("GET", url=COMPUTERS_URL))

    assert [call.request.req_kwargs["timeout"] for call in mocked_responses.calls] == [7, 30.0]


def test_api_timeout_keyword_sets_the_default(classic_api, mocked_responses, silent_logger):
    api = _classic_real_session(classic_api.auth, silent_logger, timeout=(3.0, 27.0))
    mocked_responses.get(COMPUTERS_URL, json={})

    api.do(Request("GET", url=COMPUTERS_URL))

    assert mocked_responses.calls[-1].request.req_kwargs["timeout"] == (3.0, 27.0)


# --- concurrency -----------------------------------------------------------

def test_concurrent_do_with_an_expired_token_fetches_it_once(classic_api, mocked_responses):
    token = register_slow_oauth_token(mocked_responses, "fresh-token")
    computers = mocked_responses.get(COMPUTERS_URL, json={})
    classic_api.auth.token_expiry = 0.0

    run_together(lambda: classic_api.do(Request("GET", url=COMPUTERS_URL)))

    assert token.call_count == 1
    assert computers.call_count == THREADS
    assert {call.request.headers["Authorization"] for call in computers.calls} == {"Bearer fresh-token"}


def test_concurrent_do_keeps_authorization_off_the_session(classic_api, mocked_responses):
    computers = mocked_responses.get(COMPUTERS_URL, json={})
    assert "Authorization" not in classic_api._session.headers

    run_together(lambda: classic_api.do(Request("GET", url=COMPUTERS_URL, headers={"accept": "application/json"})))

    assert computers.call_count == THREADS
    for call in computers.calls:
        assert call.request.headers["Authorization"] == f"Bearer {FAKE_TOKEN}"
        assert call.request.headers["accept"] == "application/json"
    assert "Authorization" not in classic_api._session.headers


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
    assert session.headers["User-Agent"] == f"jamfpy/{metadata.version('jamfpy')}"


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
def test_do_times_out_after_thirty_seconds_by_default(mock_auth, silent_logger):
    kwargs = _send_kwargs(_classic_real_session(mock_auth, silent_logger))

    assert kwargs["timeout"] == 30.0


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


# --- logging ---------------------------------------------------------------

def _records(caplog, name=CLASSIC_LOGGER, level=None):
    return [r for r in caplog.records if r.name == name and (level is None or r.levelno == level)]


def _debug_lines(caplog, name=CLASSIC_LOGGER):
    """The DEBUG request and response lines, keyed by their first word."""
    return {r.getMessage().split(" ", 1)[0]: r.getMessage() for r in _records(caplog, name, logging.DEBUG)}


def test_api_logs_through_its_jamfpy_child_logger(classic_api, pro_api):
    assert classic_api._logger is logging.getLogger("jamfpy.test-clc")
    assert pro_api._logger is logging.getLogger("jamfpy.test-pro")


def test_a_caller_logger_is_used_as_is(make_classic_api):
    mine = logging.getLogger("my-app.jamf")
    mine.setLevel(logging.WARNING)

    api = make_classic_api(logger=mine, log_level=logging.DEBUG)

    assert api._logger is mine
    assert mine.level == logging.WARNING


def test_one_info_line_per_attempt_with_the_fields(classic_api, mocked_responses, caplog):
    caplog.set_level(logging.INFO, logger=CLASSIC_LOGGER)
    mocked_responses.get(COMPUTERS_URL, json={"computers": []})

    classic_api.do(Request("GET", url=COMPUTERS_URL))

    [record] = _records(caplog, level=logging.INFO)
    assert (record.method, record.url, record.status, record.attempt) == ("GET", COMPUTERS_URL, 200, 1)
    assert isinstance(record.duration_ms, int)
    assert record.duration_ms >= 0
    assert record.getMessage() == f"GET {COMPUTERS_URL} -> 200 ({record.duration_ms} ms)"


def test_a_clean_request_logs_nothing_above_info(classic_api, mocked_responses, caplog):
    caplog.set_level(logging.DEBUG, logger=CLASSIC_LOGGER)
    mocked_responses.get(COMPUTERS_URL, json={})

    classic_api.do(Request("GET", url=COMPUTERS_URL))

    assert _records(caplog)
    assert max(r.levelno for r in _records(caplog)) == logging.INFO


def test_info_line_names_the_attempt_from_the_first_retry_on(make_classic_api, mocked_responses, caplog):
    mocked_responses.get(COMPUTERS_URL, status=503)
    mocked_responses.get(COMPUTERS_URL, json={})
    api = make_classic_api(logger=None, log_level=logging.INFO, retries=RetryConfig(jitter=False))

    api.do(Request("GET", url=COMPUTERS_URL))

    first, second = _records(caplog, level=logging.INFO)
    assert first.getMessage() == f"GET {COMPUTERS_URL} -> 503 ({first.duration_ms} ms)"
    assert second.getMessage() == f"GET {COMPUTERS_URL} -> 200 ({second.duration_ms} ms, attempt 2)"
    assert (first.status, first.attempt, second.status, second.attempt) == (503, 1, 200, 2)


def test_info_line_for_a_send_that_raised_names_the_exception(make_classic_api, mocked_responses, caplog):
    mocked_responses.get(COMPUTERS_URL, body=ConnectTimeout("connect timed out"))
    api = make_classic_api(logger=None, log_level=logging.INFO, retries=None)

    with pytest.raises(ConnectTimeout):
        api.do(Request("GET", url=COMPUTERS_URL))

    [record] = _records(caplog, level=logging.INFO)
    assert record.getMessage() == f"GET {COMPUTERS_URL} -> ConnectTimeout ({record.duration_ms} ms)"
    assert not hasattr(record, "status")
    assert record.attempt == 1


def test_warning_and_error_records_carry_the_fields(make_classic_api, mocked_responses, caplog):
    mocked_responses.get(COMPUTERS_URL, status=503)
    api = make_classic_api(logger=None, log_level=logging.INFO, retries=RetryConfig(total=2, jitter=False))

    api.do(Request("GET", url=COMPUTERS_URL))

    warnings = _records(caplog, level=logging.WARNING)
    [error] = _records(caplog, level=logging.ERROR)
    assert [r.attempt for r in warnings] == [1, 2]
    assert error.attempt == 3
    for record in [*warnings, error]:
        assert (record.method, record.url, record.status) == ("GET", COMPUTERS_URL, 503)
        assert isinstance(record.duration_ms, int)


def test_debug_logs_headers_and_bodies_with_authorization_redacted(classic_api, mocked_responses, caplog):
    caplog.set_level(logging.DEBUG, logger=CLASSIC_LOGGER)
    mocked_responses.post(COMPUTERS_URL, body="<computer><id>1</id></computer>", headers={"X-Trace": "abc"})

    classic_api.do(Request("POST", url=COMPUTERS_URL, data="<computer/>", headers={"content-type": "text/xml"}))

    lines = _debug_lines(caplog)
    assert lines["Request"].startswith(f"Request POST {COMPUTERS_URL} (attempt 1): headers={{")
    assert '"Authorization": "Bearer [redacted]"' in lines["Request"]
    assert '"content-type": "text/xml"' in lines["Request"]
    assert lines["Request"].endswith(" body=<computer/>")
    assert lines["Response"].startswith(f"Response POST {COMPUTERS_URL} -> 200 (attempt 1): headers={{")
    assert '"X-Trace": "abc"' in lines["Response"]
    assert lines["Response"].endswith(" body=<computer><id>1</id></computer>")
    assert not [r for r in caplog.records if FAKE_TOKEN in r.getMessage()]


def test_debug_records_carry_the_fields(classic_api, mocked_responses, caplog):
    caplog.set_level(logging.DEBUG, logger=CLASSIC_LOGGER)
    mocked_responses.get(COMPUTERS_URL, json={})

    classic_api.do(Request("GET", url=COMPUTERS_URL))

    request_line, response_line = _records(caplog, level=logging.DEBUG)
    assert (request_line.method, request_line.url, request_line.attempt) == ("GET", COMPUTERS_URL, 1)
    assert not hasattr(request_line, "status")
    assert (response_line.status, response_line.attempt) == (200, 1)
    assert isinstance(response_line.duration_ms, int)


def test_debug_truncates_long_bodies_at_1024_characters(classic_api, mocked_responses, caplog):
    caplog.set_level(logging.DEBUG, logger=CLASSIC_LOGGER)
    response_body = {"data": "y" * 3000}
    mocked_responses.post(COMPUTERS_URL, json=response_body)

    classic_api.do(Request("POST", url=COMPUTERS_URL, data="x" * 2000))

    lines = _debug_lines(caplog)
    assert lines["Request"].endswith(" body=" + "x" * 1024 + "… (truncated, 2000 chars)")
    # Redacted (so re-serialised) before it is cut: the count is the redacted text's length.
    rendered = json.dumps(response_body)
    assert lines["Response"].endswith(f" body={rendered[:1024]}… (truncated, {len(rendered)} chars)")


def test_debug_redacts_secrets_in_a_json_body(pro_api, mocked_responses, caplog):
    caplog.set_level(logging.DEBUG, logger="jamfpy.test-pro")
    url = f"{FQDN}/api/v2/mdm/commands"
    mocked_responses.post(url, json={"id": "1", "token": "server-issued"})

    pro_api.do(Request("POST", url=url, json={"commandData": {"commandType": "SET_RECOVERY_LOCK", "password": "hunter2"}}))

    lines = _debug_lines(caplog, "jamfpy.test-pro")
    assert '"password": "[redacted]"' in lines["Request"]
    assert '"commandType": "SET_RECOVERY_LOCK"' in lines["Request"]
    assert lines["Response"].endswith(' body={"id": "1", "token": "[redacted]"}')
    assert not [r for r in caplog.records if "hunter2" in r.getMessage() or "server-issued" in r.getMessage()]


def test_safe_mode_off_logs_the_raw_authorization_and_body(make_classic_api, mocked_responses, caplog):
    mocked_responses.post(COMPUTERS_URL, body="ok")
    api = make_classic_api(logger=None, log_level=logging.DEBUG, safe_mode=False)

    api.do(Request("POST", url=COMPUTERS_URL, data="password=hunter2"))

    lines = _debug_lines(caplog)
    assert f'"Authorization": "Bearer {FAKE_TOKEN}"' in lines["Request"]
    assert lines["Request"].endswith(" body=password=hunter2")


def test_debug_rendering_is_skipped_unless_debug_is_on(classic_api, mocked_responses, caplog):
    caplog.set_level(logging.INFO, logger=CLASSIC_LOGGER)
    mocked_responses.get(COMPUTERS_URL, json={})

    # Redacting and serialising a large body for a line nobody will see would be wasted work on every request.
    with patch("jamfpy.client.api.render_body", side_effect=AssertionError("rendered at INFO")), \
            patch("jamfpy.client.api.render_headers", side_effect=AssertionError("rendered at INFO")):
        classic_api.do(Request("GET", url=COMPUTERS_URL))

    assert len(_records(caplog, level=logging.INFO)) == 1
