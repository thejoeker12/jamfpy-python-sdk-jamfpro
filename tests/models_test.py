"""Unit tests for the shared ClassicEndpoint CRUD in endpoints/models.py.

A throwaway subclass exercises the inherited CRUD; a FakeAPI records the
``requests.Request`` each method builds so we can assert URL/verb/headers/body.
"""
# pylint: disable=missing-function-docstring,too-few-public-methods
from conftest import FakeAPI, FQDN

from jamfpy.endpoints.models import ClassicEndpoint
from jamfpy.client.constants import DEFAULT_HTTP_CONFIG_HEADERS as H

CRUD = H["crud"]
BASE = f"{FQDN}/JSSResource"


class Things(ClassicEndpoint):
    """Minimal Classic endpoint used only for testing inherited CRUD."""
    _uri = "/things"
    _name = "things"


def _things():
    api = FakeAPI()
    return api, Things(api)


def test_get_all_defaults_to_json_read():
    api, things = _things()
    things.get_all()
    req = api.last_request
    assert req.method == "GET"
    assert req.url == f"{BASE}/things"
    assert req.headers == CRUD["read"]["json"]


def test_get_all_xml_response_uses_xml_header():
    api, things = _things()
    things.get_all(xml_response=True)
    assert api.last_request.headers == CRUD["read"]["xml"]


def test_get_all_honours_suffix_override():
    api, things = _things()
    things.get_all(suffix="/custom")
    assert api.last_request.url == f"{BASE}/custom"


def test_get_by_id_builds_id_path():
    api, things = _things()
    things.get_by_id(5)
    req = api.last_request
    assert req.method == "GET"
    assert req.url == f"{BASE}/things/id/5"
    assert req.headers == CRUD["read"]["json"]


def test_update_by_id_puts_xml_body():
    api, things = _things()
    things.update_by_id(5, "<thing/>")
    req = api.last_request
    assert req.method == "PUT"
    assert req.url == f"{BASE}/things/id/5"
    assert req.headers == CRUD["create-update"]["xml"]
    assert req.data == "<thing/>"


def test_create_posts_to_id_zero():
    api, things = _things()
    things.create("<thing/>")
    req = api.last_request
    assert req.method == "POST"
    assert req.url == f"{BASE}/things/id/0"
    assert req.headers == CRUD["create-update"]["xml"]
    assert req.data == "<thing/>"


def test_delete_by_id_sends_no_headers():
    api, things = _things()
    things.delete_by_id(5)
    req = api.last_request
    assert req.method == "DELETE"
    assert req.url == f"{BASE}/things/id/5"
    # KNOWN SHAPE: delete builds the Request without a headers= argument.
    assert req.headers == {}


def test_name_returns_configured_name():
    _, things = _things()
    assert things.name() == "things"
