"""Unit tests for the shared ClassicEndpoint / ProEndpoint CRUD in endpoints/models.py.

A throwaway subclass exercises the inherited CRUD against the real ``ClassicAPI`` /
``ProAPI`` from the ``tenant`` fixture; ``responses`` records the request each method
sends so we can assert verb, URL, headers (including the injected Bearer token) and body.

The ``OrderedRegistry`` override below makes every registration single-use and order-bound, so a
``get_all`` that re-requests a page or walks past the last one fails the test instead of looping.
"""
# pylint: disable=missing-function-docstring,too-few-public-methods,redefined-outer-name
import json

import pytest
from conftest import FQDN, sent_headers, with_bearer
from responses.registries import OrderedRegistry

from jamfpy.endpoints.models import ClassicEndpoint, ProEndpoint
from jamfpy.client.constants import DEFAULT_HTTP_CONFIG_HEADERS as H
from jamfpy.client.exceptions import JamfAPIError
from jamfpy.client.retry import RetryConfig

CRUD = H["crud"]
BASE = f"{FQDN}/JSSResource"
PRO_BASE = f"{FQDN}/api/v1"


@pytest.fixture
def response_registry():
    """Serve each registration once, in the order registered; a surplus request raises ``ConnectionError``."""
    return OrderedRegistry


class Things(ClassicEndpoint):
    """Minimal Classic endpoint used only for testing inherited CRUD."""
    _uri = "/things"
    _name = "things"


@pytest.fixture
def things(classic_api):
    return Things(classic_api)


def _last(rsps):
    return rsps.calls[-1].request


def test_get_all_defaults_to_json_read(things, mocked_responses):
    mocked_responses.get(f"{BASE}/things", json={"things": []})
    things.get_all()
    req = _last(mocked_responses)
    assert req.method == "GET"
    assert req.url == f"{BASE}/things"
    assert sent_headers(req) == with_bearer(CRUD["read"]["json"])


def test_get_all_xml_response_uses_xml_header(things, mocked_responses):
    mocked_responses.get(f"{BASE}/things", body="<things/>")
    things.get_all(xml_response=True)
    assert sent_headers(_last(mocked_responses)) == with_bearer(CRUD["read"]["xml"])


def test_get_all_honours_suffix_override(things, mocked_responses):
    mocked_responses.get(f"{BASE}/custom", json={})
    things.get_all(suffix="/custom")
    assert _last(mocked_responses).url == f"{BASE}/custom"


def test_get_by_id_builds_id_path(things, mocked_responses):
    mocked_responses.get(f"{BASE}/things/id/5", json={})
    things.get_by_id(5)
    req = _last(mocked_responses)
    assert req.method == "GET"
    assert req.url == f"{BASE}/things/id/5"
    assert sent_headers(req) == with_bearer(CRUD["read"]["json"])


def test_update_by_id_puts_xml_body(things, mocked_responses):
    mocked_responses.put(f"{BASE}/things/id/5", body="<thing><id>5</id></thing>")
    things.update_by_id(5, "<thing/>")
    req = _last(mocked_responses)
    assert req.method == "PUT"
    assert req.url == f"{BASE}/things/id/5"
    assert sent_headers(req) == with_bearer(CRUD["create-update"]["xml"])
    assert req.body == "<thing/>"


def test_create_posts_to_id_zero(things, mocked_responses):
    mocked_responses.post(f"{BASE}/things/id/0", status=201, body="<thing><id>6</id></thing>")
    things.create("<thing/>")
    req = _last(mocked_responses)
    assert req.method == "POST"
    assert req.url == f"{BASE}/things/id/0"
    assert sent_headers(req) == with_bearer(CRUD["create-update"]["xml"])
    assert req.body == "<thing/>"


def test_delete_by_id_sends_no_headers_of_its_own(things, mocked_responses):
    mocked_responses.delete(f"{BASE}/things/id/5")
    things.delete_by_id(5)
    req = _last(mocked_responses)
    assert req.method == "DELETE"
    assert req.url == f"{BASE}/things/id/5"
    # Characterises current behaviour: delete builds the Request without a headers= argument,
    # so only the session defaults (requests' Accept: */* among them) and the auth header go out.
    assert sent_headers(req) == with_bearer({})


def test_name_returns_configured_name(things):
    assert things.name() == "things"


class ProThings(ProEndpoint):
    """Minimal Pro endpoint used only for testing inherited CRUD + pagination."""
    _uri = "/things"
    _name = "things"
    _version = "1"


@pytest.fixture
def pro_things(pro_api):
    return ProThings(pro_api)


def _page(rsps, page, size, body, status=200):
    rsps.get(f"{PRO_BASE}/things?page={page}&page-size={size}", json=body, status=status)


def test_pro_get_by_id_builds_v1_url_no_id_segment(pro_things, mocked_responses):
    mocked_responses.get(f"{PRO_BASE}/things/5", json={"id": "5"})
    pro_things.get_by_id(5)
    req = _last(mocked_responses)
    assert req.method == "GET"
    # Pro id path has no /id/ segment.
    assert req.url == f"{PRO_BASE}/things/5"
    assert sent_headers(req) == with_bearer(CRUD["read"]["json"])


def test_pro_create_posts_json_body(pro_things, mocked_responses):
    mocked_responses.post(f"{PRO_BASE}/things", status=201, json={"id": "6"})
    pro_things.create({"name": "x"})
    req = _last(mocked_responses)
    assert req.method == "POST"
    assert req.url == f"{PRO_BASE}/things"
    assert sent_headers(req) == with_bearer(CRUD["create-update"]["json"])
    assert json.loads(req.body) == {"name": "x"}


def test_pro_update_by_id_puts_json_body(pro_things, mocked_responses):
    mocked_responses.put(f"{PRO_BASE}/things/5", json={"id": "5"})
    pro_things.update_by_id(5, {"name": "x"})
    req = _last(mocked_responses)
    assert req.method == "PUT"
    assert req.url == f"{PRO_BASE}/things/5"
    assert sent_headers(req) == with_bearer(CRUD["create-update"]["json"])
    assert json.loads(req.body) == {"name": "x"}


def test_pro_delete_by_id_uses_delete_header(pro_things, mocked_responses):
    mocked_responses.delete(f"{PRO_BASE}/things/5", status=204)
    pro_things.delete_by_id(5)
    req = _last(mocked_responses)
    assert req.method == "DELETE"
    assert req.url == f"{PRO_BASE}/things/5"
    assert sent_headers(req) == with_bearer(CRUD["delete"]["json"])


def test_pro_name_returns_configured_name(pro_things):
    assert pro_things.name() == "things"


def test_pro_get_all_single_page_aggregates(pro_things, mocked_responses):
    _page(mocked_responses, 0, 100, {"totalCount": 2, "results": [{"id": 1}, {"id": 2}]})
    result = pro_things.get_all()
    body = json.loads(result.content)
    assert body == {"totalCount": 2, "results": [{"id": 1}, {"id": 2}]}
    assert len(mocked_responses.calls) == 1
    req = _last(mocked_responses)
    assert req.url == f"{PRO_BASE}/things?page=0&page-size=100"
    assert sent_headers(req) == with_bearer(CRUD["read"]["json"])


def test_pro_get_all_paginates_until_total_count(pro_things, mocked_responses):
    _page(mocked_responses, 0, 2, {"totalCount": 4, "results": [{"id": 0}, {"id": 1}]})
    _page(mocked_responses, 1, 2, {"totalCount": 4, "results": [{"id": 2}, {"id": 3}]})
    result = pro_things.get_all(page_size=2)
    body = json.loads(result.content)
    assert body["totalCount"] == 4
    assert [r["id"] for r in body["results"]] == [0, 1, 2, 3]
    # Exact multiple: terminates on totalCount, no trailing empty request.
    assert [call.request.url for call in mocked_responses.calls] == [
        f"{PRO_BASE}/things?page=0&page-size=2",
        f"{PRO_BASE}/things?page=1&page-size=2",
    ]


def test_pro_get_all_stops_on_short_page_without_total_count(pro_things, mocked_responses):
    # Missing totalCount -> falls back to the short-page backstop.
    _page(mocked_responses, 0, 2, {"results": [{"id": 0}, {"id": 1}]})
    _page(mocked_responses, 1, 2, {"results": [{"id": 2}]})
    result = pro_things.get_all(page_size=2)
    assert [r["id"] for r in json.loads(result.content)["results"]] == [0, 1, 2]
    assert len(mocked_responses.calls) == 2


def test_pro_get_all_stops_when_server_ignores_page(pro_things, mocked_responses):
    # Every page answers with the same full page and no totalCount; the guard ends the walk after page 3.
    for page in range(4):
        _page(mocked_responses, page, 2, {"results": [{"id": 0}, {"id": 1}]})
    result = pro_things.get_all(page_size=2)
    assert len(json.loads(result.content)["results"]) == 8
    assert [call.request.url for call in mocked_responses.calls] == [
        f"{PRO_BASE}/things?page={page}&page-size=2" for page in range(4)
    ]


def test_pro_get_all_total_count_zero(pro_things, mocked_responses):
    _page(mocked_responses, 0, 100, {"totalCount": 0, "results": []})
    result = pro_things.get_all()
    assert json.loads(result.content) == {"totalCount": 0, "results": []}
    assert len(mocked_responses.calls) == 1


def test_pro_get_all_raises_on_error(pro_things, mocked_responses):
    # A 500 is retried, so the page answers every attempt with it before get_all sees the failure.
    attempts = RetryConfig().total + 1
    for _ in range(attempts):
        _page(mocked_responses, 0, 100, {}, status=500)
    with pytest.raises(JamfAPIError):
        pro_things.get_all()
    assert len(mocked_responses.calls) == attempts
