"""Unit tests for the Pro Dock Items endpoint (composes get_by_id, create, update_by_id and delete_by_id; no get_all)."""
# pylint: disable=missing-function-docstring
import json

from conftest import FQDN, sent_headers, with_bearer

from jamfpy.client.constants import DEFAULT_HTTP_CONFIG_HEADERS as H
from jamfpy.endpoints.models import ProGetAll
from jamfpy.endpoints.pro_dock_items import DockItems

BASE = f"{FQDN}/api/v1"

# A DockItem body per the pro.json schema (required: name, path, type).
DOCK_ITEM = {"name": "iTunes", "type": "APP", "path": "file://localhost/Applications/iTunes.app"}


def test_create_posts_json_payload(pro_api, mocked_responses):
    mocked_responses.post(f"{BASE}/dock-items", status=201, json={"id": "7"})
    pro_api.dock_items.create(DOCK_ITEM)
    req = mocked_responses.calls[-1].request
    assert req.method == "POST"
    assert req.url == f"{BASE}/dock-items"
    assert sent_headers(req) == with_bearer(H["crud"]["create-update"]["json"])
    assert json.loads(req.body) == DOCK_ITEM


def test_get_by_id_builds_v1_url(pro_api, mocked_responses):
    mocked_responses.get(f"{BASE}/dock-items/7", json={"id": "7", **DOCK_ITEM})
    pro_api.dock_items.get_by_id(7)
    req = mocked_responses.calls[-1].request
    assert req.method == "GET"
    assert req.url == f"{BASE}/dock-items/7"
    assert sent_headers(req) == with_bearer(H["crud"]["read"]["json"])


def test_update_by_id_puts_json_payload(pro_api, mocked_responses):
    mocked_responses.put(f"{BASE}/dock-items/7", json={"id": "7", **DOCK_ITEM})
    pro_api.dock_items.update_by_id(7, DOCK_ITEM)
    req = mocked_responses.calls[-1].request
    assert req.method == "PUT"
    assert req.url == f"{BASE}/dock-items/7"
    assert sent_headers(req) == with_bearer(H["crud"]["create-update"]["json"])
    assert json.loads(req.body) == DOCK_ITEM


def test_delete_by_id_uses_delete_header(pro_api, mocked_responses):
    mocked_responses.delete(f"{BASE}/dock-items/7", status=204)
    pro_api.dock_items.delete_by_id(7)
    req = mocked_responses.calls[-1].request
    assert req.method == "DELETE"
    assert req.url == f"{BASE}/dock-items/7"
    assert sent_headers(req) == with_bearer(H["crud"]["delete"]["json"])


def test_has_no_get_all():
    # The schema's /v1/dock-items collection takes POST only, so DockItems composes four capabilities.
    assert not hasattr(DockItems, "get_all")
    assert not issubclass(DockItems, ProGetAll)
    assert all(hasattr(DockItems, method) for method in ("get_by_id", "create", "update_by_id", "delete_by_id"))


def test_name_returns_snake_case_key(pro_api):
    assert pro_api.dock_items.name() == "dock_items"
