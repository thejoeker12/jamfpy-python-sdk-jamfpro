"""Unit tests for the shared ClassicEndpoint / ProEndpoint CRUD in endpoints/models.py.

A throwaway subclass exercises the inherited CRUD; a FakeAPI records the
``requests.Request`` each method builds so we can assert URL/verb/headers/body.
"""
# pylint: disable=missing-function-docstring,too-few-public-methods
import json

import pytest
from conftest import FakeAPI, FQDN, make_response

from jamfpy.endpoints.models import ClassicEndpoint, ProEndpoint
from jamfpy.client.constants import DEFAULT_HTTP_CONFIG_HEADERS as H
from jamfpy.client.exceptions import JamfAPIError

CRUD = H["crud"]
BASE = f"{FQDN}/JSSResource"
PRO_BASE = f"{FQDN}/api/v1"


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


class ProThings(ProEndpoint):
    """Minimal Pro endpoint used only for testing inherited CRUD + pagination."""
    _uri = "/things"
    _name = "things"
    _version = "1"


def _pro_things(responses=None):
    api = FakeAPI(responses=responses)
    return api, ProThings(api)


def test_pro_get_by_id_builds_v1_url_no_id_segment():
    api, things = _pro_things()
    things.get_by_id(5)
    req = api.last_request
    assert req.method == "GET"
    # Pro id path has no /id/ segment.
    assert req.url == f"{PRO_BASE}/things/5"
    assert req.headers == CRUD["read"]["json"]


def test_pro_create_posts_json_body():
    api, things = _pro_things()
    things.create({"name": "x"})
    req = api.last_request
    assert req.method == "POST"
    assert req.url == f"{PRO_BASE}/things"
    assert req.headers == CRUD["create-update"]["json"]
    assert req.json == {"name": "x"}


def test_pro_update_by_id_puts_json_body():
    api, things = _pro_things()
    things.update_by_id(5, {"name": "x"})
    req = api.last_request
    assert req.method == "PUT"
    assert req.url == f"{PRO_BASE}/things/5"
    assert req.headers == CRUD["create-update"]["json"]
    assert req.json == {"name": "x"}


def test_pro_delete_by_id_uses_delete_header():
    api, things = _pro_things()
    things.delete_by_id(5)
    req = api.last_request
    assert req.method == "DELETE"
    assert req.url == f"{PRO_BASE}/things/5"
    assert req.headers == CRUD["delete"]["json"]


def test_pro_name_returns_configured_name():
    _, things = _pro_things()
    assert things.name() == "things"


def test_pro_get_all_single_page_aggregates():
    api, things = _pro_things(responses=[make_response({"totalCount": 2, "results": [{"id": 1}, {"id": 2}]})])
    result = things.get_all()
    body = json.loads(result.content)
    assert body == {"totalCount": 2, "results": [{"id": 1}, {"id": 2}]}
    assert len(api.requests) == 1
    assert api.last_request.url == f"{PRO_BASE}/things?page=0&page-size=100"


def test_pro_get_all_paginates_until_total_count():
    page0 = make_response({"totalCount": 4, "results": [{"id": 0}, {"id": 1}]})
    page1 = make_response({"totalCount": 4, "results": [{"id": 2}, {"id": 3}]})
    api, things = _pro_things(responses=[page0, page1])
    result = things.get_all(page_size=2)
    body = json.loads(result.content)
    assert body["totalCount"] == 4
    assert [r["id"] for r in body["results"]] == [0, 1, 2, 3]
    # Exact multiple: terminates on totalCount, no trailing empty request.
    assert [req.url for req in api.requests] == [
        f"{PRO_BASE}/things?page=0&page-size=2",
        f"{PRO_BASE}/things?page=1&page-size=2",
    ]


def test_pro_get_all_stops_on_short_page_without_total_count():
    # Missing totalCount -> falls back to the short-page backstop.
    page0 = make_response({"results": [{"id": 0}, {"id": 1}]})
    page1 = make_response({"results": [{"id": 2}]})
    api, things = _pro_things(responses=[page0, page1])
    result = things.get_all(page_size=2)
    assert [r["id"] for r in json.loads(result.content)["results"]] == [0, 1, 2]
    assert len(api.requests) == 2


def test_pro_get_all_total_count_zero():
    api, things = _pro_things(responses=[make_response({"totalCount": 0, "results": []})])
    result = things.get_all()
    assert json.loads(result.content) == {"totalCount": 0, "results": []}
    assert len(api.requests) == 1


def test_pro_get_all_raises_on_error():
    _, things = _pro_things(responses=[make_response({}, status=500)])
    with pytest.raises(JamfAPIError):
        things.get_all()
