"""Unit tests for jamfpy.client.auth (OAuth / BasicAuth / token lifecycle).

All four auth network calls (token, bearer token, keep-alive, invalidate) are
answered by ``responses`` registrations on the ``mocked_responses`` fixture, so the
real ``requests.request()`` call runs and nothing hits a tenant.
"""
# pylint: disable=missing-function-docstring,protected-access,redefined-outer-name,too-many-lines
import base64
import logging
import threading
from datetime import datetime, timezone
from importlib import metadata
from unittest.mock import patch
from urllib.parse import parse_qs

import pytest
from conftest import FQDN, THREADS, TOKEN_URL, register_oauth_token, register_slow_oauth_token, run_together

from jamfpy.client.auth import OAuth, BasicAuth
from jamfpy.client.constants import DEFAULT_HTTP_CONFIG_HEADERS
from jamfpy.client.exceptions import JamfAuthError

BEARER_URL = f"{FQDN}/api/v1/auth/token"
KEEP_ALIVE_URL = f"{FQDN}/api/v1/auth/keep-alive"
INVALIDATE_URL = f"{FQDN}/api/v1/auth/invalidate-token"


def _now():
    return datetime.now(timezone.utc).timestamp()


def _oauth(logger, **kwargs):
    return OAuth(fqdn=FQDN, client_id="cid", client_secret="secret", logger=logger, **kwargs)


def _basic(logger, **kwargs):
    kwargs.setdefault("token_exp_thold_mins", 20)
    kwargs.setdefault("username", "user")
    kwargs.setdefault("password", "pass")
    return BasicAuth(fqdn=FQDN, logger=logger, **kwargs)


def _jamf_timestamp(epoch):
    """Render an epoch the way Jamf's token endpoints do: millisecond precision, trailing Z."""
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _register_oauth(rsps, expires_in, token="abc"):
    return register_oauth_token(rsps, token=token, expires_in=expires_in)


def _register_bearer(rsps, url, lifetime_secs, token):
    """Answer a bearer token or keep-alive request with a token expiring ``lifetime_secs`` from now."""
    return rsps.post(url, json={"token": token, "expires": _jamf_timestamp(_now() + lifetime_secs)})


CLAMP_MESSAGE = "is not shorter than the token lifetime"


def _clamp_warnings(caplog):
    return [r for r in caplog.records if CLAMP_MESSAGE in r.getMessage()]


def _warnings_from(caplog, logger):
    return [r for r in caplog.records if r.name == logger.name and r.levelno >= logging.WARNING]


@pytest.fixture
def warning_logger():
    """A logger at WARNING that propagates, so caplog sees exactly what a WARNING-level user would."""
    logger = logging.getLogger("jamfpy-test-auth-warnings")
    logger.handlers.clear()
    logger.setLevel(logging.WARNING)
    logger.propagate = True
    return logger


# --- OAuth -----------------------------------------------------------------

def test_oauth_set_new_token_parses_token_and_expiry(silent_logger, mocked_responses):
    _register_oauth(mocked_responses, 3600)

    auth = _oauth(silent_logger)
    auth.set_new_token()

    assert auth._token_str == "abc"
    assert auth.token_expiry == pytest.approx(_now() + 3600, abs=5)

    req = mocked_responses.calls[-1].request
    assert req.method == "POST"
    assert req.url == TOKEN_URL
    assert parse_qs(req.body) == {
        "client_id": ["cid"],
        "client_secret": ["secret"],
        "grant_type": ["client_credentials"],
    }
    assert req.headers["Content-Type"] == "application/x-www-form-urlencoded"


def test_oauth_set_new_token_raises_on_error(silent_logger, mocked_responses):
    mocked_responses.post(TOKEN_URL, status=401, body="nope")
    auth = _oauth(silent_logger)
    with pytest.raises(JamfAuthError):
        auth.set_new_token()


def test_oauth_keep_alive_is_unsupported(silent_logger):
    auth = _oauth(silent_logger)
    with pytest.raises(JamfAuthError):
        auth._keep_alive_token()


# --- BasicAuth -------------------------------------------------------------

def test_basic_init_auth_builds_base64_token(silent_logger):
    auth = _basic(silent_logger, username="user", password="pass")
    assert auth.basic_auth_token == base64.b64encode(b"user:pass").decode()


def test_basic_uses_supplied_token_without_credentials(silent_logger):
    auth = _basic(silent_logger, username=None, password=None, basic_auth_token="pretoken")
    assert auth.basic_auth_token == "pretoken"


def test_basic_set_new_token_parses_response(silent_logger, mocked_responses):
    mocked_responses.post(BEARER_URL, json={"token": "t", "expires": "2035-01-01T00:00:00.000+0000"})

    auth = _basic(silent_logger)
    auth.set_new_token()

    assert auth._token_str == "t"
    assert auth.token_expiry > _now()

    req = mocked_responses.calls[-1].request
    assert req.method == "POST"
    assert req.url == BEARER_URL
    assert req.headers["Authorization"] == f"Basic {auth.basic_auth_token}"


def test_basic_set_new_token_raises_on_error(silent_logger, mocked_responses):
    mocked_responses.post(BEARER_URL, status=401)
    auth = _basic(silent_logger)
    with pytest.raises(JamfAuthError):
        auth.set_new_token()


def test_basic_keep_alive_token_updates_token(silent_logger, mocked_responses):
    mocked_responses.post(KEEP_ALIVE_URL, json={"token": "t2", "expires": "2035-01-01T00:00:00Z"})

    auth = _basic(silent_logger)
    auth._token_str = "old"  # keep-alive only runs once a token already exists
    auth._keep_alive_token()

    assert auth._token_str == "t2"
    assert auth.token_expiry > _now()
    req = mocked_responses.calls[-1].request
    assert req.url == KEEP_ALIVE_URL
    assert req.headers["Authorization"] == "Bearer old"


def test_basic_keep_alive_raises_on_error(silent_logger, mocked_responses):
    mocked_responses.post(KEEP_ALIVE_URL, status=401)
    auth = _basic(silent_logger)
    auth._token_str = "old"
    with pytest.raises(JamfAuthError):
        auth._keep_alive_token()


# --- token checks (pure, given token_expiry) -------------------------------

def test_check_token_is_expired_true_when_past(silent_logger):
    auth = _oauth(silent_logger)
    auth.token_expiry = _now() - 100
    assert auth.check_token_is_expired() is True


def test_check_token_is_expired_false_when_future(silent_logger):
    auth = _oauth(silent_logger)
    auth.token_expiry = _now() + 10_000
    assert auth.check_token_is_expired() is False


def test_check_token_in_buffer_true_when_close(silent_logger):
    auth = _oauth(silent_logger, token_exp_thold_mins=20)
    auth.token_expiry = _now() + 10 * 60  # 10 min out, inside a 20 min buffer
    assert auth.check_token_in_buffer() is True


def test_check_token_in_buffer_false_when_far(silent_logger):
    auth = _oauth(silent_logger, token_exp_thold_mins=20)
    auth.token_expiry = _now() + 60 * 60  # 60 min out, outside the buffer
    assert auth.check_token_in_buffer() is False


# --- check_token orchestration ---------------------------------------------

def test_check_token_refreshes_when_expired(silent_logger):
    auth = _oauth(silent_logger, token_exp_thold_mins=20)
    auth.token_expiry = _now() - 100

    def refresh():
        auth.token_expiry = _now() + 3600

    with patch.object(auth, "set_new_token", side_effect=refresh) as mock_set:
        auth.check_token()
    mock_set.assert_called_once()


def test_check_token_oauth_refetches_within_buffer(silent_logger):
    auth = _oauth(silent_logger, token_exp_thold_mins=20)
    auth.token_expiry = _now() + 10 * 60

    def refresh():
        auth.token_expiry = _now() + 3600

    with patch.object(auth, "set_new_token", side_effect=refresh) as mock_set:
        auth.check_token()
    mock_set.assert_called_once()


def test_check_token_bearer_keeps_alive_within_buffer(silent_logger):
    auth = _basic(silent_logger, token_exp_thold_mins=20)
    auth._token_str = "old"  # keep-alive extends an existing token
    auth.token_expiry = _now() + 10 * 60

    def refresh():
        auth.token_expiry = _now() + 3600

    with patch.object(auth, "_keep_alive_token", side_effect=refresh) as mock_keep:
        auth.check_token()
    mock_keep.assert_called_once()


def test_check_token_uses_refreshed_token_even_inside_buffer(silent_logger):
    auth = _oauth(silent_logger, token_exp_thold_mins=20)
    auth.token_expiry = _now() - 10
    # set_new_token is a no-op, so the token stays inside the buffer after refresh; it is used, not rejected.
    with patch.object(auth, "set_new_token") as mock_set:
        auth.check_token()
    mock_set.assert_called_once()


def test_token_returns_string_when_valid(silent_logger):
    auth = _oauth(silent_logger, token_exp_thold_mins=20)
    auth.token_expiry = _now() + 3600
    auth._token_str = "live-token"
    assert auth.token() == "live-token"


# --- lazy token ------------------------------------------------------------

def test_new_auth_holds_no_token_and_reads_as_expired(silent_logger):
    auth = _oauth(silent_logger)
    assert auth._token_str is None
    assert auth.token_expiry == 0.0
    assert auth.check_token_is_expired() is True


def test_oauth_token_fetches_on_first_call_only(silent_logger, mocked_responses):
    token = _register_oauth(mocked_responses, 3600)
    auth = _oauth(silent_logger)
    assert len(mocked_responses.calls) == 0

    assert auth.token() == "abc"
    assert auth.token() == "abc"
    assert token.call_count == 1


def test_basic_without_a_token_fetches_rather_than_keeping_alive(silent_logger, mocked_responses):
    bearer = _register_bearer(mocked_responses, BEARER_URL, 3600, "t1")
    auth = _basic(silent_logger)
    auth.token_expiry = _now() + 10 * 60  # inside the buffer, but there is no token to keep alive

    assert auth.token() == "t1"
    assert bearer.call_count == 1


def test_first_fetch_is_not_reported_as_an_expired_token(warning_logger, caplog, mocked_responses):
    _register_oauth(mocked_responses, 3600)
    _oauth(warning_logger).token()
    assert not _warnings_from(caplog, warning_logger)


def test_concurrent_first_token_calls_fetch_one_token(silent_logger, mocked_responses):
    token = register_slow_oauth_token(mocked_responses, "fresh-token")
    auth = _oauth(silent_logger)

    tokens = run_together(auth.token)

    assert token.call_count == 1
    assert tokens == ["fresh-token"] * THREADS


# --- every auth call: timeout, User-Agent, lock ----------------------------

AUTH_CALLS = ["oauth-token", "bearer-token", "keep-alive", "invalidate"]


def _auth_call(name, logger, rsps, **kwargs):
    """Register the URL one of the four auth calls posts to; return its Auth and a callable that makes the call."""
    match name:
        case "oauth-token":
            _register_oauth(rsps, 3600)
            auth = _oauth(logger, **kwargs)
            return auth, auth.set_new_token
        case "bearer-token":
            _register_bearer(rsps, BEARER_URL, 3600, "t")
            auth = _basic(logger, **kwargs)
            return auth, auth.set_new_token
        case "keep-alive":
            _register_bearer(rsps, KEEP_ALIVE_URL, 3600, "t2")
            auth = _basic(logger, **kwargs)
            auth._token_str = "old"
            return auth, auth._keep_alive_token
        case _:
            rsps.post(INVALIDATE_URL, status=204)
            auth = _oauth(logger, **kwargs)
            auth._token_str = "abc"
            return auth, auth.invalidate


@pytest.mark.parametrize("name", AUTH_CALLS)
def test_auth_call_uses_the_default_timeout(silent_logger, mocked_responses, name):
    _, make_call = _auth_call(name, silent_logger, mocked_responses)
    make_call()
    assert mocked_responses.calls[-1].request.req_kwargs["timeout"] == 30.0


@pytest.mark.parametrize("name", AUTH_CALLS)
def test_auth_call_uses_the_configured_timeout(silent_logger, mocked_responses, name):
    _, make_call = _auth_call(name, silent_logger, mocked_responses, timeout=(3.0, 27.0))
    make_call()
    assert mocked_responses.calls[-1].request.req_kwargs["timeout"] == (3.0, 27.0)


@pytest.mark.parametrize("name", AUTH_CALLS)
def test_auth_call_sends_the_jamfpy_user_agent(silent_logger, mocked_responses, name):
    _, make_call = _auth_call(name, silent_logger, mocked_responses)
    make_call()
    assert mocked_responses.calls[-1].request.headers["User-Agent"] == f"jamfpy/{metadata.version('jamfpy')}"


def test_oauth_token_call_leaves_the_configured_headers_alone(silent_logger, mocked_responses):
    _, make_call = _auth_call("oauth-token", silent_logger, mocked_responses)
    make_call()
    assert DEFAULT_HTTP_CONFIG_HEADERS["auth"]["oauth"] == {"Content-Type": "application/x-www-form-urlencoded"}


@pytest.mark.parametrize("name", AUTH_CALLS)
def test_auth_call_waits_for_the_token_lock(silent_logger, mocked_responses, name):
    auth, make_call = _auth_call(name, silent_logger, mocked_responses)
    caller = threading.Thread(target=make_call)

    with auth._lock:
        caller.start()
        caller.join(timeout=0.2)
        # Blocked on the lock this thread holds, so nothing has gone out yet.
        assert caller.is_alive()
        assert len(mocked_responses.calls) == 0

    caller.join(timeout=10)
    assert not caller.is_alive()
    assert len(mocked_responses.calls) == 1


# --- invalidate ------------------------------------------------------------

def test_invalidate_returns_true_on_ok(silent_logger, mocked_responses):
    mocked_responses.post(INVALIDATE_URL, status=204)
    auth = _oauth(silent_logger)
    auth._token_str = "abc"
    assert auth.invalidate() is True


def test_invalidate_posts_to_full_tenant_url(silent_logger, mocked_responses):
    mocked_responses.post(INVALIDATE_URL, status=204)
    auth = _oauth(silent_logger)
    auth._token_str = "abc"
    auth.invalidate()

    req = mocked_responses.calls[-1].request
    assert req.method == "POST"
    assert req.url == "https://test.jamfcloud.com/api/v1/auth/invalidate-token"
    assert req.headers["Authorization"] == "Bearer abc"


def test_invalidate_returns_false_on_error(silent_logger, mocked_responses):
    mocked_responses.post(INVALIDATE_URL, status=401)
    auth = _oauth(silent_logger)
    auth._token_str = "abc"
    assert auth.invalidate() is False


def test_invalidate_without_a_token_sends_nothing(warning_logger, caplog, mocked_responses):
    auth = _oauth(warning_logger)

    with caplog.at_level(logging.DEBUG, logger=warning_logger.name):
        assert auth.invalidate() is True

    assert len(mocked_responses.calls) == 0
    messages = [(r.levelno, r.getMessage()) for r in caplog.records if r.name == warning_logger.name]
    assert (logging.DEBUG, "No token to invalidate") in messages


# --- Jamf expiry parsing -----------------------------------------------------

# Real Jamf token timestamps vary the fractional digits; each must parse to the exact UTC epoch.
JAMF_EXPIRIES = [
    ("2026-10-15T14:34:41.571Z", 1792074881.571),
    ("2026-10-15T14:34:41.5Z", 1792074881.5),
    ("2026-10-15T14:34:41.571234Z", 1792074881.571234),
]


@pytest.mark.parametrize("expires, epoch", JAMF_EXPIRIES)
def test_basic_set_new_token_parses_jamf_expiry(silent_logger, mocked_responses, expires, epoch):
    mocked_responses.post(BEARER_URL, json={"token": "t", "expires": expires})

    auth = _basic(silent_logger)
    auth.set_new_token()

    assert auth.token_expiry == epoch


@pytest.mark.parametrize("expires, epoch", JAMF_EXPIRIES)
def test_basic_keep_alive_parses_jamf_expiry(silent_logger, mocked_responses, expires, epoch):
    mocked_responses.post(KEEP_ALIVE_URL, json={"token": "t2", "expires": expires})

    auth = _basic(silent_logger)
    auth._token_str = "old"
    auth._keep_alive_token()

    assert auth.token_expiry == epoch


# --- buffer clamp for short-lived tokens -----------------------------------
# The dev tenant's API client issues 299 s tokens against a 20 min default buffer.

def test_short_lived_oauth_token_is_used_with_default_buffer(silent_logger, mocked_responses):
    token = _register_oauth(mocked_responses, 299)
    auth = _oauth(silent_logger)
    auth.set_new_token()  # what Tenant.authenticate() does
    assert auth.token() == "abc"

    assert token.call_count == 1


def test_short_lived_oauth_token_is_not_refetched_straight_after(silent_logger, mocked_responses):
    token = _register_oauth(mocked_responses, 299)
    auth = _oauth(silent_logger)
    auth.set_new_token()
    auth.token()
    auth.token()

    assert token.call_count == 1


def test_short_lived_oauth_token_refetched_inside_half_lifetime(silent_logger, mocked_responses):
    token = _register_oauth(mocked_responses, 299)
    auth = _oauth(silent_logger)
    auth.set_new_token()

    auth.token_expiry = _now() + 160  # just outside the 149.5 s clamped buffer
    auth.token()
    assert token.call_count == 1

    auth.token_expiry = _now() + 140  # inside it
    auth.token()
    assert token.call_count == 2


def test_buffer_clamp_warns_once_per_auth(warning_logger, caplog, mocked_responses):
    _register_oauth(mocked_responses, 299)
    auth = _oauth(warning_logger)
    auth.set_new_token()
    for _ in range(3):
        auth.token()
    auth.token_expiry = _now() + 100
    auth.token()  # refetches, recording the lifetime again

    warnings = _clamp_warnings(caplog)
    assert len(warnings) == 1
    assert warnings[0].levelno == logging.WARNING
    assert "20 min" in warnings[0].getMessage()
    assert "lifetime of 299 s" in warnings[0].getMessage()
    assert "150 s buffer" in warnings[0].getMessage()


def test_buffer_clamp_below_lifetime_is_silent(warning_logger, caplog, mocked_responses):
    # 1800 s token: the 1200 s buffer is clamped to 900 s, but it is shorter than the lifetime, so no warning.
    token = _register_oauth(mocked_responses, 1800)
    auth = _oauth(warning_logger)
    auth.set_new_token()
    assert auth.token() == "abc"

    assert token.call_count == 1
    assert auth._buffer_secs() == 900
    assert not _warnings_from(caplog, warning_logger)


def test_buffer_clamp_warns_once_for_each_auth(warning_logger, caplog, mocked_responses):
    _register_oauth(mocked_responses, 299)
    for _ in range(2):
        auth = _oauth(warning_logger)
        auth.set_new_token()
        auth.token_expiry = _now() + 100
        auth.token()  # refetches, recording the lifetime again

    assert len(_clamp_warnings(caplog)) == 2


@pytest.mark.parametrize("lifetime_secs", [0, -30])
def test_non_positive_token_lifetime_gives_zero_buffer(warning_logger, caplog, mocked_responses, lifetime_secs):
    _register_oauth(mocked_responses, lifetime_secs)
    auth = _oauth(warning_logger)
    auth.set_new_token()

    assert auth._buffer_secs() == 0
    warnings = _clamp_warnings(caplog)
    assert len(warnings) == 1
    assert "0 s buffer" in warnings[0].getMessage()


def test_long_lived_oauth_token_keeps_configured_buffer(warning_logger, caplog, mocked_responses):
    # Long-lived means at least twice the 20 min buffer; a 30 min token would already clamp to 15 min.
    token = _register_oauth(mocked_responses, 3600)
    auth = _oauth(warning_logger)
    auth.set_new_token()
    auth.token()
    assert token.call_count == 1
    assert auth._buffer_secs() == 20 * 60

    auth.token_expiry = _now() + 21 * 60
    auth.token()
    assert token.call_count == 1

    auth.token_expiry = _now() + 19 * 60
    auth.token()
    assert token.call_count == 2

    assert not _clamp_warnings(caplog)


def test_short_lived_bearer_token_keeps_alive_inside_half_lifetime(warning_logger, caplog, mocked_responses):
    _register_bearer(mocked_responses, BEARER_URL, 299, "t1")
    _register_bearer(mocked_responses, KEEP_ALIVE_URL, 299, "t2")
    auth = _basic(warning_logger)  # default 20 min buffer
    auth.set_new_token()
    assert auth.token() == "t1"
    assert auth.token() == "t1"
    assert len(mocked_responses.calls) == 1

    auth.token_expiry = _now() + 100  # inside the ~149 s clamped buffer
    assert auth.token() == "t2"
    assert auth.token() == "t2"

    assert len(mocked_responses.calls) == 2
    keep_alive = mocked_responses.calls[-1].request
    assert keep_alive.url == KEEP_ALIVE_URL
    assert keep_alive.headers["Authorization"] == "Bearer t1"
    assert len(_clamp_warnings(caplog)) == 1


def test_long_lived_bearer_token_keeps_configured_buffer(warning_logger, caplog, mocked_responses):
    _register_bearer(mocked_responses, BEARER_URL, 3600, "t1")
    _register_bearer(mocked_responses, KEEP_ALIVE_URL, 3600, "t2")
    auth = _basic(warning_logger)
    auth.set_new_token()
    assert auth.token() == "t1"

    auth.token_expiry = _now() + 21 * 60
    assert auth.token() == "t1"

    auth.token_expiry = _now() + 19 * 60
    assert auth.token() == "t2"

    assert len(mocked_responses.calls) == 2
    assert mocked_responses.calls[-1].request.url == KEEP_ALIVE_URL
    assert not _clamp_warnings(caplog)
