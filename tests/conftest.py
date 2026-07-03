"""Shared fixtures and test doubles for the jamfpy suite.

The SDK's only real work is assembling ``requests.Request`` objects and handing
them to a network layer, so nearly every test either records the Request an
endpoint builds (via ``FakeAPI``) or patches the two network boundaries
(``jamfpy.client.auth.request`` and ``API._session.send``). Nothing here touches
a live tenant.
"""
# pylint: disable=protected-access,too-few-public-methods
import json
import logging

import pytest
from requests import Response

from jamfpy.client.constants import DEFAULT_HTTP_CONFIG_HEADERS

FQDN = "https://test.jamfcloud.com"


def make_response(json_body=None, status=200, encoding="utf-8", headers=None, url=f"{FQDN}/x"):
    """Build a real ``requests.Response`` with a JSON body for offline tests.

    Used where the code under test actually reads the response (``.ok``,
    ``.json()``, ``.raise_for_status()``) — the transforming endpoints and auth.
    """
    resp = Response()
    resp.status_code = status
    resp.encoding = encoding
    resp.url = url
    if headers:
        resp.headers.update(headers)
    if json_body is not None:
        resp._content = json.dumps(json_body).encode(encoding)
    return resp


class FakeAPI:
    """Stand-in for ``ClassicAPI``/``ProAPI`` that records the Requests it's handed.

    Endpoints only ever call ``url()``, ``header()`` and ``do()`` on their API,
    so this is enough to unit-test request construction in isolation.
    """

    def __init__(self, responses=None):
        self.requests = []
        self._responses = list(responses) if responses is not None else []
        # Returned by do() when no explicit response queue is supplied; most
        # endpoint tests assert on the recorded Request, not the return value.
        self.default_response = object()

    @property
    def last_request(self):
        """The most recently recorded Request, or None."""
        return self.requests[-1] if self.requests else None

    def url(self, target=None):
        """Mimic ``API.url``: classic ignores target, pro formats the version in."""
        if target is None:
            return f"{FQDN}/JSSResource"
        return f"{FQDN}/api/v{target}"

    def header(self, key):
        """Return the real CRUD header set so header shape matches production."""
        return DEFAULT_HTTP_CONFIG_HEADERS["crud"][key]

    def do(self, request):
        """Record the Request and return the next queued (or default) response."""
        self.requests.append(request)
        if self._responses:
            return self._responses.pop(0)
        return self.default_response


@pytest.fixture
def fake_api():
    """A fresh recording FakeAPI per test."""
    return FakeAPI()


@pytest.fixture
def silent_logger():
    """A no-output logger to inject where constructors accept ``logger=``."""
    logger = logging.getLogger("jamfpy-test")
    logger.handlers.clear()
    logger.addHandler(logging.NullHandler())
    logger.setLevel(logging.CRITICAL)
    return logger
