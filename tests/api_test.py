"""Unit tests for the API base behaviour via ClassicAPI / ProAPI.

The one wire call (``API.do`` -> ``session.send``) and the auth refresh are
mocked; construction itself does no network.
"""
# pylint: disable=missing-function-docstring,protected-access,redefined-outer-name
from unittest.mock import MagicMock

import pytest
from requests import Request
from conftest import FQDN

from jamfpy.client.client import ClassicAPI, ProAPI
from jamfpy.client.http_config import HTTPConfig
from jamfpy.client.constants import DEFAULT_HTTP_CONFIG_HEADERS
from jamfpy.client.exceptions import JamfpyConfigError


@pytest.fixture
def mock_auth():
    auth = MagicMock()
    auth.token.return_value = "tok"
    return auth


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
    sentinel = MagicMock(status_code=200, url=f"{FQDN}/x")
    api._session.send.return_value = sentinel

    result = api.do(Request("GET", url=f"{FQDN}/JSSResource/computers"))

    assert result is sentinel
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
