"""Shared fixtures and helpers for the jamfpy unit suite.

Tests drive the real SDK stack (``Tenant`` -> ``Auth`` -> ``API.do()`` -> ``Session``)
and mock only the network edge, with ``responses``: it replaces
``HTTPAdapter.send``, so the auth calls (``requests.request()``) and every
endpoint call (``API.do()`` -> ``Session.send``) land in one ``RequestsMock``
that serves registered URLs and records each ``PreparedRequest`` in
``mocked_responses.calls``. An unregistered URL raises ``ConnectionError``, so
nothing can reach a live tenant.

``tenant`` is a real OAuth ``Tenant`` whose token request is answered by
``mocked_responses``; ``pro_api`` and ``classic_api`` are its two APIs, so an
endpoint test sees the Authorization header the real ``Auth`` injects, and the
fixture fails any test whose API call went out without it. The TLS tests in
``api_test.py`` patch ``HTTPAdapter.send`` themselves instead, because they
assert the keyword arguments that reach the adapter.

This ``tenant`` is the offline one. ``tests/integration/conftest.py`` defines a
different fixture with the same name that builds a ``Tenant`` against a real
tenant from the environment.
"""
# pylint: disable=redefined-outer-name
import logging

import pytest
import responses
from responses.registries import FirstMatchRegistry

import jamfpy

FQDN = "https://test.jamfcloud.com"
TOKEN_URL = f"{FQDN}/api/oauth/token"
FAKE_TOKEN = "fake-access-token"


def register_oauth_token(rsps, token=FAKE_TOKEN, expires_in=1800):
    """Answer the OAuth client-credentials request with a token; returns the registration (for ``call_count``)."""
    return rsps.post(
        TOKEN_URL,
        json={"access_token": token, "expires_in": expires_in, "token_type": "Bearer", "scope": "api-role:1"},
    )


def with_bearer(header_set):
    """An endpoint's header set plus the Authorization header ``API.do()`` adds from the real Auth."""
    return {**header_set, "Authorization": f"Bearer {FAKE_TOKEN}"}


def sent_headers(request):
    """A recorded request's headers minus Content-Length, which requests derives from the body."""
    return {k: v for k, v in request.headers.items() if k.lower() != "content-length"}


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
    """A real OAuth ``Tenant`` built against the mocked token endpoint.

    ``Tenant()`` fetches its token at construction, so the call log is reset afterwards:
    ``mocked_responses.calls`` then holds only the requests the test itself triggers.
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
