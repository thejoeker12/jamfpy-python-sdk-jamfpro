"""Shared fixtures and helpers for the jamfpy unit suite.

Tests drive the real SDK stack (``Tenant`` -> ``Auth`` -> ``API.do()`` -> ``Session``)
and mock only the network edge, with ``responses``: it replaces
``HTTPAdapter.send``, so the auth calls (``requests.request()``) and every
endpoint call (``API.do()`` -> ``Session.send``) land in one ``RequestsMock``
that serves registered URLs and records each ``PreparedRequest`` in
``mocked_responses.calls``. An unregistered URL raises ``ConnectionError``, so
nothing can reach a live tenant.

``tenant`` is a real OAuth ``Tenant``, authenticated against a token endpoint
answered by ``mocked_responses``; ``pro_api`` and ``classic_api`` are its two
APIs, so an endpoint test sees the Authorization header the real ``Auth``
injects, and the fixture fails any test whose API call went out without it.
A test of lazy auth builds its own ``Tenant`` instead, and registers the token
endpoint only if it makes a request (every registration must be used). The TLS tests in
``api_test.py`` patch ``HTTPAdapter.send`` themselves instead, because they
assert the keyword arguments that reach the adapter.

This ``tenant`` is the offline one. ``tests/integration/conftest.py`` defines a
different fixture with the same name that builds a ``Tenant`` against a real
tenant from the environment.
"""
# pylint: disable=redefined-outer-name
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from importlib import metadata

import pytest
import responses
from requests.utils import default_headers
from responses.registries import FirstMatchRegistry

import jamfpy

FQDN = "https://test.jamfcloud.com"
TOKEN_URL = f"{FQDN}/api/oauth/token"
FAKE_TOKEN = "fake-access-token"
USER_AGENT = f"jamfpy/{metadata.version('jamfpy')}"
THREADS = 20
# Long enough that, without the Auth lock, every thread released together would reach the token endpoint.
SLOW_TOKEN_SECS = 0.2


def register_oauth_token(rsps, token=FAKE_TOKEN, expires_in=1800):
    """Answer the OAuth client-credentials request with a token; returns the registration (for ``call_count``)."""
    return rsps.post(
        TOKEN_URL,
        json={"access_token": token, "expires_in": expires_in, "token_type": "Bearer", "scope": "api-role:1"},
    )


def register_slow_oauth_token(rsps, token):
    """Answer the OAuth token request after ``SLOW_TOKEN_SECS``, so concurrent callers pile up behind it."""
    def callback(_request):
        time.sleep(SLOW_TOKEN_SECS)
        return 200, {}, json.dumps({"access_token": token, "expires_in": 1800})

    return rsps.add_callback(responses.POST, TOKEN_URL, callback=callback)


def run_together(fn):
    """Call ``fn`` from ``THREADS`` threads released at once by a barrier; return every thread's result."""
    barrier = threading.Barrier(THREADS, timeout=10)

    def worker():
        barrier.wait()
        return fn()

    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        futures = [pool.submit(worker) for _ in range(THREADS)]
        # Bounded, so a deadlock fails the test instead of hanging the suite.
        return [future.result(timeout=30) for future in futures]


def _lower_keys(headers):
    return {k.lower(): v for k, v in headers.items()}


def with_bearer(header_set):
    """Every header ``API.do()`` sends for an endpoint's header set, names lower-cased (see ``sent_headers``).

    The session's requests defaults with jamfpy's User-Agent, the endpoint's headers over them (so its ``accept``
    replaces the default ``Accept: */*``), and the Authorization header from the real Auth.
    """
    session_defaults = {**default_headers(), "User-Agent": USER_AGENT}
    return {**_lower_keys(session_defaults), **_lower_keys(header_set), "authorization": f"Bearer {FAKE_TOKEN}"}


def sent_headers(request):
    """A recorded request's headers minus Content-Length, which requests derives from the body.

    Names are lower-cased because HTTP header names are case-insensitive and requests keeps whichever spelling
    was set last, so an endpoint's ``accept`` over the session's ``Accept`` goes out as ``accept``.
    """
    return {k: v for k, v in _lower_keys(request.headers).items() if k != "content-length"}


def _assert_every_api_call_authorised(calls):
    """Fail if any call other than a token request lacks the Bearer token ``Auth`` was issued.

    The token is ``FAKE_TOKEN`` unless the test makes ``Auth`` fetch another, in which case a token
    the token endpoint handed out in the test is also accepted.
    """
    issued = {FAKE_TOKEN}
    issued.update(call.response.json()["access_token"] for call in calls if call.request.url == TOKEN_URL)
    accepted = {f"Bearer {token}" for token in issued}
    unauthorised = [
        f"{call.request.method} {call.request.url}"
        for call in calls
        if call.request.url != TOKEN_URL and call.request.headers.get("Authorization") not in accepted
    ]
    assert not unauthorised, f"requests sent without a Bearer token from Auth: {unauthorised}"


@pytest.fixture
def response_registry():
    """The ``responses`` registry class behind ``mocked_responses``.

    The default serves a matching registration for every request, however often it repeats.
    A module that must not loop forever on a repeated URL overrides this with ``OrderedRegistry``,
    which spends one registration per request, in order.
    """
    return FirstMatchRegistry


@pytest.fixture
def mocked_responses(response_registry):
    """An active ``RequestsMock``: registered URLs are served, anything else raises ``ConnectionError``.

    Every registration must be used, so a test cannot carry a dead one.
    """
    with responses.RequestsMock(registry=response_registry, assert_all_requests_are_fired=True) as rsps:
        yield rsps


@pytest.fixture
def tenant(mocked_responses):
    """A real OAuth ``Tenant``, authenticated against the mocked token endpoint.

    ``Tenant()`` is lazy, so the fixture calls ``authenticate()`` to fetch the token up front and then
    resets the call log: ``mocked_responses.calls`` holds only the requests the test itself triggers.
    The 1800 s token sits outside the (clamped 900 s) refresh buffer, so no test refetches it
    unless it moves ``token_expiry``.

    At teardown it asserts that every call the test made, bar token requests, carried the
    Authorization header, so an endpoint test cannot skip that check.
    """
    register_oauth_token(mocked_responses)
    built = jamfpy.Tenant(
        fqdn=FQDN,
        auth_method="oauth2",
        client_id="test-client-id",
        client_secret="test-client-secret",
        log_level=logging.CRITICAL,
    )
    built.authenticate()
    mocked_responses.calls.reset()
    yield built
    _assert_every_api_call_authorised(mocked_responses.calls)


@pytest.fixture
def pro_api(tenant):
    """The tenant's real ``ProAPI``."""
    return tenant.pro


@pytest.fixture
def classic_api(tenant):
    """The tenant's real ``ClassicAPI``."""
    return tenant.classic


@pytest.fixture
def silent_logger():
    """A no-output logger to inject where constructors accept ``logger=``."""
    logger = logging.getLogger("jamfpy-test")
    logger.handlers.clear()
    logger.addHandler(logging.NullHandler())
    logger.setLevel(logging.CRITICAL)
    return logger
