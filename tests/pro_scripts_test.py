"""Unit tests for the Pro Scripts endpoint (paginating get_all is legacy)."""
# pylint: disable=missing-function-docstring
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


def test_delete_by_id_sends_no_headers():
    api = FakeAPI()
    Scripts(api).delete_by_id(5)
    req = api.last_request
    assert req.method == "DELETE"
    assert req.url == f"{BASE}/scripts/5"
    assert req.headers == {}


def test_get_all_single_page_returns_tuple():
    # KNOWN QUIRK: a single short page returns (Response, results-list).
    api = FakeAPI(responses=[make_response({"results": [{"id": 1}, {"id": 2}]})])
    result = Scripts(api).get_all()
    assert isinstance(result, tuple)
    _, results = result
    assert results == [{"id": 1}, {"id": 2}]


def test_get_all_multi_page_returns_bare_response():
    # KNOWN QUIRK: across multiple pages get_all returns the last (empty)
    # Response, NOT the aggregated list and NOT a tuple.
    page1 = make_response({"results": [{"id": i} for i in range(200)]})
    page2 = make_response({"results": []})
    api = FakeAPI(responses=[page1, page2])
    result = Scripts(api).get_all()
    assert not isinstance(result, tuple)
    assert result is page2


def test_get_all_pagination_stuck_on_page_zero():
    # KNOWN QUIRK: the pre-interpolated f-string means every page requests page=0.
    page1 = make_response({"results": [{"id": i} for i in range(200)]})
    page2 = make_response({"results": []})
    api = FakeAPI(responses=[page1, page2])
    Scripts(api).get_all()
    assert len(api.requests) == 2
    assert all("page=0" in req.url for req in api.requests)


def test_get_all_raises_on_error():
    api = FakeAPI(responses=[make_response({}, status=500)])
    with pytest.raises(JamfAPIError):
        Scripts(api).get_all()
