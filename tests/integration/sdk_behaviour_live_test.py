"""Live checks of SDK behaviour the offline suite can only simulate against ``responses``.

Lazy auth against the real token endpoint, parallel pagination, request hooks over a whole lifecycle and token
invalidation on ``close()``. Marker-gated like everything under ``tests/integration`` (the conftest marks each
test). A test that needs its own ``Tenant`` builds it from the same environment variables as the session
``tenant`` fixture and closes it in a ``finally``; everything created goes through ``unique_name`` and ``janitor``.
"""
# pylint: disable=redefined-outer-name
import logging
import os
import threading
from collections import Counter
from urllib.parse import parse_qs, urlsplit

import pytest

import jamfpy

from .clc_resources_live_test import SPECS as CLASSIC_SPECS
from .conftest import REQUIRED_ENV
from .lifecycle import resolve_accessor, run_classic_lifecycle

pytestmark = pytest.mark.integration


def _env_tenant(**options) -> jamfpy.Tenant:
    """A second live ``Tenant``, built from the environment as the session ``tenant`` fixture builds its own."""
    missing = [k for k in REQUIRED_ENV if not os.environ.get(k)]
    if missing:
        pytest.fail(f"live-tenant env vars not set: {', '.join(missing)}", pytrace=False)
    fqdn = os.environ["JAMFPRO_INSTANCE_FQDN"]
    if not fqdn.startswith("http"):
        fqdn = f"https://{fqdn}"
    return jamfpy.Tenant(
        fqdn=fqdn,
        auth_method="oauth2",
        client_id=os.environ["JAMFPRO_CLIENT_ID"],
        client_secret=os.environ["JAMFPRO_CLIENT_SECRET"],
        **options,
    )


def test_tenant_fetches_its_token_on_the_first_request():
    """Tenant() sends nothing; the first API request fetches the token from the real token endpoint."""
    live = _env_tenant()
    try:
        assert live.pro.auth is live.classic.auth
        assert live.pro.auth.token_expiry == 0.0, "Tenant() fetched a token at construction"

        resp = live.classic.categories.get_all()

        assert resp.status_code == 200, f"get_all: {resp.status_code}"
        assert live.pro.auth.token_expiry > 0
    finally:
        live.classic.close()


def test_parallel_get_all_matches_a_sequential_walk(tenant, unique_name, janitor):
    """get_all at parallelism 5 returns what a sequential walk does, one request per page, off the calling thread."""
    names = [f"{unique_name}-{i}" for i in range(1, 4)]
    for name in names:
        created = tenant.pro.scripts.create({"name": name})
        assert created.status_code == 201, f"create: {created.status_code} {created.text}"
        janitor.append((tenant.pro.scripts, created.json()["id"], (204, 404)))

    caller = threading.get_ident()
    # (page, attempt, thread) per request; list.append is atomic, so the page workers can share the list.
    seen = []

    def record_page(prepared, ctx):
        page = int(parse_qs(urlsplit(prepared.url).query)["page"][0])
        seen.append((page, ctx.attempt, threading.get_ident()))

    tenant.hooks.before_request(record_page)
    try:
        parallel = tenant.pro.scripts.get_all(page_size=1)
    finally:
        tenant.hooks.remove(record_page)

    sequential_tenant = _env_tenant(parallelism=1)
    try:
        sequential = sequential_tenant.pro.scripts.get_all(page_size=1)
    finally:
        sequential_tenant.classic.close()

    assert parallel.status_code == 200, f"parallel get_all: {parallel.status_code} {parallel.text}"
    assert sequential.status_code == 200, f"sequential get_all: {sequential.status_code} {sequential.text}"
    body, expected = parallel.json(), sequential.json()
    assert body["totalCount"] == expected["totalCount"] >= 3
    assert body["results"] == expected["results"]
    assert set(names) <= {script["name"] for script in body["results"]}
    # One first attempt per page; a retried page would add attempts above 1, which ctx.attempt tells apart.
    assert Counter(page for page, attempt, _ in seen if attempt == 1) == Counter(range(body["totalCount"]))
    assert any(thread != caller for _, _, thread in seen), "every page ran on the calling thread"


def test_hooks_see_every_request_of_a_classic_lifecycle(tenant, unique_name, janitor):
    """before_request and after_response fire once per request of a Classic lifecycle, and never for auth."""
    spec = next(spec for spec in CLASSIC_SPECS if spec["id"] == "categories")
    # A fresh, lazy Tenant: its first request fetches a token, which the hooks must not see.
    live = _env_tenant()
    before, after = [], []
    live.hooks.before_request(lambda prepared, ctx: before.append((prepared.method, prepared.url, ctx)))
    live.hooks.after_response(lambda prepared, response, ctx: after.append((prepared.method, response.status_code, ctx)))
    created = []
    try:
        run_classic_lifecycle(live.classic, spec, spec["min"], unique_name, created)
        assert live.classic.auth.token_expiry > 0
    finally:
        # live is closed before the janitor runs at teardown, so cleanup goes through the session tenant.
        janitor.extend((resolve_accessor(tenant.classic, spec["accessor"]), rid, ok) for _, rid, ok in created)
        live.classic.close()

    assert [method for method, _, _ in before] == ["POST", "GET", "PUT", "GET", "DELETE", "GET"]
    assert [(method, status) for method, status, _ in after] == [
        ("POST", 201), ("GET", 200), ("PUT", 201), ("GET", 200), ("DELETE", 200), ("GET", 404),
    ]
    contexts = [ctx for _, _, ctx in before + after]
    assert {(ctx.api, ctx.tenant, ctx.attempt) for ctx in contexts} == {("classic", live.fqdn, 1)}
    paths = [urlsplit(url).path for _, url, _ in before]
    assert all(path.startswith("/JSSResource/categories/id/") for path in paths), paths


def test_close_invalidates_the_token(caplog):
    """close() invalidates the token on the server; the next request is a 401, not a fresh token."""
    live = _env_tenant()
    try:
        first = live.classic.categories.get_all()
        assert first.status_code == 200, f"get_all: {first.status_code}"
    finally:
        # Keep only what close() logs: the token fetch above may log the one-time buffer-clamp WARNING.
        caplog.clear()
        live.classic.close()

    # close() logs a WARNING exactly when invalidate() returns False.
    assert not [record.getMessage() for record in caplog.records if record.levelno >= logging.WARNING]
    expiry = live.classic.auth.token_expiry

    # The cached token is dead now, and the SDK does not fetch another on a 401.
    after_close = live.classic.categories.get_all()

    assert after_close.status_code == 401, f"get_all after close: {after_close.status_code}"
    assert live.classic.auth.token_expiry == expiry
