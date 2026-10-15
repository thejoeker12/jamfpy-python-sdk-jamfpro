"""Unit tests for tools/introspect.py: the method and dummy-argument rules, the path normaliser and the request recorder.

The recorder runs on fixture endpoints over throwaway ``ProAPI`` / ``ClassicAPI`` objects. The ``responses`` mock is
active with nothing registered, so a request that escaped the stub would raise instead of leaving the process.
tests/contract_test.py and tools/coverage_doc.py use the same helpers on the real endpoints.
"""
# pylint: disable=missing-function-docstring,redefined-outer-name
import inspect

import pytest
from requests import Request, Response

import jamfpy
from jamfpy.endpoints.models import ClassicEndpoint, Endpoint, ProEndpoint
from tools import introspect
from tools.introspect import CONTRACT_ARG, EMPTY_PAGE, DummyValueError, Sent

FQDN = "https://introspect.invalid"


class Widgets(ProEndpoint):
    """A Pro CRUD fixture."""

    _uri = "/widgets"
    _name = "widgets"
    _version = "1"


class Gadgets(ClassicEndpoint):
    """A Classic CRUD fixture."""

    _uri = "/gadgets"
    _name = "gadgets"


class Verbs(Endpoint):
    """A fixture endpoint with one method for each thing the recorder has to handle."""

    _uri = "/verbs"
    label = "a public attribute that is not callable"

    def __init__(self, api) -> None:
        super().__init__(api)
        self.child = Widgets(api)
        self.fire = self.ping
        self.last: Response | None = None

    @staticmethod
    def shout() -> None:
        """Public and callable, so it is a method, though it needs no instance."""

    def _hidden(self) -> None:
        """Private: left out."""

    def ping(self) -> Response:
        self.last = self._api.do(Request("GET", url=self._api.url("1") + f"{self._uri}/ping?x=1&y=2"))
        return self.last

    def twice(self) -> Response:
        self._api.do(Request("GET", url=self._api.url("1") + self._uri))
        return self._api.do(Request("GET", url=self._api.url("1") + self._uri))

    def fan(self, ids: list[str], note: str = "n", *, force: bool) -> Response:
        self._api.do(Request("DELETE", url=self._api.url("2") + f"{self._uri}/{ids[0]}", params={"force": force}))
        return self._api.do(Request("POST", url=self._api.url("2") + self._uri, json={"note": note}))

    def quiet(self) -> None:
        """Sends nothing."""


class Failing(Endpoint):
    """A fixture endpoint whose method raises after sending."""

    _uri = "/failing"

    def explode(self) -> Response:
        self._api.do(Request("GET", url=self._api.url("1") + self._uri))
        raise RuntimeError("boom")


class Lost(Endpoint):
    """A fixture endpoint that sends a request with no URL."""

    _uri = "/lost"

    def wander(self) -> Response:
        return self._api.do(Request("GET"))


class Odd(Endpoint):
    """A fixture endpoint with a parameter the dummy-argument rules have no value for."""

    _uri = "/odd"

    def first(self) -> Response:
        return self._api.do(Request("GET", url=self._api.url("1") + self._uri))

    def lopsided(self, ratio: float) -> Response:
        return self._api.do(Request("GET", url=self._api.url("1") + f"{self._uri}/{ratio}"))


@pytest.fixture
def apis(mocked_responses):
    assert not mocked_responses.calls
    auth = jamfpy.OAuth(fqdn=FQDN, client_id="introspect", client_secret="introspect")
    return {"classic": jamfpy.ClassicAPI(fqdn=FQDN, auth=auth), "pro": jamfpy.ProAPI(fqdn=FQDN, auth=auth)}


# Methods


def test_public_methods_are_the_sorted_public_callables_except_name_and_nested_endpoints(apis):
    verbs = Verbs(apis["pro"])

    assert introspect.public_methods(verbs) == ("fan", "fire", "ping", "quiet", "shout", "twice")
    assert introspect.public_methods(Widgets(apis["pro"])) == ("create", "delete_by_id", "get_all", "get_by_id", "update_by_id")


# Dummy arguments


def sample(flag: bool, count: int, text: str, texts: list[str], mapping: dict[str, object]) -> None:
    del flag, count, text, texts, mapping


def test_dummy_arguments_build_a_value_per_type():
    assert introspect.dummy_arguments(sample) == ([False, 1, CONTRACT_ARG, [CONTRACT_ARG], {}], {})


def with_defaults(kept: int = 7, *rest: str, key: str, other: int = 3, **extra: int) -> None:  # pylint: disable=keyword-arg-before-vararg
    del kept, rest, key, other, extra


def test_dummy_arguments_let_a_default_win_and_skip_var_arguments():
    args, kwargs = introspect.dummy_arguments(with_defaults)

    assert args == [7]
    assert kwargs == {"key": CONTRACT_ARG, "other": 3}


def test_dummy_arguments_evaluate_string_annotations():
    def deferred(page: "int", names: "list[str]") -> None:
        del page, names

    assert introspect.dummy_arguments(deferred) == ([1, [CONTRACT_ARG]], {})


@pytest.mark.parametrize("annotation", [float, list[int], bytes, inspect.Parameter.empty])
def test_a_type_without_a_dummy_value_raises_a_type_error_naming_the_parameter(annotation):
    param = inspect.Parameter("ratio", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=annotation)

    with pytest.raises(DummyValueError, match=r"^no dummy value for parameter 'ratio' annotated .*: add one to dummy_value in tools/") as raised:
        introspect.dummy_value(param)

    assert isinstance(raised.value, TypeError)


# Paths


@pytest.mark.parametrize(("url", "api", "expected"), [
    (f"{FQDN}/api/v1/things?page=0&page-size=100", "pro", "/v1/things"),
    (f"{FQDN}/api/v2/things/123e4567-e89b-12d3-a456-426614174000", "pro", "/v2/things/{id}"),
    (f"{FQDN}/JSSResource/buildings/id/1", "classic", "/buildings/id/{id}"),
    (f"{FQDN}/JSSResource/accounts/username/{CONTRACT_ARG}", "classic", "/accounts/username/{id}"),
])
def test_sent_path_strips_the_base_and_query_and_normalises_ids(url, api, expected):
    assert introspect.sent_path(url, api) == expected


@pytest.mark.parametrize(("url", "api"), [
    (f"{FQDN}/JSSResource/buildings", "pro"),
    (f"{FQDN}/api/v1/things", "classic"),
    (f"{FQDN}/api", "pro"),
])
def test_sent_path_refuses_a_url_outside_the_api_base(url, api):
    with pytest.raises(ValueError, match=rf"^{FQDN}.* is not under the {api} base "):
        introspect.sent_path(url, api)


# Recording


def test_records_each_methods_distinct_requests_in_send_order_with_normalised_paths(apis):
    verbs = Verbs(apis["pro"])

    recorded = introspect.record_requests(verbs, "pro", apis["pro"])

    assert recorded == {
        # The id comes from the str dummy, the query is dropped, and a repeated request is listed once.
        "fan": (Sent("delete", "/v2/verbs/{id}"), Sent("post", "/v2/verbs")),
        "fire": (Sent("get", "/v1/verbs/ping"),),
        "ping": (Sent("get", "/v1/verbs/ping"),),
        "quiet": (),
        "shout": (),
        "twice": (Sent("get", "/v1/verbs"),),
    }
    assert list(recorded) == list(introspect.public_methods(verbs))


def test_the_stub_answers_with_an_ok_empty_first_page(apis):
    verbs = Verbs(apis["pro"])

    introspect.record_requests(verbs, "pro", apis["pro"])

    assert verbs.last is not None
    assert (verbs.last.status_code, verbs.last.ok, verbs.last.json()) == (200, True, EMPTY_PAGE)
    assert verbs.last.url == f"{FQDN}/api/v1/verbs/ping?x=1&y=2"


def test_a_paginating_get_all_stops_after_the_first_page(apis):
    recorded = introspect.record_requests(Widgets(apis["pro"]), "pro", apis["pro"])

    assert recorded == {
        "create": (Sent("post", "/v1/widgets"),),
        "delete_by_id": (Sent("delete", "/v1/widgets/{id}"),),
        "get_all": (Sent("get", "/v1/widgets"),),
        "get_by_id": (Sent("get", "/v1/widgets/{id}"),),
        "update_by_id": (Sent("put", "/v1/widgets/{id}"),),
    }


def test_classic_requests_are_recorded_under_the_jssresource_base(apis):
    recorded = introspect.record_requests(Gadgets(apis["classic"]), "classic", apis["classic"])

    assert recorded == {
        "create": (Sent("post", "/gadgets/id/{id}"),),
        "delete_by_id": (Sent("delete", "/gadgets/id/{id}"),),
        "get_all": (Sent("get", "/gadgets"),),
        "get_by_id": (Sent("get", "/gadgets/id/{id}"),),
        "update_by_id": (Sent("put", "/gadgets/id/{id}"),),
    }


def test_do_is_put_back_after_recording_even_when_a_method_raises(apis):
    pro = apis["pro"]
    real_do = pro.do

    introspect.record_requests(Verbs(pro), "pro", pro)
    assert "do" not in vars(pro) and pro.do == real_do

    with pytest.raises(RuntimeError, match="boom"):
        introspect.record_requests(Failing(pro), "pro", pro)
    assert "do" not in vars(pro) and pro.do == real_do


def test_a_request_with_no_url_is_refused_and_do_is_put_back(apis):
    with pytest.raises(ValueError, match="a request with no URL reached do"):
        introspect.record_requests(Lost(apis["pro"]), "pro", apis["pro"])

    assert "do" not in vars(apis["pro"])


def test_a_parameter_without_a_dummy_value_raises_before_that_method_sends(apis):
    odd = Odd(apis["pro"])

    with pytest.raises(DummyValueError, match="no dummy value for parameter 'ratio'"):
        introspect.record_requests(odd, "pro", apis["pro"])

    assert "do" not in vars(apis["pro"])


def test_recording_one_api_leaves_the_other_alone(apis):
    classic_do = apis["classic"].do

    introspect.record_requests(Verbs(apis["pro"]), "pro", apis["pro"])

    assert "do" not in vars(apis["classic"]) and apis["classic"].do == classic_do
