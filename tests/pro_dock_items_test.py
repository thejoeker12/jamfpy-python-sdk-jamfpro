"""Unit tests for the Pro Dock Items endpoint (inherits ProEndpoint CRUD + pagination)."""
# pylint: disable=missing-function-docstring
import json

import pytest
from conftest import FakeAPI, FQDN, make_response

from jamfpy.endpoints.pro_dock_items import DockItems
from jamfpy.client.constants import DEFAULT_HTTP_CONFIG_HEADERS as H
from jamfpy.client.exceptions import JamfAPIError

BASE = f"{FQDN}/api/v1"

# A DockItem body per the pro.json schema (required: name, path, type).
DOCK_ITEM = {"name": "iTunes", "type": "APP", "path": "file://localhost/Applications/iTunes.app"}


def test_create_posts_json_payload():
    api = FakeAPI()
    DockItems(api).create(DOCK_ITEM)
    req = api.last_request
    assert req.method == "POST"
    assert req.url == f"{BASE}/dock-items"
    assert req.headers == H["crud"]["create-update"]["json"]
    assert req.json == DOCK_ITEM


def test_get_by_id_builds_v1_url():
    api = FakeAPI()
    DockItems(api).get_by_id(7)
    req = api.last_request
    assert req.method == "GET"
    assert req.url == f"{BASE}/dock-items/7"
    assert req.headers == H["crud"]["read"]["json"]


def test_update_by_id_puts_json_payload():
    api = FakeAPI()
    DockItems(api).update_by_id(7, DOCK_ITEM)
    req = api.last_request
    assert req.method == "PUT"
    assert req.url == f"{BASE}/dock-items/7"
    assert req.headers == H["crud"]["create-update"]["json"]
    assert req.json == DOCK_ITEM


def test_delete_by_id_uses_delete_header():
    api = FakeAPI()
    DockItems(api).delete_by_id(7)
    req = api.last_request
    assert req.method == "DELETE"
    assert req.url == f"{BASE}/dock-items/7"
    assert req.headers == H["crud"]["delete"]["json"]


def test_get_all_single_page_returns_aggregated_response():
    api = FakeAPI(responses=[make_response({"totalCount": 2, "results": [{"id": "1"}, {"id": "2"}]})])
    result = DockItems(api).get_all()
    body = json.loads(result.content)
    assert body == {"totalCount": 2, "results": [{"id": "1"}, {"id": "2"}]}
    assert len(api.requests) == 1
    assert api.last_request.url == f"{BASE}/dock-items?page=0&page-size=100"


def test_get_all_raises_on_error():
    api = FakeAPI(responses=[make_response({}, status=500)])
    with pytest.raises(JamfAPIError):
        DockItems(api).get_all()


def test_name_returns_snake_case_key():
    assert DockItems(FakeAPI()).name() == "dock_items"
