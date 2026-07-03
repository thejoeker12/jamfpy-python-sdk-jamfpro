"""Unit tests for the Pro Scripts endpoint (inherits ProEndpoint CRUD + pagination)."""
# pylint: disable=missing-function-docstring
import json

import pytest
from conftest import FakeAPI, FQDN, make_response

from jamfpy.endpoints.pro_scripts import Scripts
from jamfpy.client.constants import DEFAULT_HTTP_CONFIG_HEADERS as H
from jamfpy.client.exceptions import JamfAPIError

BASE = f"{FQDN}/api/v1"


def test_get_by_id_builds_v1_url():
    api = FakeAPI()
    Scripts(api).get_by_id(5)
    req = api.last_request
    assert req.method == "GET"
    assert req.url == f"{BASE}/scripts/5"
    assert req.headers == H["crud"]["read"]["json"]


def test_delete_by_id_uses_delete_header():
    api = FakeAPI()
    Scripts(api).delete_by_id(5)
    req = api.last_request
    assert req.method == "DELETE"
    assert req.url == f"{BASE}/scripts/5"
    assert req.headers == H["crud"]["delete"]["json"]


def test_create_posts_json_payload():
    api = FakeAPI()
    Scripts(api).create({"name": "x"})
    req = api.last_request
    assert req.method == "POST"
    assert req.url == f"{BASE}/scripts"
    assert req.headers == H["crud"]["create-update"]["json"]
    assert req.json == {"name": "x"}


def test_update_by_id_puts_json_payload():
    api = FakeAPI()
    Scripts(api).update_by_id(5, {"name": "x"})
    req = api.last_request
    assert req.method == "PUT"
    assert req.url == f"{BASE}/scripts/5"
    assert req.headers == H["crud"]["create-update"]["json"]
    assert req.json == {"name": "x"}


def test_get_all_single_page_returns_aggregated_response():
    api = FakeAPI(responses=[make_response({"totalCount": 2, "results": [{"id": 1}, {"id": 2}]})])
    result = Scripts(api).get_all()
    # One consistent contract: a Response whose body is {totalCount, results}.
    body = json.loads(result.content)
    assert body == {"totalCount": 2, "results": [{"id": 1}, {"id": 2}]}
    assert len(api.requests) == 1
    assert api.last_request.url == f"{BASE}/scripts?page=0&page-size=100"


def test_get_all_paginates_and_increments_page():
    page0 = make_response({"totalCount": 150, "results": [{"id": i} for i in range(100)]})
    page1 = make_response({"totalCount": 150, "results": [{"id": i} for i in range(100, 150)]})
    api = FakeAPI(responses=[page0, page1])
    result = Scripts(api).get_all()

    body = json.loads(result.content)
    assert body["totalCount"] == 150
    assert [r["id"] for r in body["results"]] == list(range(150))
    # Pagination advances 0 -> 1 (the old code was stuck on page=0).
    assert [req.url for req in api.requests] == [
        f"{BASE}/scripts?page=0&page-size=100",
        f"{BASE}/scripts?page=1&page-size=100",
    ]


def test_get_all_terminates_on_exact_multiple_via_total_count():
    # totalCount reached exactly on a full page -> no trailing empty request.
    page0 = make_response({"totalCount": 100, "results": [{"id": i} for i in range(100)]})
    api = FakeAPI(responses=[page0])
    result = Scripts(api).get_all()
    assert json.loads(result.content)["totalCount"] == 100
    assert len(api.requests) == 1


def test_get_all_honours_custom_page_size_and_sort():
    api = FakeAPI(responses=[make_response({"totalCount": 1, "results": [{"id": 1}]})])
    Scripts(api).get_all(page_size=25, sort="name:asc")
    assert api.last_request.url == f"{BASE}/scripts?page=0&page-size=25&sort=name:asc"


def test_get_all_empty_returns_zero_count():
    api = FakeAPI(responses=[make_response({"totalCount": 0, "results": []})])
    result = Scripts(api).get_all()
    assert json.loads(result.content) == {"totalCount": 0, "results": []}
    assert len(api.requests) == 1


def test_get_all_raises_on_error():
    api = FakeAPI(responses=[make_response({}, status=500)])
    with pytest.raises(JamfAPIError):
        Scripts(api).get_all()
