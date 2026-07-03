"""Unit tests for jamfpy.client.auth (OAuth / BasicAuth / token lifecycle).

All four auth network calls go through the module-level ``requests.request``
imported as ``jamfpy.client.auth.request`` — patched here so nothing hits a tenant.
"""
# pylint: disable=missing-function-docstring,protected-access
import base64
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest
from conftest import FQDN

from jamfpy.client.auth import OAuth, BasicAuth
from jamfpy.client.exceptions import JamfAuthError


def _now():
    return datetime.now(timezone.utc).timestamp()


def _oauth(logger, **kwargs):
    return OAuth(fqdn=FQDN, client_id="cid", client_secret="secret", logger=logger, **kwargs)


def _basic(logger, **kwargs):
    kwargs.setdefault("token_exp_thold_mins", 20)
    kwargs.setdefault("username", "user")
    kwargs.setdefault("password", "pass")
    return BasicAuth(fqdn=FQDN, logger=logger, **kwargs)


# --- OAuth -----------------------------------------------------------------

def test_oauth_set_new_token_parses_token_and_expiry(silent_logger):
    with patch("jamfpy.client.auth.request") as mock_req:
        resp = MagicMock(ok=True)
        resp.json.return_value = {"access_token": "abc", "expires_in": 3600}
        mock_req.return_value = resp

        auth = _oauth(silent_logger)
        auth.set_new_token()

    assert auth._token_str == "abc"
    assert auth.token_expiry == pytest.approx(_now() + 3600, abs=5)

    kwargs = mock_req.call_args.kwargs
    assert kwargs["method"] == "POST"
    assert kwargs["url"] == f"{FQDN}/api/oauth/token"
    assert kwargs["data"] == {
        "client_id": "cid",
        "client_secret": "secret",
        "grant_type": "client_credentials",
    }
    assert kwargs["headers"] == {"Content-Type": "application/x-www-form-urlencoded"}


def test_oauth_set_new_token_raises_on_error(silent_logger):
    with patch("jamfpy.client.auth.request") as mock_req:
        mock_req.return_value = MagicMock(ok=False, text="nope")
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


def test_basic_set_new_token_parses_response(silent_logger):
    with patch("jamfpy.client.auth.request") as mock_req:
        resp = MagicMock(ok=True)
        resp.json.return_value = {"token": "t", "expires": "2035-01-01T00:00:00.000+0000"}
        mock_req.return_value = resp

        auth = _basic(silent_logger)
        auth.set_new_token()

    assert auth._token_str == "t"
    assert auth.token_expiry > _now()

    kwargs = mock_req.call_args.kwargs
    assert kwargs["method"] == "POST"
    assert kwargs["url"] == f"{FQDN}/api/v1/auth/token"
    assert kwargs["headers"]["Authorization"] == f"Basic {auth.basic_auth_token}"


def test_basic_set_new_token_raises_on_error(silent_logger):
    with patch("jamfpy.client.auth.request") as mock_req:
        mock_req.return_value = MagicMock(ok=False, status_code=401)
        auth = _basic(silent_logger)
        with pytest.raises(JamfAuthError):
            auth.set_new_token()


def test_basic_keep_alive_token_updates_token(silent_logger):
    with patch("jamfpy.client.auth.request") as mock_req:
        resp = MagicMock(ok=True)
        resp.json.return_value = {"token": "t2", "expires": "2035-01-01T00:00:00Z"}
        mock_req.return_value = resp

        auth = _basic(silent_logger)
        auth._token_str = "old"  # keep-alive only runs once a token already exists
        auth._keep_alive_token()

    assert auth._token_str == "t2"
    assert auth.token_expiry > _now()
    assert mock_req.call_args.kwargs["url"] == f"{FQDN}/api/v1/auth/keep-alive"


def test_basic_keep_alive_raises_on_error(silent_logger):
    with patch("jamfpy.client.auth.request") as mock_req:
        mock_req.return_value = MagicMock(ok=False)
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
    auth.token_expiry = _now() + 10 * 60

    def refresh():
        auth.token_expiry = _now() + 3600

    with patch.object(auth, "_keep_alive_token", side_effect=refresh) as mock_keep:
        auth.check_token()
    mock_keep.assert_called_once()


def test_check_token_raises_when_buffer_exceeds_lifetime(silent_logger):
    auth = _oauth(silent_logger, token_exp_thold_mins=20)
    auth.token_expiry = _now() - 10
    # set_new_token is a no-op, so the token stays inside the buffer after refresh.
    with patch.object(auth, "set_new_token"):
        with pytest.raises(JamfAuthError):
            auth.check_token()


def test_token_returns_string_when_valid(silent_logger):
    auth = _oauth(silent_logger, token_exp_thold_mins=20)
    auth.token_expiry = _now() + 3600
    auth._token_str = "live-token"
    assert auth.token() == "live-token"


# --- invalidate ------------------------------------------------------------

def test_invalidate_returns_true_on_ok(silent_logger):
    auth = _oauth(silent_logger)
    auth._token_str = "abc"
    with patch("jamfpy.client.auth.request") as mock_req:
        mock_req.return_value = MagicMock(ok=True)
        assert auth.invalidate() is True


def test_invalidate_returns_false_on_error(silent_logger):
    auth = _oauth(silent_logger)
    auth._token_str = "abc"
    with patch("jamfpy.client.auth.request") as mock_req:
        mock_req.return_value = MagicMock(ok=False)
        assert auth.invalidate() is False
