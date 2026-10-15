"""Unit tests for the Pro Scripts endpoint (inherits ProEndpoint CRUD + pagination)."""
# pylint: disable=missing-function-docstring
import json

import pytest
from conftest import FQDN, sent_headers, with_bearer

from jamfpy.client.constants import DEFAULT_HTTP_CONFIG_HEADERS as H
from jamfpy.client.exceptions import JamfAPIError

BASE = f"{FQDN}/api/v1"


def test_get_by_id_builds_v1_url(pro_api, mocked_responses):
    mocked_responses.get(f"{BASE}/scripts/5", json={"id": "5"})
    pro_api.scripts.get_by_id(5)
    req = mocked_responses.calls[-1].request
    assert req.method == "GET"
    assert req.url == f"{BASE}/scripts/5"
    assert sent_headers(req) == with_bearer(H["crud"]["read"]["json"])


def test_delete_by_id_uses_delete_header(pro_api, mocked_responses):
    mocked_responses.delete(f"{BASE}/scripts/5", status=204)
    pro_api.scripts.delete_by_id(5)
    req = mocked_responses.calls[-1].request
    assert req.method == "DELETE"
    assert req.url == f"{BASE}/scripts/5"
    assert sent_headers(req) == with_bearer(H["crud"]["delete"]["json"])


def test_create_posts_json_payload(pro_api, mocked_responses):
    mocked_responses.post(f"{BASE}/scripts", status=201, json={"id": "6"})
    pro_api.scripts.create({"name": "x"})
    req = mocked_responses.calls[-1].request
    assert req.method == "POST"
    assert req.url == f"{BASE}/scripts"
    assert sent_headers(req) == with_bearer(H["crud"]["create-update"]["json"])
    assert json.loads(req.body) == {"name": "x"}


def test_update_by_id_puts_json_payload(pro_api, mocked_responses):
    mocked_responses.put(f"{BASE}/scripts/5", json={"id": "5"})
    pro_api.scripts.update_by_id(5, {"name": "x"})
    req = mocked_responses.calls[-1].request
    assert req.method == "PUT"
    assert req.url == f"{BASE}/scripts/5"
    assert sent_headers(req) == with_bearer(H["crud"]["create-update"]["json"])
    assert json.loads(req.body) == {"name": "x"}


def test_get_all_single_page_returns_aggregated_response(pro_api, mocked_responses):
    mocked_responses.get(f"{BASE}/scripts?page=0&page-size=100", json={"totalCount": 2, "results": [{"id": 1}, {"id": 2}]})
    result = pro_api.scripts.get_all()
    # One consistent contract: a Response whose body is {totalCount, results}.
    body = json.loads(result.content)
    assert body == {"totalCount": 2, "results": [{"id": 1}, {"id": 2}]}
    assert len(mocked_responses.calls) == 1
    req = mocked_responses.calls[-1].request
    assert req.url == f"{BASE}/scripts?page=0&page-size=100"
    assert sent_headers(req) == with_bearer(H["crud"]["read"]["json"])


def test_get_all_paginates_and_increments_page(pro_api, mocked_responses):
    mocked_responses.get(f"{BASE}/scripts?page=0&page-size=100",
                         json={"totalCount": 150, "results": [{"id": i} for i in range(100)]})
    mocked_responses.get(f"{BASE}/scripts?page=1&page-size=100",
                         json={"totalCount": 150, "results": [{"id": i} for i in range(100, 150)]})
    result = pro_api.scripts.get_all()

    body = json.loads(result.content)
    assert body["totalCount"] == 150
    assert [r["id"] for r in body["results"]] == list(range(150))
    # Pagination advances 0 -> 1 (the old code was stuck on page=0).
    assert [call.request.url for call in mocked_responses.calls] == [
        f"{BASE}/scripts?page=0&page-size=100",
        f"{BASE}/scripts?page=1&page-size=100",
    ]


def test_get_all_terminates_on_exact_multiple_via_total_count(pro_api, mocked_responses):
    # totalCount reached exactly on a full page -> no trailing empty request.
    mocked_responses.get(f"{BASE}/scripts?page=0&page-size=100",
                         json={"totalCount": 100, "results": [{"id": i} for i in range(100)]})
    result = pro_api.scripts.get_all()
    assert json.loads(result.content)["totalCount"] == 100
    assert len(mocked_responses.calls) == 1


def test_get_all_honours_custom_page_size_and_sort(pro_api, mocked_responses):
    url = f"{BASE}/scripts?page=0&page-size=25&sort=name:asc"
    mocked_responses.get(url, json={"totalCount": 1, "results": [{"id": 1}]})
    pro_api.scripts.get_all(page_size=25, sort="name:asc")
    assert mocked_responses.calls[-1].request.url == url


def test_get_all_empty_returns_zero_count(pro_api, mocked_responses):
    mocked_responses.get(f"{BASE}/scripts?page=0&page-size=100", json={"totalCount": 0, "results": []})
    result = pro_api.scripts.get_all()
    assert json.loads(result.content) == {"totalCount": 0, "results": []}
    assert len(mocked_responses.calls) == 1


def test_get_all_raises_on_error(pro_api, mocked_responses):
    mocked_responses.get(f"{BASE}/scripts?page=0&page-size=100", json={}, status=500)
    with pytest.raises(JamfAPIError):
        pro_api.scripts.get_all()
