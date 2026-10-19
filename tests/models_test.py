"""Unit tests for the shared ClassicEndpoint CRUD and the Pro capability mixins in endpoints/models.py.

A throwaway subclass exercises the inherited CRUD against the real ``ClassicAPI`` /
``ProAPI`` from the ``tenant`` fixture; ``responses`` records the request each method
sends so we can assert verb, URL, headers (including the injected Bearer token) and body.

The ``OrderedRegistry`` override below makes every registration single-use and order-bound, so a
``get_all`` that re-requests a page or walks past the last one fails the test instead of looping.
``TestParallelGetAll`` puts the default ``FirstMatchRegistry`` back: OrderedRegistry is one FIFO
for the whole mock, and pages fetched in parallel arrive in any order, so those tests give each
page its own ``page=`` URL instead.
"""
# pylint: disable=missing-function-docstring,too-few-public-methods,redefined-outer-name,too-many-lines
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlsplit

import pytest
import responses
from conftest import FQDN, sent_headers, with_bearer
from responses import matchers
from responses.registries import FirstMatchRegistry, OrderedRegistry

import jamfpy
from jamfpy.endpoints import models
from jamfpy.endpoints.models import (
    ClassicEndpoint,
    ProBase,
    ProCreate,
    ProDeleteById,
    ProEndpoint,
    ProGetAll,
    ProGetById,
    ProUpdateById,
)
from jamfpy.endpoints.pro_app_installers import AppInstallers
from jamfpy.endpoints.pro_dock_items import DockItems
from jamfpy.endpoints.pro_scripts import Scripts
from jamfpy.client.constants import DEFAULT_HTTP_CONFIG_HEADERS as H
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


def test_pro_get_all_returns_a_failed_first_page_raw(pro_things, mocked_responses):
    # A 500 is retried, so the page answers every attempt with it before get_all sees the failure.
    attempts = RetryConfig().total + 1
    for _ in range(attempts):
        _page(mocked_responses, 0, 100, {"error": "boom"}, status=500)
    result = pro_things.get_all()
    assert result.status_code == 500
    assert result.json() == {"error": "boom"}
    assert len(mocked_responses.calls) == attempts


def test_pro_get_all_without_total_count_stops_at_a_later_pages_total_count(pro_things, mocked_responses):
    # Characterises current behaviour: the sequential walk takes a totalCount from whichever page carries one.
    _page(mocked_responses, 0, 2, {"results": [{"id": 0}, {"id": 1}]})
    _page(mocked_responses, 1, 2, {"totalCount": 4, "results": [{"id": 2}, {"id": 3}]})
    result = pro_things.get_all(page_size=2)
    assert json.loads(result.content) == {"totalCount": 4, "results": [{"id": i} for i in range(4)]}
    assert len(mocked_responses.calls) == 2


def test_pro_get_all_without_total_count_returns_a_failed_later_page_raw(pro_things, mocked_responses):
    _page(mocked_responses, 0, 2, {"results": [{"id": 0}, {"id": 1}]})
    for _ in range(RetryConfig().total + 1):
        _page(mocked_responses, 1, 2, {"error": "boom"}, status=500)
    result = pro_things.get_all(page_size=2)
    assert result.status_code == 500
    assert _page_of(result.url) == 1


# --- capability mixins -------------------------------------------------------

MIXIN_METHODS = {
    ProGetAll: "get_all",
    ProGetById: "get_by_id",
    ProCreate: "create",
    ProUpdateById: "update_by_id",
    ProDeleteById: "delete_by_id",
}


def test_pro_endpoint_composes_all_five_mixins():
    assert all(mixin in ProEndpoint.__mro__ for mixin in MIXIN_METHODS)


@pytest.mark.parametrize("mixin, method", MIXIN_METHODS.items(), ids=list(MIXIN_METHODS.values()))
def test_each_mixin_contributes_exactly_one_public_method(mixin, method):
    assert issubclass(mixin, ProBase)
    assert {name for name in vars(mixin) if not name.startswith("_")} == {method}


def test_pro_base_carries_version_page_size_and_name():
    assert (ProBase._version, ProBase._page_size) == ("1", 100)  # pylint: disable=protected-access
    assert {name for name in vars(ProBase) if not name.startswith("_")} == {"name"}


def test_dock_items_composes_the_four_verbs_its_schema_has():
    assert not hasattr(DockItems, "get_all")
    assert [cls for cls in DockItems.__mro__ if cls in MIXIN_METHODS] == [ProGetById, ProCreate, ProUpdateById, ProDeleteById]
    assert all(hasattr(DockItems, method) for method in ("get_by_id", "create", "update_by_id", "delete_by_id", "name"))


@pytest.mark.parametrize("endpoint", [Scripts, AppInstallers])
def test_full_crud_endpoints_are_pro_endpoints(endpoint):
    assert issubclass(endpoint, ProEndpoint)
    assert all(hasattr(endpoint, method) for method in MIXIN_METHODS.values())


SINGLE_MIXIN_CALLS = [
    (ProGetAll, "get_all", (), "GET", f"{PRO_BASE}/things?page=0&page-size=100", CRUD["read"]["json"], None),
    (ProGetById, "get_by_id", (5,), "GET", f"{PRO_BASE}/things/5", CRUD["read"]["json"], None),
    (ProCreate, "create", ({"name": "x"},), "POST", f"{PRO_BASE}/things", CRUD["create-update"]["json"], {"name": "x"}),
    (ProUpdateById, "update_by_id", (5, {"name": "x"}), "PUT", f"{PRO_BASE}/things/5", CRUD["create-update"]["json"], {"name": "x"}),
    (ProDeleteById, "delete_by_id", (5,), "DELETE", f"{PRO_BASE}/things/5", CRUD["delete"]["json"], None),
]


@pytest.mark.parametrize("call", SINGLE_MIXIN_CALLS, ids=[call[1] for call in SINGLE_MIXIN_CALLS])
def test_a_mixin_on_its_own_sends_the_same_request(pro_api, mocked_responses, call):
    mixin, method, args, verb, url, headers, body = call
    only = type("OnlyThings", (mixin,), {"_uri": "/things", "_name": "things"})(pro_api)
    mocked_responses.add(verb, url, json={"totalCount": 0, "results": []})
    getattr(only, method)(*args)
    req = _last(mocked_responses)
    assert (req.method, req.url) == (verb, url)
    assert sent_headers(req) == with_bearer(headers)
    assert (json.loads(req.body) if req.body else None) == body


# --- parallel pagination -----------------------------------------------------

SIZE = 2


def _page_of(url):
    return int(parse_qs(urlsplit(url).query)["page"][0])


def _page_url(page):
    return f"{PRO_BASE}/things?page={page}&page-size={SIZE}"


def _page_body(page, total):
    return {"totalCount": total, "results": [{"id": i} for i in range(page * SIZE, min((page + 1) * SIZE, total))]}


def _register_pages(rsps, total, pages=None):
    """Register an ok answer for each page of a ``total``-record dataset (or just ``pages``); returns the page count."""
    count = max(1, -(-total // SIZE))
    for page in range(count) if pages is None else pages:
        rsps.get(_page_url(page), json=_page_body(page, total))
    return count


def _ids(resp):
    return [record["id"] for record in resp.json()["results"]]


@pytest.fixture
def make_pro_things(tenant, sleeps):
    """``ProThings`` on a ``ProAPI`` with the given ``parallelism``, sharing the tenant's Auth and hooks.

    It logs through ``jamfpy.test-pro`` at CRITICAL; a test that reads its WARNINGs raises the level after building.
    """
    def build(parallelism):
        api = jamfpy.ProAPI(
            fqdn=FQDN, auth=tenant.pro.auth, hooks=tenant.hooks, log_level=logging.CRITICAL,
            sleep=sleeps.append, random_source=lambda: 0.5, parallelism=parallelism,
        )
        return ProThings(api)
    return build


@pytest.fixture
def executors(monkeypatch):
    """The ``max_workers`` of every ThreadPoolExecutor ``get_all`` creates, in order."""
    seen = []

    class RecordingExecutor(ThreadPoolExecutor):
        """A real executor that records its size."""
        def __init__(self, max_workers=None, **kwargs):
            seen.append(max_workers)
            super().__init__(max_workers=max_workers, **kwargs)

    monkeypatch.setattr(models, "ThreadPoolExecutor", RecordingExecutor)
    return seen


@pytest.fixture
def page_failed(monkeypatch):
    """An Event set once any page ``get_all`` fetched in parallel has completed without an ok status or has raised."""
    event = threading.Event()

    def note(done):
        if done.exception() is not None or not done.result().ok:
            event.set()

    class WatchingExecutor(ThreadPoolExecutor):
        """A real executor whose futures set ``event`` when a page fails."""
        def submit(self, fn, /, *args, **kwargs):
            future = super().submit(fn, *args, **kwargs)
            future.add_done_callback(note)
            return future

    monkeypatch.setattr(models, "ThreadPoolExecutor", WatchingExecutor)
    return event


def test_parallelism_one_fetches_pages_in_order_on_the_calling_thread(make_pro_things, mocked_responses, executors):
    _register_pages(mocked_responses, 7)
    result = make_pro_things(1).get_all(page_size=SIZE)
    assert _ids(result) == list(range(7))
    assert [_page_of(call.request.url) for call in mocked_responses.calls] == [0, 1, 2, 3]
    assert not executors


def test_parallelism_one_stops_at_a_repeated_page(make_pro_things, mocked_responses, caplog):
    same = {"totalCount": 8, "results": [{"id": 0}, {"id": 1}]}
    for page in (0, 1):
        mocked_responses.get(_page_url(page), json=same)
    things = make_pro_things(1)
    caplog.set_level(logging.WARNING, logger="jamfpy.test-pro")

    result = things.get_all(page_size=SIZE)

    # Sequential, so nothing after the repeated page is requested.
    assert result.json() == {"totalCount": 2, "results": [{"id": 0}, {"id": 1}]}
    assert [_page_of(call.request.url) for call in mocked_responses.calls] == [0, 1]
    assert [record.levelno for record in caplog.records] == [logging.WARNING]
    assert caplog.records[0].getMessage().endswith("the server appears to ignore page: 2 results from page 0 returned")


@pytest.mark.parametrize("case", [
    (1, 2, "2 results from page 0 returned"),
    (1, 1, "1 result from page 0 returned"),
    (3, 2, "6 results from pages 0-2 returned"),
], ids=["many-results-one-page", "one-result-one-page", "many-results-several-pages"])
def test_the_ignored_page_warning_is_grammatical_for_one_and_many(make_pro_things, mocked_responses, caplog, case):
    distinct_pages, results_per_page, expected = case
    # Pages 0..distinct_pages-1 hold different records and the next repeats page 0. A page may hold fewer records
    # than the page size: the totalCount of 99 keeps get_all fetching.
    def body(first_id):
        return {"totalCount": 99, "results": [{"id": first_id + i} for i in range(results_per_page)]}

    for page in range(distinct_pages):
        mocked_responses.get(_page_url(page), json=body(page * results_per_page))
    mocked_responses.get(_page_url(distinct_pages), json=body(0))
    things = make_pro_things(1)
    caplog.set_level(logging.WARNING, logger="jamfpy.test-pro")

    things.get_all(page_size=SIZE)

    [warning] = caplog.records
    assert warning.getMessage().endswith(f"the server appears to ignore page: {expected}")


class TestParallelGetAll:
    """get_all at parallelism above 1: pages 1..N on worker threads, served by the default registry."""

    @pytest.fixture
    def response_registry(self):
        return FirstMatchRegistry

    def test_same_aggregate_at_parallelism_one_and_five(self, make_pro_things, mocked_responses):
        _register_pages(mocked_responses, 7)
        sequential = make_pro_things(1).get_all(page_size=SIZE)
        parallel = make_pro_things(5).get_all(page_size=SIZE)
        assert sequential.json() == parallel.json() == {"totalCount": 7, "results": [{"id": i} for i in range(7)]}
        assert sequential.status_code == parallel.status_code == 200
        # The aggregate is built on the last page, whichever order the pages arrived in.
        assert _page_of(sequential.url) == _page_of(parallel.url) == 3

    def test_pages_after_the_first_are_in_flight_together(self, make_pro_things, mocked_responses):
        # Each of pages 1-3 blocks until all three are in its handler at once; sent one at a time, the barrier
        # times out and BrokenBarrierError fails the call.
        barrier = threading.Barrier(parties=3, timeout=5)

        def answer(page):
            def callback(_request):
                barrier.wait()
                return 200, {}, json.dumps(_page_body(page, 7))
            return callback

        _register_pages(mocked_responses, 7, pages=[0])
        for page in (1, 2, 3):
            # add_callback ignores the query string unless told to match it, which would hand any page any callback.
            mocked_responses.add_callback(
                responses.GET, _page_url(page), callback=answer(page),
                match=[matchers.query_string_matcher(urlsplit(_page_url(page)).query)],
            )

        result = make_pro_things(3).get_all(page_size=SIZE)

        assert _ids(result) == list(range(7))

    @pytest.mark.parametrize("case", [
        (2, 7, [2]),
        (3, 7, [3]),
        (5, 7, [3]),
        (5, 3, [1]),
        (5, 2, []),
        (1, 7, []),
    ], ids=["2-of-3", "3-of-3", "5-capped-at-3", "one-page-left", "single-page", "sequential"])
    def test_max_workers_is_the_smaller_of_parallelism_and_pages_remaining(self, make_pro_things, mocked_responses, executors, case):
        parallelism, total, expected = case
        _register_pages(mocked_responses, total)
        make_pro_things(parallelism).get_all(page_size=SIZE)
        assert executors == expected

    def test_hooks_fire_once_per_page_and_later_pages_run_on_worker_threads(self, tenant, make_pro_things, mocked_responses):
        _register_pages(mocked_responses, 7)
        seen, lock = [], threading.Lock()

        @tenant.hooks.before_request
        def before(prepared, ctx):
            with lock:
                seen.append(("before", _page_of(prepared.url), ctx.attempt, threading.get_ident()))

        @tenant.hooks.after_response
        def after(prepared, response, ctx):  # pylint: disable=unused-argument
            with lock:
                seen.append(("after", _page_of(prepared.url), ctx.attempt, threading.get_ident()))

        make_pro_things(5).get_all(page_size=SIZE)

        caller = threading.get_ident()
        assert sorted((kind, page) for kind, page, _, _ in seen) == sorted(
            (kind, page) for kind in ("before", "after") for page in range(4)
        )
        assert {attempt for _, _, attempt, _ in seen} == {1}
        assert {ident for _, page, _, ident in seen if page == 0} == {caller}
        assert caller not in {ident for _, page, _, ident in seen if page != 0}

    def test_a_failed_page_is_returned_raw(self, make_pro_things, mocked_responses):
        _register_pages(mocked_responses, 7, pages=[0, 1, 3])
        mocked_responses.get(_page_url(2), json={"error": "page 2"}, status=500)

        result = make_pro_things(5).get_all(page_size=SIZE)

        assert result.status_code == 500
        assert _page_of(result.url) == 2
        # The page's own body, not an aggregate holding page 0's results.
        assert result.json() == {"error": "page 2"}

    def test_the_lowest_failed_page_wins(self, make_pro_things, mocked_responses):
        _register_pages(mocked_responses, 7, pages=[0, 2])
        mocked_responses.get(_page_url(1), json={"error": "page 1"}, status=500)
        mocked_responses.get(_page_url(3), json={"error": "page 3"}, status=502)

        result = make_pro_things(5).get_all(page_size=SIZE)

        assert (result.status_code, _page_of(result.url)) == (500, 1)
        assert result.json() == {"error": "page 1"}

    @staticmethod
    def _held_until(event, total, page, status=200, body=None):
        """A callback answering ``page`` only once ``event`` is set, or after 3 s so a missing stop fails by count."""
        def callback(_request):
            event.wait(timeout=3)
            return status, {}, json.dumps(body if body is not None else _page_body(page, total))
        return callback

    def _hold(self, rsps, event, total, pages, **answer):
        for page in pages:
            # add_callback ignores the query string unless told to match it.
            rsps.add_callback(
                responses.GET, _page_url(page), callback=self._held_until(event, total, page, **answer),
                match=[matchers.query_string_matcher(urlsplit(_page_url(page)).query)],
            )

    def test_a_failed_page_stops_further_pages_from_starting(self, make_pro_things, mocked_responses, page_failed):
        total = 24
        _register_pages(mocked_responses, total, pages=[0])
        mocked_responses.get(_page_url(1), json={"error": "page 1"}, status=401)
        # Pages 2-11 answer only after a page has failed, so pages 1-5 are the batch in flight when page 1 fails.
        self._hold(mocked_responses, page_failed, total, range(2, 12))
        # The pages that are never started are never requested.
        mocked_responses.assert_all_requests_are_fired = False

        result = make_pro_things(5).get_all(page_size=SIZE)

        assert (result.status_code, _page_of(result.url)) == (401, 1)
        assert result.json() == {"error": "page 1"}
        requested = [_page_of(call.request.url) for call in mocked_responses.calls]
        assert len(requested) <= 1 + 5
        assert len(requested) < 12
        assert max(requested) <= 5

    def test_a_failing_page_bounds_the_retries_that_follow_it(self, make_pro_things, mocked_responses, page_failed):
        total = 24
        attempts = RetryConfig().total + 1
        _register_pages(mocked_responses, total, pages=[0])
        mocked_responses.get(_page_url(1), json={"error": "page 1"}, status=503)
        self._hold(mocked_responses, page_failed, total, range(2, 12), status=503, body={"error": "later page"})
        mocked_responses.assert_all_requests_are_fired = False

        result = make_pro_things(5).get_all(page_size=SIZE)

        assert (result.status_code, _page_of(result.url)) == (503, 1)
        # Page 0 once, then pages 1-5 at most, each retried on its own: not the 1 + 11 * attempts of fetching all.
        assert len(mocked_responses.calls) <= 1 + 5 * attempts
        assert len(mocked_responses.calls) < 1 + 11 * attempts

    def test_the_lowest_failed_page_wins_even_when_a_later_one_failed_first(self, make_pro_things, mocked_responses, page_failed):
        total = 24
        _register_pages(mocked_responses, total, pages=[0, 2])
        # Page 3 fails at once, and that failure is what releases page 1, so page 1 fails second.
        self._hold(mocked_responses, page_failed, total, [1], status=401, body={"error": "page 1"})
        mocked_responses.get(_page_url(3), json={"error": "page 3"}, status=403)
        self._hold(mocked_responses, page_failed, total, range(4, 12))
        mocked_responses.assert_all_requests_are_fired = False

        result = make_pro_things(5).get_all(page_size=SIZE)

        assert (result.status_code, _page_of(result.url)) == (401, 1)
        assert result.json() == {"error": "page 1"}

    def test_a_page_repeating_page_0_stops_with_a_warning(self, make_pro_things, mocked_responses, caplog):
        same = {"totalCount": 8, "results": [{"id": 0}, {"id": 1}]}
        for page in range(4):
            mocked_responses.get(_page_url(page), json=same)
        things = make_pro_things(5)
        caplog.set_level(logging.WARNING, logger="jamfpy.test-pro")

        result = things.get_all(page_size=SIZE)

        assert result.json() == {"totalCount": 2, "results": [{"id": 0}, {"id": 1}]}
        assert sorted(_page_of(call.request.url) for call in mocked_responses.calls) == [0, 1, 2, 3]
        [warning] = caplog.records
        assert warning.levelno == logging.WARNING
        assert "repeated page 0's results" in warning.getMessage()
        assert _page_url(1) in warning.getMessage()
        assert warning.getMessage().endswith("the server appears to ignore page: 2 results from page 0 returned")

    def test_without_total_count_pages_are_walked_one_at_a_time(self, make_pro_things, mocked_responses, executors):
        for page, ids in enumerate([[0, 1], [2, 3], [4]]):
            mocked_responses.get(_page_url(page), json={"results": [{"id": i} for i in ids]})

        result = make_pro_things(5).get_all(page_size=SIZE)

        assert _ids(result) == [0, 1, 2, 3, 4]
        assert [_page_of(call.request.url) for call in mocked_responses.calls] == [0, 1, 2]
        assert not executors

    def test_a_retried_page_still_aggregates_and_the_retry_warning_names_it(self, make_pro_things, mocked_responses, sleeps, caplog):
        _register_pages(mocked_responses, 7, pages=[0, 1, 3])
        # The default registry serves one URL's registrations in order: the 503, then the 200 for the retry.
        mocked_responses.get(_page_url(2), status=503)
        mocked_responses.get(_page_url(2), json=_page_body(2, 7))
        things = make_pro_things(5)
        caplog.set_level(logging.WARNING, logger="jamfpy.test-pro")

        result = things.get_all(page_size=SIZE)

        assert result.json() == {"totalCount": 7, "results": [{"id": i} for i in range(7)]}
        [retry] = caplog.records
        assert retry.url == _page_url(2)
        assert retry.getMessage().startswith(f"Retrying GET {_page_url(2)}: attempt 1 failed with HTTP 503")
        assert sleeps == [0.25]
