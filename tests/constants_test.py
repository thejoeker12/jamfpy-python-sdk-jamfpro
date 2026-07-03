"""Guard the constants that URL/header assembly depends on."""
# pylint: disable=missing-function-docstring
from jamfpy.client.constants import (
    VALID_AUTH_METHODS,
    DEFAULT_HTTP_CONFIG_URLS,
    DEFAULT_HTTP_CONFIG_HEADERS,
    DEFAULT_TOKEN_BUFFER,
)


def test_valid_auth_methods():
    # These are the user-facing strings accepted by Tenant(auth_method=...).
    assert VALID_AUTH_METHODS == ("oauth2", "basic")


def test_default_token_buffer():
    assert DEFAULT_TOKEN_BUFFER == 20


def test_auth_url_map_shape():
    auth = DEFAULT_HTTP_CONFIG_URLS["auth"]
    assert auth["bearer"] == "/api/v1/auth/token"
    assert auth["oauth"] == "/api/oauth/token"
    assert auth["invalidate-token"] == "/api/v1/auth/invalidate-token"
    assert auth["keep-alive"] == "/api/v1/auth/keep-alive"


def test_api_url_map_shape():
    api = DEFAULT_HTTP_CONFIG_URLS["api"]
    assert api["classic"] == "/JSSResource"
    assert api["pro"] == "/api/v{jamfapiversion}"


def test_crud_header_sets_present():
    crud = DEFAULT_HTTP_CONFIG_HEADERS["crud"]
    for key in ("create-update", "read", "delete", "image"):
        assert key in crud
    # Endpoints select by ["json"] / ["xml"] on these sets.
    assert crud["read"]["json"] == {"accept": "application/json"}
    assert crud["read"]["xml"] == {"accept": "text/xml"}
    assert crud["create-update"]["xml"] == {"accept": "text/xml", "content-type": "text/xml"}


def test_auth_header_sets_present():
    auth = DEFAULT_HTTP_CONFIG_HEADERS["auth"]
    assert auth["oauth"] == {"Content-Type": "application/x-www-form-urlencoded"}
    assert "Authorization" in auth["bearer"]
