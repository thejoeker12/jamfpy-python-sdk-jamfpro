"""Unit tests for request hooks (jamfpy/client/hooks.py) and the points where ``API.do()`` fires them.

Hooks are registered on the ``tenant`` fixture's shared ``tenant.hooks``, or on a fresh ``Hooks`` passed to a
``ClassicAPI`` built by ``make_classic_api`` (recorded sleeps, no jitter randomness). ``responses`` answers
each attempt; when one URL is registered several times the default registry serves the registrations in
turn, so a test can script a retry (503, then 200).
"""
# pylint: disable=missing-function-docstring,protected-access,redefined-outer-name,unused-argument
import dataclasses
import logging
import threading
import time

import pytest
from requests import PreparedRequest, Request, Response
from requests.exceptions import ConnectionError as RequestsConnectionError, SSLError
from conftest import FQDN, THREADS, TOKEN_URL, register_oauth_token, run_together

import jamfpy
from jamfpy.client.hooks import Hooks, RequestContext
from jamfpy.client.retry import RetryConfig

COMPUTERS_URL = f"{FQDN}/JSSResource/computers"
PRO_BASE = f"{FQDN}/api/v1"
NO_JITTER = RetryConfig(jitter=False)


@pytest.fixture
def hooks():
    return Hooks()


@pytest.fixture
def events(hooks):
    """Register a hook of each kind on ``hooks`` that appends one tuple per call."""
    recorded = []

    @hooks.before_request
    def before(prepared, ctx):
        recorded.append(("before", ctx.attempt))

    @hooks.after_response
    def after(prepared, response, ctx):
        recorded.append(("after", ctx.attempt, response))

    @hooks.on_retry
    def retry(prepared, ctx, reason, delay):
        recorded.append(("retry", ctx.attempt, reason, delay))

    return recorded


def _get(api):
    return api.do(Request("GET", url=COMPUTERS_URL))


# --- what fires, in what order ----------------------------------------------

def test_hooks_fire_in_order_per_attempt(make_classic_api, hooks, events, mocked_responses):
    mocked_responses.get(COMPUTERS_URL, status=503)
    mocked_responses.get(COMPUTERS_URL, json={})

    result = _get(make_classic_api(retries=NO_JITTER, hooks=hooks))

    assert [event[:2] for event in events] == [("before", 1), ("after", 1), ("retry", 1), ("before", 2), ("after", 2)]
    first_response = events[1][2]
    assert first_response.status_code == 503
    # on_retry gets the very response after_response saw, and the delay about to be slept.
    assert events[2][2] is first_response
    assert events[2][3] == 0.5
    assert events[4][2] is result


def test_on_retry_fires_before_the_sleep(make_classic_api, hooks, mocked_responses):
    mocked_responses.get(COMPUTERS_URL, status=503)
    mocked_responses.get(COMPUTERS_URL, status=503)
    mocked_responses.get(COMPUTERS_URL, json={})
    # One list for both, so the order between the hook and the sleep is what gets asserted.
    order = []
    hooks.on_retry(lambda prepared, ctx, reason, delay: order.append(("on_retry", delay)))

    _get(make_classic_api(retries=NO_JITTER, hooks=hooks, sleep=lambda delay: order.append(("sleep", delay))))

    assert order == [("on_retry", 0.5), ("sleep", 0.5), ("on_retry", 1.0), ("sleep", 1.0)]


def test_on_retry_gets_the_exception_for_a_connection_retry(make_classic_api, hooks, events, mocked_responses):
    error = RequestsConnectionError("connection reset")
    mocked_responses.get(COMPUTERS_URL, body=error)
    mocked_responses.get(COMPUTERS_URL, json={})

    _get(make_classic_api(retries=NO_JITTER, hooks=hooks))

    # No after_response for the attempt whose send raised.
    assert [event[:2] for event in events] == [("before", 1), ("retry", 1), ("before", 2), ("after", 2)]
    assert events[1][2] is error
    assert events[1][3] == 0.5


def test_only_before_request_fires_when_the_send_raises_and_is_not_retried(make_classic_api, hooks, events, mocked_responses):
    mocked_responses.get(COMPUTERS_URL, body=SSLError("certificate verify failed"))

    with pytest.raises(SSLError):
        _get(make_classic_api(retries=NO_JITTER, hooks=hooks))

    assert events == [("before", 1)]


def test_after_response_fires_for_an_error_status(make_classic_api, hooks, events, mocked_responses):
    mocked_responses.get(COMPUTERS_URL, status=404)

    _get(make_classic_api(retries=NO_JITTER, hooks=hooks))

    assert [event[:2] for event in events] == [("before", 1), ("after", 1)]
    assert events[1][2].status_code == 404


def test_hooks_receive_the_prepared_request_with_its_authorization(tenant, classic_api, mocked_responses):
    mocked_responses.get(COMPUTERS_URL, json={})
    seen = []
    tenant.hooks.before_request(lambda prepared, ctx: seen.append(prepared))

    _get(classic_api)

    assert isinstance(seen[0], PreparedRequest)
    assert seen[0].url == COMPUTERS_URL
    assert seen[0].headers["Authorization"] == mocked_responses.calls[-1].request.headers["Authorization"]


def test_hook_return_values_are_ignored(make_classic_api, hooks, mocked_responses):
    mocked_responses.get(COMPUTERS_URL, json={"computers": []})
    hooks.before_request(lambda prepared, ctx: "ignored")
    hooks.after_response(lambda prepared, response, ctx: Response())

    assert _get(make_classic_api(hooks=hooks)).json() == {"computers": []}


# --- context ---------------------------------------------------------------

def test_context_names_the_api_and_tenant(tenant, pro_api, classic_api, mocked_responses):
    mocked_responses.get(f"{PRO_BASE}/scripts/1", json={})
    mocked_responses.get(f"{FQDN}/JSSResource/computers/id/2", json={})
    contexts = []
    tenant.hooks.before_request(lambda prepared, ctx: contexts.append(ctx))

    pro_api.scripts.get_by_id(1)
    classic_api.computers.get_by_id(2)

    assert [ctx.api for ctx in contexts] == ["pro", "classic"]
    assert {ctx.tenant for ctx in contexts} == {FQDN}


def test_context_attempt_increments_and_started_is_monotonic(make_classic_api, hooks, mocked_responses):
    for status in (503, 503, 200):
        mocked_responses.get(COMPUTERS_URL, status=status)
    contexts = []
    hooks.before_request(lambda prepared, ctx: contexts.append(ctx))
    before = time.monotonic()

    _get(make_classic_api(retries=NO_JITTER, hooks=hooks))

    assert [ctx.attempt for ctx in contexts] == [1, 2, 3]
    started = [ctx.started for ctx in contexts]
    assert all(isinstance(value, float) for value in started)
    assert before <= started[0] <= started[1] <= started[2] <= time.monotonic()


def test_request_context_is_frozen():
    ctx = RequestContext(tenant=FQDN, api="pro", attempt=1, started=0.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.attempt = 2  # type: ignore[misc]  # a frozen field: the assignment is what the test checks


# --- failing hooks -----------------------------------------------------------

@pytest.fixture
def retried_api(make_classic_api, hooks, mocked_responses, warning_logger):
    """A ``ClassicAPI`` on ``hooks`` whose first attempt gets a 503 and its second a 200, logging at WARNING."""
    mocked_responses.get(COMPUTERS_URL, status=503)
    mocked_responses.get(COMPUTERS_URL, json={})
    return make_classic_api(retries=NO_JITTER, hooks=hooks, logger=warning_logger)


@pytest.mark.parametrize("kind", ["before_request", "after_response", "on_retry"])
def test_a_raising_hook_is_logged_and_the_request_carries_on(retried_api, hooks, events, caplog, kind):
    def broken(*args):
        raise RuntimeError("hook bug")

    getattr(hooks, kind)(broken)

    result = _get(retried_api)

    assert result.status_code == 200
    # The recording hooks registered before it still ran for both attempts.
    assert [event[:2] for event in events] == [("before", 1), ("after", 1), ("retry", 1), ("before", 2), ("after", 2)]
    hook_warnings = [r for r in caplog.records if "Request hook" in r.getMessage()]
    assert hook_warnings
    assert all(r.levelno == logging.WARNING for r in hook_warnings)
    assert all(broken.__qualname__ in r.getMessage() for r in hook_warnings)
    assert hook_warnings[0].exc_info[0] is RuntimeError


def test_a_raising_callable_without_a_qualname_is_logged_by_repr(make_classic_api, hooks, mocked_responses, warning_logger, caplog):
    class Broken:
        """A callable instance: instances carry no __qualname__ of their own."""
        def __call__(self, *args):
            raise RuntimeError("hook bug")

        def __repr__(self):
            return "<Broken hook>"

    mocked_responses.get(COMPUTERS_URL, json={})
    hooks.before_request(Broken())

    assert _get(make_classic_api(hooks=hooks, logger=warning_logger)).status_code == 200
    assert ["<Broken hook>" in r.getMessage() for r in caplog.records if r.levelno == logging.WARNING] == [True]


# --- registration -----------------------------------------------------------

def test_tenant_hooks_work_as_decorators_across_both_apis(tenant, pro_api, classic_api, mocked_responses):
    mocked_responses.get(f"{PRO_BASE}/scripts/1", json={})
    mocked_responses.get(f"{FQDN}/JSSResource/computers/id/2", json={})
    seen = []

    @tenant.hooks.before_request
    def record(prepared, ctx):
        seen.append(prepared.url)

    # The decorator hands the function back unchanged.
    assert record.__name__ == "record"
    pro_api.scripts.get_by_id(1)
    classic_api.computers.get_by_id(2)

    assert seen == [f"{PRO_BASE}/scripts/1", f"{FQDN}/JSSResource/computers/id/2"]


def test_tenant_shares_one_hooks_object_between_both_apis(tenant):
    assert isinstance(tenant.hooks, Hooks)
    assert tenant.pro._hooks is tenant.hooks
    assert tenant.classic._hooks is tenant.hooks


def test_an_api_without_hooks_gets_a_private_empty_registry(tenant, make_classic_api, mocked_responses):
    seen = []
    tenant.hooks.before_request(lambda prepared, ctx: seen.append(prepared.url))
    mocked_responses.get(COMPUTERS_URL, json={})

    api = make_classic_api()
    _get(api)

    assert isinstance(api._hooks, Hooks)
    assert api._hooks is not tenant.hooks
    assert not seen


def test_remove_unregisters_from_every_list(make_classic_api, hooks, mocked_responses):
    mocked_responses.get(COMPUTERS_URL, status=503)
    mocked_responses.get(COMPUTERS_URL, json={})
    calls = []

    def everywhere(*args):
        calls.append(len(args))

    for register in (hooks.before_request, hooks.after_response, hooks.on_retry, hooks.before_request):
        register(everywhere)
    hooks.remove(everywhere)
    _get(make_classic_api(retries=NO_JITTER, hooks=hooks))

    assert not calls


def test_remove_of_an_unregistered_function_does_nothing(hooks):
    hooks.remove(lambda prepared, ctx: None)


def test_a_hook_can_remove_itself(make_classic_api, hooks, mocked_responses):
    mocked_responses.get(COMPUTERS_URL, status=503)
    mocked_responses.get(COMPUTERS_URL, json={})
    seen = []

    def once(prepared, ctx):
        seen.append(ctx.attempt)
        hooks.remove(once)

    hooks.before_request(once)
    _get(make_classic_api(retries=NO_JITTER, hooks=hooks))

    assert seen == [1]


def test_a_hook_registered_during_dispatch_runs_from_the_next_request(make_classic_api, hooks, mocked_responses):
    mocked_responses.get(COMPUTERS_URL, json={})
    ran = []

    def late(prepared, ctx):
        ran.append("late")

    def registrar(prepared, ctx):
        ran.append("registrar")
        if ran.count("registrar") == 1:
            hooks.before_request(late)

    hooks.before_request(registrar)
    api = make_classic_api(hooks=hooks)

    _get(api)
    # Dispatch walks a snapshot, so the hook added mid-dispatch has not run yet.
    assert ran == ["registrar"]

    _get(api)
    assert ran == ["registrar", "registrar", "late"]


def test_a_hook_that_registers_itself_runs_once_per_dispatch(make_classic_api, hooks, mocked_responses):
    mocked_responses.get(COMPUTERS_URL, json={})
    calls = []

    def again(prepared, ctx):
        calls.append(ctx.attempt)
        # Bounded, so a dispatch over the live list fails the assertion below instead of looping forever.
        if len(calls) < 5:
            hooks.before_request(again)

    hooks.before_request(again)
    _get(make_classic_api(hooks=hooks))

    assert calls == [1]
    # The registration still took effect, for the next dispatch.
    assert hooks._before_request == [again, again]


def test_hooks_are_exported():
    assert jamfpy.Hooks is Hooks
    assert jamfpy.RequestContext is RequestContext


# --- scope -------------------------------------------------------------------

def test_auth_calls_never_fire_hooks(tenant, classic_api, mocked_responses):
    register_oauth_token(mocked_responses, token="fresh-token")
    register_oauth_token(mocked_responses, token="fresh-token")
    mocked_responses.get(COMPUTERS_URL, json={})
    seen = []
    tenant.hooks.before_request(lambda prepared, ctx: seen.append(("before", prepared.url)))
    tenant.hooks.after_response(lambda prepared, response, ctx: seen.append(("after", prepared.url)))

    tenant.authenticate()
    classic_api.auth.token_expiry = 0.0
    _get(classic_api)

    # Both token fetches went out (one explicit, one inside do()), and neither reached a hook.
    assert [call.request.url for call in mocked_responses.calls] == [TOKEN_URL, TOKEN_URL, COMPUTERS_URL]
    assert seen == [("before", COMPUTERS_URL), ("after", COMPUTERS_URL)]


def test_get_all_fires_hooks_once_per_page(tenant, pro_api, mocked_responses):
    page_0 = f"{PRO_BASE}/scripts?page=0&page-size=2"
    page_1 = f"{PRO_BASE}/scripts?page=1&page-size=2"
    mocked_responses.get(page_0, json={"totalCount": 3, "results": [{"id": "1"}, {"id": "2"}]})
    mocked_responses.get(page_1, json={"totalCount": 3, "results": [{"id": "3"}]})
    seen = []
    tenant.hooks.before_request(lambda prepared, ctx: seen.append(("before", prepared.url, ctx.attempt)))
    tenant.hooks.after_response(lambda prepared, response, ctx: seen.append(("after", prepared.url, ctx.attempt)))

    pro_api.scripts.get_all(page_size=2)

    assert seen == [("before", page_0, 1), ("after", page_0, 1), ("before", page_1, 1), ("after", page_1, 1)]


# --- threads -----------------------------------------------------------------

def test_hooks_are_thread_safe_while_others_register_and_remove(tenant, classic_api, mocked_responses):
    computers = mocked_responses.get(COMPUTERS_URL, json={})
    seen, seen_lock = [], threading.Lock()

    @tenant.hooks.after_response
    def count(prepared, response, ctx):
        with seen_lock:
            seen.append(response.status_code)

    def churn(*args):
        # Registered and removed by every worker while the others dispatch; also removes and re-adds itself
        # from inside a dispatch, so the lists change under every kind of concurrent access.
        tenant.hooks.remove(churn)
        tenant.hooks.before_request(churn)

    def worker():
        tenant.hooks.before_request(churn)
        tenant.hooks.after_response(churn)
        response = _get(classic_api)
        tenant.hooks.remove(churn)
        return response.status_code

    assert run_together(worker) == [200] * THREADS
    assert computers.call_count == THREADS
    assert seen == [200] * THREADS
    tenant.hooks.remove(churn)
    assert churn not in tenant.hooks._before_request + tenant.hooks._after_response
