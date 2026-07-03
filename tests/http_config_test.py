"""Unit tests for HTTPConfig."""
# pylint: disable=missing-function-docstring
from jamfpy.client.http_config import HTTPConfig
from jamfpy.client.constants import DEFAULT_HTTP_CONFIG_URLS, DEFAULT_HTTP_CONFIG_HEADERS


def test_defaults_fall_back_to_shared_dicts():
    config = HTTPConfig()
    assert config.urls is DEFAULT_HTTP_CONFIG_URLS
    assert config.headers is DEFAULT_HTTP_CONFIG_HEADERS


def test_custom_urls_and_headers_override():
    urls = {"api": {"classic": "/custom"}}
    headers = {"crud": {"read": {"json": {"accept": "x"}}}}
    config = HTTPConfig(urls=urls, headers=headers)
    assert config.urls is urls
    assert config.headers is headers


def test_partial_override_keeps_default_for_the_other():
    config = HTTPConfig(urls={"only": "urls"})
    assert config.urls == {"only": "urls"}
    assert config.headers is DEFAULT_HTTP_CONFIG_HEADERS
