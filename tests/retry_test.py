"""Unit tests for the retry policy (jamfpy/client/retry.py) and the retry loop it drives in ``API.do()``.

Each test builds a ``ClassicAPI`` on the ``tenant`` fixture's real ``Auth`` (``make_classic_api``) with its
own ``RetryConfig``, a recording ``sleep`` (the ``sleeps`` list) and a fixed ``random_source``, so no test
waits or depends on chance. ``responses`` answers every attempt; the ``OrderedRegistry`` override spends one registration per
attempt, in order, so a test states exactly what each attempt gets back, and an exception registered as
a ``body`` is raised from the send as a real network failure would be.
"""
# pylint: disable=missing-function-docstring,protected-access,redefined-outer-name
import dataclasses
import logging
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from http import HTTPStatus

import pytest
import requests
from requests import Request
from requests.exceptions import (
    ConnectionError as RequestsConnectionError, ConnectTimeout, InvalidURL, MissingSchema, ProxyError, ReadTimeout, SSLError,
)
from responses.registries import OrderedRegistry
from conftest import FAKE_TOKEN, FQDN, TOKEN_URL, register_oauth_token

import jamfpy
from jamfpy.client.exceptions import JamfAuthError
from jamfpy.client.retry import RetryConfig, RetryPolicy, backoff_delay, parse_retry_after

COMPUTERS_URL = f"{FQDN}/JSSResource/computers"
NO_JITTER = RetryConfig(jitter=False)


@pytest.fixture
def response_registry():
    """One registration per attempt, in order; a surplus attempt finds nothing and fails the test."""
    return OrderedRegistry


def _get(api):
    return api.do(Request("GET", url=COMPUTERS_URL))


def _post(api):
    return api.do(Request("POST", url=COMPUTERS_URL, data="<computer/>"))


def _urls(mocked_responses):
    return [call.request.url for call in mocked_responses.calls]


# --- RetryConfig -----------------------------------------------------------

def test_retry_config_defaults():
    config = RetryConfig()
    assert dataclasses.astuple(config) == (
        3, 0.5, 30.0, True, (429, 500, 502, 503, 504), ("GET", "HEAD", "OPTIONS", "PUT", "DELETE"), False,
    )


def test_retry_config_is_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        RetryConfig().total = 5  # type: ignore[misc]  # a frozen field: the assignment is what the test checks


# --- RetryConfig validation ------------------------------------------------

@pytest.mark.parametrize("field, value", [
    ("total", -1), ("total", 1.5), ("total", "3"), ("total", None), ("total", True),
    ("backoff_factor", -0.1), ("backoff_factor", "0.5"), ("backoff_factor", None), ("backoff_factor", float("nan")),
    ("max_backoff", -1), ("max_backoff", "30"), ("max_backoff", None), ("max_backoff", float("nan")),
])
def test_retry_config_rejects_a_bad_number(field, value):
    with pytest.raises(ValueError, match=field):
        RetryConfig(**{field: value})


@pytest.mark.parametrize("field, value", [
    ("statuses", 429), ("statuses", None), ("statuses", (429, "500")), ("statuses", [None]), ("statuses", (True,)),
    ("methods", 5), ("methods", None), ("methods", ("GET", 1)), ("methods", [None]),
])
def test_retry_config_rejects_a_bad_collection(field, value):
    with pytest.raises(ValueError, match=field):
        RetryConfig(**{field: value})


def test_retry_config_explains_the_tuple_form_for_a_bare_string():
    with pytest.raises(ValueError, match=r"methods must be a tuple of str, not a bare string; for one value write methods=\('GET',\)"):
        RetryConfig(methods="GET")  # type: ignore[arg-type]  # the bare string is the mistake under test


@pytest.mark.parametrize("field, value", [("statuses", "429"), ("statuses", b"429"), ("methods", b"GET")])
def test_retry_config_rejects_other_bare_strings(field, value):
    with pytest.raises(ValueError, match=f"{field} must be a tuple of .*, not a bare string"):
        RetryConfig(**{field: value})


def test_retry_config_allows_zero_and_stores_collections_as_tuples():
    config = RetryConfig(total=0, backoff_factor=0, max_backoff=0, statuses=[429, HTTPStatus.BAD_GATEWAY], methods={"get"})

    assert config.statuses == (429, 502)
    assert config.methods == ("get",)
    assert isinstance(config.statuses, tuple)
    # Tuples, not whatever the caller passed, so the frozen config stays hashable.
    assert isinstance(hash(config), int)


def test_tenant_passes_retries_to_both_apis():
    config = RetryConfig(total=1)
    tenant = jamfpy.Tenant(fqdn=FQDN, auth_method="oauth2", client_id="id", client_secret="secret",
                           log_level=logging.CRITICAL, retries=config)
    assert tenant.pro._retry.config is config
    assert tenant.classic._retry.config is config


def test_tenant_retries_default_on_and_none_turns_them_off():
    on = jamfpy.Tenant(fqdn=FQDN, auth_method="oauth2", client_id="id", client_secret="secret", log_level=logging.CRITICAL)
    off = jamfpy.Tenant(fqdn=FQDN, auth_method="oauth2", client_id="id", client_secret="secret", log_level=logging.CRITICAL,
                        retries=None)
    assert on.pro._retry.config == RetryConfig()
    assert off.pro._retry is None
    assert off.classic._retry is None


# --- backoff ---------------------------------------------------------------

def test_status_retry_then_success_sleeps_backoff_factor(make_classic_api, mocked_responses, sleeps):
    mocked_responses.get(COMPUTERS_URL, status=503)
    mocked_responses.get(COMPUTERS_URL, json={"computers": []})

    result = _get(make_classic_api(retries=NO_JITTER))

    assert result.status_code == 200
    assert _urls(mocked_responses) == [COMPUTERS_URL, COMPUTERS_URL]
    assert sleeps == [0.5]


def test_jitter_scales_the_delay_by_the_random_source(make_classic_api, mocked_responses, sleeps):
    mocked_responses.get(COMPUTERS_URL, status=503)
    mocked_responses.get(COMPUTERS_URL, json={})

    _get(make_classic_api(retries=RetryConfig(), random_source=lambda: 0.5))

    assert sleeps == [0.25]


def test_delay_doubles_and_is_capped_at_max_backoff(make_classic_api, mocked_responses, sleeps):
    for _ in range(4):
        mocked_responses.get(COMPUTERS_URL, status=503)

    _get(make_classic_api(retries=RetryConfig(backoff_factor=1.0, max_backoff=3.0, jitter=False)))

    assert sleeps == [1.0, 2.0, 3.0]


def test_backoff_caps_before_applying_jitter():
    # Full jitter: uniform over [0, min(cap, backoff)], so half of a 30 s cap is 15 s, not min(30, 40 * 0.5) = 20 s.
    assert backoff_delay(RetryConfig(backoff_factor=5.0, max_backoff=30.0), 4, lambda: 0.5) == 15.0


def test_total_bounds_the_attempts_and_returns_the_last_response(make_classic_api, mocked_responses, sleeps):
    for attempt in range(1, 5):
        mocked_responses.get(COMPUTERS_URL, status=503, body=f"attempt {attempt}")

    result = _get(make_classic_api(retries=NO_JITTER))

    assert result.status_code == 503
    assert result.text == "attempt 4"
    assert len(mocked_responses.calls) == 4
    assert sleeps == [0.5, 1.0, 2.0]


def test_default_tenant_api_retries_without_sleeping_in_tests(classic_api, mocked_responses, sleeps):
    for _ in range(4):
        mocked_responses.get(COMPUTERS_URL, status=500)

    assert _get(classic_api).status_code == 500
    assert len(sleeps) == 3


def test_retries_none_makes_one_attempt(make_classic_api, mocked_responses, sleeps):
    mocked_responses.get(COMPUTERS_URL, status=503)

    assert _get(make_classic_api(retries=None)).status_code == 503
    assert len(mocked_responses.calls) == 1
    assert not sleeps


def test_retries_none_raises_a_connection_error_at_once(make_classic_api, mocked_responses, sleeps):
    mocked_responses.get(COMPUTERS_URL, body=RequestsConnectionError("down"))

    with pytest.raises(RequestsConnectionError):
        _get(make_classic_api(retries=None))
    assert not sleeps


@pytest.mark.parametrize("status", [200, 400, 401, 404, 501])
def test_unlisted_status_is_returned_at_once(make_classic_api, mocked_responses, sleeps, status):
    # A Retry-After on a status that isn't retried changes nothing.
    mocked_responses.get(COMPUTERS_URL, status=status, headers={"Retry-After": "1"})

    assert _get(make_classic_api(retries=NO_JITTER)).status_code == status
    assert len(mocked_responses.calls) == 1
    assert not sleeps


def test_unlisted_method_is_not_retried(make_classic_api, mocked_responses, sleeps):
    mocked_responses.patch(COMPUTERS_URL, status=503)

    assert make_classic_api(retries=NO_JITTER).do(Request("PATCH", url=COMPUTERS_URL)).status_code == 503
    assert not sleeps


def test_methods_match_case_insensitively(make_classic_api, mocked_responses, sleeps):
    mocked_responses.get(COMPUTERS_URL, status=503)
    mocked_responses.get(COMPUTERS_URL, json={})

    _get(make_classic_api(retries=RetryConfig(jitter=False, methods=("get",))))

    assert sleeps == [0.5]


# --- Retry-After -----------------------------------------------------------

def test_retry_after_seconds_replace_the_delay(make_classic_api, mocked_responses, sleeps):
    mocked_responses.get(COMPUTERS_URL, status=429, headers={"Retry-After": "2"})
    mocked_responses.get(COMPUTERS_URL, json={})

    # Jitter on: the server's value is used as given, not jittered.
    assert _get(make_classic_api(retries=RetryConfig())).status_code == 200
    assert sleeps == [2.0]


def test_retry_after_http_date_replaces_the_delay(make_classic_api, mocked_responses, sleeps):
    now = datetime.now(timezone.utc)
    retry_at = format_datetime(now + timedelta(seconds=5), usegmt=True)
    mocked_responses.get(COMPUTERS_URL, status=503, headers={"Retry-After": retry_at})
    mocked_responses.get(COMPUTERS_URL, json={})

    _get(make_classic_api(retries=NO_JITTER))

    assert len(sleeps) == 1
    # HTTP-dates have one-second resolution, so the wait lands just under 5 s.
    assert 4.0 <= sleeps[0] <= 6.0


def test_retry_after_beyond_max_backoff_returns_at_once(make_classic_api, mocked_responses, sleeps, warning_logger, caplog):
    mocked_responses.get(COMPUTERS_URL, status=429, headers={"Retry-After": "120"})

    result = _get(make_classic_api(retries=RetryConfig(max_backoff=30.0), logger=warning_logger))

    assert result.status_code == 429
    assert len(mocked_responses.calls) == 1
    assert not sleeps
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    assert "retry after 120.0 s" in errors[0].getMessage()
    assert "max_backoff of 30.0 s" in errors[0].getMessage()


def test_retry_after_equal_to_max_backoff_is_honoured(make_classic_api, mocked_responses, sleeps):
    mocked_responses.get(COMPUTERS_URL, status=429, headers={"Retry-After": "30"})
    mocked_responses.get(COMPUTERS_URL, json={})

    result = _get(make_classic_api(retries=RetryConfig(max_backoff=30.0, jitter=False)))

    # Only a value beyond the cap ends the retries; one exactly at it is waited out.
    assert result.status_code == 200
    assert len(mocked_responses.calls) == 2
    assert sleeps == [30.0]


def test_unparseable_retry_after_falls_back_to_backoff(make_classic_api, mocked_responses, sleeps):
    mocked_responses.get(COMPUTERS_URL, status=503, headers={"Retry-After": "soon"})
    mocked_responses.get(COMPUTERS_URL, json={})

    _get(make_classic_api(retries=NO_JITTER))

    assert sleeps == [0.5]


FIXED_NOW = datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("value, expected", [
    (None, None),
    ("2", 2.0),
    (" 7 ", 7.0),
    ("0", 0.0),
    ("Thu, 15 Oct 2026 12:00:05 GMT", 5.0),
    # A "-0000" zone parses naive; it is still GMT.
    ("Thu, 15 Oct 2026 12:00:05 -0000", 5.0),
    ("Thu, 15 Oct 2026 11:59:00 GMT", 0.0),
    ("soon", None),
    ("", None),
    ("-1", None),
    ("1.5", None),
    ("\u0662", None),  # Arabic-Indic two: str.isdigit passes it, but RFC 9110 delay-seconds is ASCII only.
    ("\u00b2", None),  # Superscript two: str.isdigit passes it, int() would not.
])
def test_parse_retry_after(value, expected):
    assert parse_retry_after(value, FIXED_NOW) == expected


# --- POST opt-in ------------------------------------------------------------

def test_post_status_is_not_retried_by_default(make_classic_api, mocked_responses, sleeps):
    mocked_responses.post(COMPUTERS_URL, status=503)

    assert _post(make_classic_api(retries=NO_JITTER)).status_code == 503
    assert len(mocked_responses.calls) == 1
    assert not sleeps


def test_post_status_is_retried_with_retry_post(make_classic_api, mocked_responses, sleeps):
    mocked_responses.post(COMPUTERS_URL, status=503)
    mocked_responses.post(COMPUTERS_URL, status=201)

    assert _post(make_classic_api(retries=RetryConfig(jitter=False, retry_post=True))).status_code == 201
    assert sleeps == [0.5]


def test_post_connect_timeout_is_retried_without_retry_post(make_classic_api, mocked_responses, sleeps):
    mocked_responses.post(COMPUTERS_URL, body=ConnectTimeout("connect timed out"))
    mocked_responses.post(COMPUTERS_URL, status=201)

    assert _post(make_classic_api(retries=NO_JITTER)).status_code == 201
    assert sleeps == [0.5]


@pytest.mark.parametrize("error", [ReadTimeout, RequestsConnectionError, ProxyError])
def test_post_read_timeout_and_connection_error_need_retry_post(make_classic_api, mocked_responses, sleeps, error):
    mocked_responses.post(COMPUTERS_URL, body=error("may have reached the server"))

    with pytest.raises(error):
        _post(make_classic_api(retries=NO_JITTER))
    assert len(mocked_responses.calls) == 1
    assert not sleeps


@pytest.mark.parametrize("error", [ReadTimeout, RequestsConnectionError, ProxyError])
def test_post_read_timeout_and_connection_error_retried_with_retry_post(make_classic_api, mocked_responses, sleeps, error):
    mocked_responses.post(COMPUTERS_URL, body=error("may have reached the server"))
    mocked_responses.post(COMPUTERS_URL, status=201)

    assert _post(make_classic_api(retries=RetryConfig(jitter=False, retry_post=True))).status_code == 201
    assert sleeps == [0.5]


# --- exhaustion and exceptions that are never retried ---------------------

@pytest.mark.parametrize("error", [ConnectTimeout, ReadTimeout, RequestsConnectionError, ProxyError])
def test_connection_failures_raise_the_last_exception_when_exhausted(make_classic_api, mocked_responses, sleeps, error):
    raised = [error(f"attempt {attempt}") for attempt in range(1, 5)]
    for exc in raised:
        mocked_responses.get(COMPUTERS_URL, body=exc)

    with pytest.raises(error) as excinfo:
        _get(make_classic_api(retries=NO_JITTER))

    assert excinfo.value is raised[-1]
    assert len(sleeps) == RetryConfig().total


def test_ssl_error_propagates_without_a_retry(make_classic_api, mocked_responses, sleeps):
    mocked_responses.get(COMPUTERS_URL, body=SSLError("certificate verify failed"))

    with pytest.raises(SSLError):
        _get(make_classic_api(retries=NO_JITTER))
    assert len(mocked_responses.calls) == 1
    assert not sleeps


def test_invalid_url_from_the_send_propagates_without_a_retry(make_classic_api, mocked_responses, sleeps):
    mocked_responses.get(COMPUTERS_URL, body=InvalidURL("bad proxy URL"))

    with pytest.raises(InvalidURL):
        _get(make_classic_api(retries=NO_JITTER))
    assert len(mocked_responses.calls) == 1
    assert not sleeps


def test_missing_schema_propagates_before_any_send(make_classic_api, mocked_responses, sleeps):
    with pytest.raises(MissingSchema):
        make_classic_api(retries=NO_JITTER).do(Request("GET", url="test.jamfcloud.com/JSSResource/computers"))
    assert not mocked_responses.calls
    assert not sleeps


def test_policy_never_retries_an_exception_outside_the_rules(silent_logger):
    # do() only hands the policy the exceptions it covers; the policy still refuses anything else on its own.
    policy = RetryPolicy(RetryConfig(), sleep=lambda _: None, random_source=lambda: 0.5)
    prepped = Request("GET", url=COMPUTERS_URL).prepare()

    assert policy.delay(silent_logger, prepped, ValueError("not a network failure"), 1) is None
    assert policy.delay(silent_logger, prepped, RequestsConnectionError("reset"), 1) == 0.25


def test_other_request_exceptions_propagate_without_a_retry(make_classic_api, mocked_responses, sleeps):
    mocked_responses.get(COMPUTERS_URL, body=requests.exceptions.ChunkedEncodingError("truncated body"))

    with pytest.raises(requests.exceptions.ChunkedEncodingError):
        _get(make_classic_api(retries=NO_JITTER))
    assert not sleeps


# --- token -----------------------------------------------------------------

def test_each_attempt_reapplies_a_refreshed_token(tenant, make_classic_api, mocked_responses):
    api = make_classic_api(retries=NO_JITTER, hooks=tenant.hooks)
    mocked_responses.get(COMPUTERS_URL, status=503)
    register_oauth_token(mocked_responses, token="fresh-token")
    mocked_responses.get(COMPUTERS_URL, json={})

    @tenant.hooks.on_retry
    def expire_token(_prepared, _ctx, _reason, _delay):
        api.auth.token_expiry = 0.0

    assert _get(api).status_code == 200
    calls = mocked_responses.calls
    assert [call.request.url for call in calls] == [COMPUTERS_URL, TOKEN_URL, COMPUTERS_URL]
    assert calls[0].request.headers["Authorization"] == f"Bearer {FAKE_TOKEN}"
    assert calls[2].request.headers["Authorization"] == "Bearer fresh-token"


@pytest.mark.parametrize("token_answer, raised", [
    ({"status": 503}, JamfAuthError),
    ({"body": RequestsConnectionError("unreachable")}, RequestsConnectionError),
])
def test_auth_calls_are_never_retried(mocked_responses, sleeps, token_answer, raised):
    # Its own Tenant: the tenant fixture's teardown reads every token response as an issued token.
    mocked_responses.post(TOKEN_URL, **token_answer)
    tenant = jamfpy.Tenant(fqdn=FQDN, auth_method="oauth2", client_id="id", client_secret="secret",
                           log_level=logging.CRITICAL)
    tenant.classic._retry.sleep = sleeps.append

    with pytest.raises(raised):
        tenant.classic.computers.get_all()
    assert _urls(mocked_responses) == [TOKEN_URL]
    assert not sleeps


# --- logging ---------------------------------------------------------------

def test_each_retry_logs_a_warning_and_the_final_failure_an_error(make_classic_api, mocked_responses, warning_logger, caplog):
    for _ in range(3):
        mocked_responses.get(COMPUTERS_URL, status=503)

    _get(make_classic_api(retries=RetryConfig(total=2, jitter=False), logger=warning_logger))

    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    errors = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert len(warnings) == 2
    for attempt, (message, delay) in enumerate(zip(warnings, ["0.50 s", "1.00 s"]), start=1):
        assert "GET" in message
        assert COMPUTERS_URL in message
        assert f"attempt {attempt}" in message
        assert "HTTP 503" in message
        assert delay in message
    assert len(errors) == 1
    assert "after 3 attempt(s)" in errors[0]
    assert COMPUTERS_URL in errors[0]


def test_exhausted_connection_failure_logs_an_error_naming_the_exception(make_classic_api, mocked_responses, warning_logger, caplog):
    mocked_responses.get(COMPUTERS_URL, body=ConnectTimeout("connect timed out"))
    mocked_responses.get(COMPUTERS_URL, body=ConnectTimeout("connect timed out"))

    with pytest.raises(ConnectTimeout):
        _get(make_classic_api(retries=RetryConfig(total=1, jitter=False), logger=warning_logger))

    errors = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    assert "ConnectTimeout" in errors[0]


def test_a_retried_request_traces_every_attempt_at_debug(make_classic_api, mocked_responses, warning_logger, caplog):
    mocked_responses.get(COMPUTERS_URL, status=503)
    mocked_responses.get(COMPUTERS_URL, json={})
    api = make_classic_api(retries=NO_JITTER, logger=warning_logger)

    with caplog.at_level(logging.DEBUG, logger=warning_logger.name):
        _get(api)

    def step(stage, attempt):
        return f"{stage}: Method: GET at: {COMPUTERS_URL} with headers: [redacted] (attempt {attempt})"

    traced = [r.getMessage() for r in caplog.records if r.name == warning_logger.name and r.levelno == logging.DEBUG]
    # A 503 that is about to be retried is logged as a plain response, not a success.
    assert traced == [
        step("prepping", 1), step("sending", 1), f"Response: GET {COMPUTERS_URL} -> 503 (attempt 1)",
        step("prepping", 2), step("sending", 2), f"Response: GET {COMPUTERS_URL} -> 200 (attempt 2)",
    ]


def test_clean_first_attempt_logs_nothing_at_warning(make_classic_api, mocked_responses, warning_logger, caplog):
    mocked_responses.get(COMPUTERS_URL, json={})

    _get(make_classic_api(retries=RetryConfig(), logger=warning_logger))

    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
