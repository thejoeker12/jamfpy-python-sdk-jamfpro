"""Fixtures for the live integration suite.

Everything in this directory exercises a REAL Jamf Pro tenant, configured via
the ``JAMFPRO_INSTANCE_FQDN`` / ``JAMFPRO_CLIENT_ID`` / ``JAMFPRO_CLIENT_SECRET``
environment variables. Tests are marker-gated (``integration``) and deselected
by default — run them explicitly with ``pytest -m integration tests/integration``.

The per-resource specs and lifecycle runners live in ``lifecycle.py`` and the
``*_live_test.py`` modules; coverage is tracked in COVERAGE.md → *Live
integration test coverage*.
"""
# pylint: disable=redefined-outer-name
import os
import uuid

import pytest

import jamfpy

REQUIRED_ENV = ("JAMFPRO_INSTANCE_FQDN", "JAMFPRO_CLIENT_ID", "JAMFPRO_CLIENT_SECRET")


def pytest_collection_modifyitems(items):
    """Auto-mark every test under this directory so none can dodge the gate."""
    for item in items:
        if "tests/integration" in str(item.path):
            item.add_marker("integration")


@pytest.fixture(scope="session")
def tenant():
    """Live ``jamfpy.Tenant`` built from JAMFPRO_* env vars; token invalidated at teardown.

    Missing configuration fails the run in CI (misconfigured secrets must not go
    green) but skips locally so humans without creds just see skips.
    """
    missing = [k for k in REQUIRED_ENV if not os.environ.get(k)]
    if missing:
        msg = f"live-tenant env vars not set: {', '.join(missing)}"
        if os.environ.get("CI"):
            pytest.fail(msg, pytrace=False)
        pytest.skip(msg)

    fqdn = os.environ["JAMFPRO_INSTANCE_FQDN"]
    if not fqdn.startswith("http"):
        fqdn = f"https://{fqdn}"

    live_tenant = jamfpy.Tenant(
        fqdn=fqdn,
        auth_method="oauth2",
        client_id=os.environ["JAMFPRO_CLIENT_ID"],
        client_secret=os.environ["JAMFPRO_CLIENT_SECRET"],
    )
    yield live_tenant
    # pro and classic share one auth object; a single close invalidates the token.
    live_tenant.classic.close()


@pytest.fixture
def unique_name():
    """Collision-free resource name, traceable back to the CI run that made it."""
    run = os.environ.get("GITHUB_RUN_ID", "local")
    return f"jamfpy-it-{run}-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def janitor():
    """Collects ``(endpoint, id, ok_codes)``; deletes at teardown even if the test failed.

    Tests register right after a successful create. 404 is in every ok set so
    the happy path can delete in-test and assert the real status code; anything
    else surfaces as a loud cleanup error instead of a silently leaked resource.
    """
    records = []
    yield records
    failures = []
    for endpoint, rid, ok_codes in records:
        resp = endpoint.delete_by_id(rid)
        if resp.status_code not in ok_codes:
            failures.append(f"{endpoint.name()} id {rid}: {resp.status_code}")
    assert not failures, f"cleanup failed for: {failures}"
