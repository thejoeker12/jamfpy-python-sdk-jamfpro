"""Offline smoke tests for the scripts in ``examples/``.

Each test sets the example's environment variables, registers with ``responses`` exactly the requests the example
sends, runs its ``main()`` and asserts on what was sent (method, URL and, for the writes, the body) and on what it
printed. The examples are standalone scripts, not a package, so they are imported by file path.

Two autouse fixtures keep the runs offline and instant: the environment is pinned (credentials set, the CA and
proxy variables requests reads cleared), and ``jamfpy.Tenant`` is swapped for a subclass whose retry loop records
its backoff delays in ``sleeps`` instead of sleeping. ``responses`` raises on any unregistered URL, so nothing
reaches a network. ``test_every_example_has_a_test`` fails when an ``examples/*.py`` has no ``test_<name>`` here.
"""
# pylint: disable=redefined-outer-name,protected-access
import base64
import datetime
import importlib.util
import json
import secrets
import time
from collections import Counter
from pathlib import Path
from urllib.parse import parse_qs

import pytest
import requests
import responses
from conftest import FAKE_TOKEN, FQDN, TOKEN_URL, register_oauth_token

import jamfpy

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
CLIENT_ID = "example-client-id"
CLIENT_SECRET = "example-client-secret"
INVALIDATE_URL = f"{FQDN}/api/v1/auth/invalidate-token"
BEARER_URL = f"{FQDN}/api/v1/auth/token"
CLASSIC = f"{FQDN}/JSSResource"
PRO = f"{FQDN}/api/v1"
# Read by requests itself; cleared so a developer's shell can't change what a test sees.
REQUESTS_ENV = ("REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "ALL_PROXY")
EXAMPLE_ONLY_ENV = ("JAMFPRO_USERNAME", "JAMFPRO_PASSWORD", "JAMFPY_EXAMPLE_CA_BUNDLE", "JAMFPY_EXAMPLE_CLIENT_CERT")


@pytest.fixture(autouse=True)
def example_env(monkeypatch):
    """The three ``.env`` variables every example reads, and nothing else that could change a run."""
    monkeypatch.setenv("JAMFPRO_INSTANCE_FQDN", FQDN)
    monkeypatch.setenv("JAMFPRO_CLIENT_ID", CLIENT_ID)
    monkeypatch.setenv("JAMFPRO_CLIENT_SECRET", CLIENT_SECRET)
    for name in REQUESTS_ENV + tuple(name.lower() for name in REQUESTS_ENV) + EXAMPLE_ONLY_ENV:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def no_real_sleep(monkeypatch, sleeps):
    """Every ``Tenant`` an example builds records its retry delays in ``sleeps``; any other sleep fails the test.

    The retry loop's sleep is bound when the API is built, so patching ``time.sleep`` alone would not reach it.
    """

    class RecordingTenant(jamfpy.Tenant):
        """A real ``Tenant`` whose APIs append each backoff delay to ``sleeps``."""

        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            for api in (self.pro, self.classic):
                if api._retry is not None:
                    api._retry.sleep = sleeps.append

    def refuse(seconds):
        raise AssertionError(f"an example slept for real ({seconds} s)")

    monkeypatch.setattr(jamfpy, "Tenant", RecordingTenant)
    monkeypatch.setattr(time, "sleep", refuse)


def run_example(stem):
    """Import ``examples/<stem>.py`` by path and run its ``main()``."""
    spec = importlib.util.spec_from_file_location(f"jamfpy_example_{stem}", EXAMPLES / f"{stem}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.main()


def sent(mocked_responses):
    """Every request sent, as ``(method, url)`` in order."""
    return [(call.request.method, call.request.url) for call in mocked_responses.calls]


def assert_api_calls_carry(mocked_responses, token):
    """Every call bar the token request carries ``token`` as its Bearer header."""
    for call in mocked_responses.calls:
        if call.request.url not in (TOKEN_URL, BEARER_URL):
            assert call.request.headers["Authorization"] == f"Bearer {token}", call.request.url


def page_url(page, size, sort=None):
    """The URL a Pro ``scripts.get_all`` sends for one page."""
    return f"{PRO}/scripts?page={page}&page-size={size}" + (f"&sort={sort}" if sort else "")


def script_page(start, count, total):
    """A Pro scripts page body with ``count`` scripts numbered from ``start``."""
    results = [{"id": str(i), "name": f"script-{i:03d}"} for i in range(start, start + count)]
    return {"totalCount": total, "results": results}


def test_quickstart(mocked_responses, capsys):
    """One Classic and one Pro read, after an up-front token fetch, then the token is invalidated."""
    register_oauth_token(mocked_responses)
    mocked_responses.get(f"{CLASSIC}/buildings", json={"buildings": [{"id": 1, "name": "London"}]})
    mocked_responses.get(page_url(0, 100), json=script_page(1, 2, 2))
    mocked_responses.post(INVALIDATE_URL, status=204)

    run_example("quickstart")

    assert sent(mocked_responses) == [
        ("POST", TOKEN_URL), ("GET", f"{CLASSIC}/buildings"), ("GET", page_url(0, 100)), ("POST", INVALIDATE_URL),
    ]
    assert_api_calls_carry(mocked_responses, FAKE_TOKEN)
    out = capsys.readouterr().out
    assert "Classic: 1 buildings ['London']" in out
    assert "Pro: 2 scripts ['script-001', 'script-002']" in out


def test_basic_auth(mocked_responses, monkeypatch, capsys):
    """The username and password go to the bearer-token endpoint only; the API call carries the bearer token."""
    monkeypatch.setenv("JAMFPRO_USERNAME", "example-user")
    monkeypatch.setenv("JAMFPRO_PASSWORD", "example-password")
    expires = datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=30)
    mocked_responses.post(BEARER_URL, json={"token": "bearer-token", "expires": expires.isoformat()})
    mocked_responses.get(f"{CLASSIC}/categories", json={"categories": [{"id": 1, "name": "Apps"}]})
    mocked_responses.post(INVALIDATE_URL, status=204)

    run_example("basic_auth")

    assert sent(mocked_responses) == [("POST", BEARER_URL), ("GET", f"{CLASSIC}/categories"), ("POST", INVALIDATE_URL)]
    credentials = base64.b64encode(b"example-user:example-password").decode()
    assert mocked_responses.calls[0].request.headers["Authorization"] == f"Basic {credentials}"
    assert_api_calls_carry(mocked_responses, "bearer-token")
    assert "1 categories" in capsys.readouterr().out


def test_error_handling(mocked_responses, capsys):
    """A 404 comes back as a Response; bad config, refused credentials and an unreachable host raise."""
    def token(request):
        if parse_qs(request.body)["client_secret"] == ["not-the-real-secret"]:
            return 401, {}, json.dumps({"error": "invalid_client"})
        return 200, {}, json.dumps({"access_token": FAKE_TOKEN, "expires_in": 1800})

    missing = f"{CLASSIC}/categories/id/{2**31 - 1}"
    unreachable_token_url = "https://jamfpy-example.invalid/api/oauth/token"
    mocked_responses.add_callback(responses.POST, TOKEN_URL, callback=token)
    mocked_responses.get(missing, status=404)
    mocked_responses.post(INVALIDATE_URL, status=204)
    mocked_responses.post(unreachable_token_url, body=requests.ConnectionError("Name or service not known"))

    run_example("error_handling")

    assert sent(mocked_responses) == [
        ("POST", TOKEN_URL), ("GET", missing), ("POST", INVALIDATE_URL), ("POST", TOKEN_URL), ("POST", unreachable_token_url),
    ]
    out = capsys.readouterr().out
    assert "not found (404), as expected" in out
    assert "Configuration refused:" in out
    assert "Credentials refused:" in out
    assert "Unreachable host: ConnectionError" in out


def test_unwrapped_endpoint(mocked_responses, capsys):
    """A hand-built request goes through do() with the token and the per-call timeout."""
    register_oauth_token(mocked_responses)
    mocked_responses.get(f"{PRO}/jamf-pro-version", json={"version": "11.20.0"})
    mocked_responses.post(INVALIDATE_URL, status=204)

    run_example("unwrapped_endpoint")

    assert sent(mocked_responses) == [("POST", TOKEN_URL), ("GET", f"{PRO}/jamf-pro-version"), ("POST", INVALIDATE_URL)]
    assert_api_calls_carry(mocked_responses, FAKE_TOKEN)
    assert mocked_responses.calls[1].request.req_kwargs["timeout"] == (5.0, 30.0)
    assert "Jamf Pro version: 11.20.0" in capsys.readouterr().out


def test_logging_output(mocked_responses, capsys):
    """A text INFO line, then JSON DEBUG lines, with the credentials and the token redacted."""
    register_oauth_token(mocked_responses)
    mocked_responses.get(f"{CLASSIC}/categories", json={"categories": []})
    mocked_responses.post(INVALIDATE_URL, status=204)

    run_example("logging_output")

    assert Counter(sent(mocked_responses)) == {
        ("POST", TOKEN_URL): 2, ("GET", f"{CLASSIC}/categories"): 2, ("POST", INVALIDATE_URL): 2,
    }
    out = capsys.readouterr().out
    text_part, json_part = out.split("--- JSON, DEBUG ---")
    assert f"[INFO] (test-clc): GET {CLASSIC}/categories -> 200" in text_part
    records = [json.loads(line) for line in json_part.splitlines() if line.startswith("{")]
    assert {"DEBUG", "INFO"} <= {record["level"] for record in records}
    assert any(record["sender"] == "test-auth" for record in records)
    for secret in (CLIENT_ID, CLIENT_SECRET, FAKE_TOKEN):
        assert secret not in out


def test_timeouts_and_retries(mocked_responses, capsys):
    """Each tenant sends its read with its own timeout."""
    register_oauth_token(mocked_responses)
    mocked_responses.get(f"{CLASSIC}/categories", json={"categories": []})
    mocked_responses.post(INVALIDATE_URL, status=204)

    run_example("timeouts_and_retries")

    reads = [call.request for call in mocked_responses.calls if call.request.method == "GET"]
    assert [request.req_kwargs["timeout"] for request in reads] == [10.0, (5.0, 60.0), 30.0]
    assert Counter(sent(mocked_responses)) == {
        ("POST", TOKEN_URL): 3, ("GET", f"{CLASSIC}/categories"): 3, ("POST", INVALIDATE_URL): 3,
    }
    assert capsys.readouterr().out.count(": 200") == 3


def test_pagination(mocked_responses, capsys):
    """Three pages of 50, fetched in parallel and sequentially, aggregate to the same 120 scripts."""
    register_oauth_token(mocked_responses)
    for page in range(3):
        mocked_responses.get(page_url(page, 50, "name:asc"), json=script_page(page * 50, min(50, 120 - page * 50), 120))
    mocked_responses.post(INVALIDATE_URL, status=204)

    run_example("pagination")

    expected = {("POST", TOKEN_URL): 2, ("POST", INVALIDATE_URL): 2}
    expected.update({("GET", page_url(page, 50, "name:asc")): 2 for page in range(3)})
    assert Counter(sent(mocked_responses)) == expected
    out = capsys.readouterr().out
    assert "parallelism=5: 120 scripts" in out
    assert "parallelism=1: 120 scripts" in out
    assert "Same records in the same order: True" in out


def test_pagination_returns_a_failed_page_raw(mocked_responses, capsys):
    """A failed page comes back as itself, so the example reports its status and URL."""
    register_oauth_token(mocked_responses)
    mocked_responses.get(page_url(0, 50, "name:asc"), json=script_page(0, 50, 120))
    mocked_responses.get(page_url(1, 50, "name:asc"), status=404)
    # The parallel run starts page 2 alongside page 1; the sequential run stops at page 1.
    mocked_responses.get(page_url(2, 50, "name:asc"), json=script_page(100, 20, 120))
    mocked_responses.post(INVALIDATE_URL, status=204)

    run_example("pagination")

    out = capsys.readouterr().out
    assert f"parallelism=5: a page failed with 404 at {page_url(1, 50, 'name:asc')}" in out
    assert f"parallelism=1: a page failed with 404 at {page_url(1, 50, 'name:asc')}" in out
    assert "Same records" not in out


@pytest.mark.parametrize("configured", [False, True], ids=["unset", "set"])
def test_certificates(mocked_responses, monkeypatch, tmp_path, capsys, configured):
    """The optional paths reach the request as verify and cert, and an env proxy is honoured."""
    register_oauth_token(mocked_responses)
    mocked_responses.get(f"{CLASSIC}/categories", json={"categories": []})
    mocked_responses.post(INVALIDATE_URL, status=204)
    ca_bundle, client_cert = tmp_path / "ca.pem", tmp_path / "client.pem"
    if configured:
        ca_bundle.write_text("ca", encoding="utf-8")
        client_cert.write_text("cert", encoding="utf-8")
        monkeypatch.setenv("JAMFPY_EXAMPLE_CA_BUNDLE", str(ca_bundle))
        monkeypatch.setenv("JAMFPY_EXAMPLE_CLIENT_CERT", str(client_cert))
        monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:3128")

    run_example("certificates")

    assert sent(mocked_responses) == [("POST", TOKEN_URL), ("GET", f"{CLASSIC}/categories"), ("POST", INVALIDATE_URL)]
    sent_kwargs = mocked_responses.calls[1].request.req_kwargs
    out = capsys.readouterr().out
    if configured:
        assert sent_kwargs["verify"] == str(ca_bundle)
        assert sent_kwargs["cert"] == str(client_cert)
        assert sent_kwargs["proxies"]["https"] == "http://proxy.invalid:3128"
        assert f"JAMFPY_EXAMPLE_CA_BUNDLE: {ca_bundle}" in out
        assert "HTTPS_PROXY: set" in out
        assert "proxy.invalid" not in out
    else:
        assert sent_kwargs["verify"] is True
        assert sent_kwargs["cert"] is None
        assert "JAMFPY_EXAMPLE_CA_BUNDLE not set" in out
        assert "HTTPS_PROXY: not set" in out


def test_request_hooks(mocked_responses, sleeps, capsys):
    """The hooks count every attempt, including a retried 503, and see each Pro page."""
    register_oauth_token(mocked_responses)
    # Served in turn: the first attempt gets the 503, the retry the 200.
    mocked_responses.get(f"{CLASSIC}/categories", status=503)
    mocked_responses.get(f"{CLASSIC}/categories", json={"categories": []})
    mocked_responses.get(page_url(0, 10), json=script_page(0, 10, 15))
    mocked_responses.get(page_url(1, 10), json=script_page(10, 5, 15))
    mocked_responses.post(INVALIDATE_URL, status=204)

    run_example("request_hooks")

    assert Counter(sent(mocked_responses)) == {
        ("POST", TOKEN_URL): 1, ("GET", f"{CLASSIC}/categories"): 2, ("GET", page_url(0, 10)): 1,
        ("GET", page_url(1, 10)): 1, ("POST", INVALIDATE_URL): 1,
    }
    assert len(sleeps) == 1
    out = capsys.readouterr().out
    assert f"retrying GET {CLASSIC}/categories after attempt 1 (HTTP 503)" in out
    assert "Attempts sent per API: {'classic': 2, 'pro': 2}" in out
    assert "Responses per status: {503: 1, 200: 3}" in out
    assert "Retries: 1" in out


def test_concurrent_requests(mocked_responses, capsys):
    """Every listed category is read by id, from a thread pool sharing one tenant and one token."""
    register_oauth_token(mocked_responses)
    categories = [{"id": i, "name": f"Category {i}"} for i in range(1, 4)]
    mocked_responses.get(f"{CLASSIC}/categories", json={"categories": categories})
    for category in categories:
        mocked_responses.get(f"{CLASSIC}/categories/id/{category['id']}", json={"category": category})
    mocked_responses.post(INVALIDATE_URL, status=204)

    run_example("concurrent_requests")

    expected = Counter([("POST", TOKEN_URL), ("GET", f"{CLASSIC}/categories"), ("POST", INVALIDATE_URL)])
    expected.update(("GET", f"{CLASSIC}/categories/id/{i}") for i in range(1, 4))
    assert Counter(sent(mocked_responses)) == expected
    assert_api_calls_carry(mocked_responses, FAKE_TOKEN)
    out = capsys.readouterr().out
    assert "1 Category 1\n2 Category 2\n3 Category 3\n" in out
    assert "Read 3 categories" in out


CATEGORY_ID_URL = f"{CLASSIC}/categories/id/42"
EXAMPLE_NAME = "jamfpy-example-0badc0de"


def register_category_create(mocked_responses):
    """Answer the category create with id 42, as Jamf does, in XML."""
    register_oauth_token(mocked_responses)
    mocked_responses.post(f"{CLASSIC}/categories/id/0", status=201, body='<?xml version="1.0"?><category><id>42</id></category>')
    mocked_responses.get(CATEGORY_ID_URL, json={"category": {"id": 42, "name": EXAMPLE_NAME}})


def test_classic_write_lifecycle(mocked_responses, monkeypatch, capsys):
    """Create, read, update, read and delete one category, with the XML bodies the schema takes."""
    monkeypatch.setattr(secrets, "token_hex", lambda nbytes: "0badc0de")
    register_category_create(mocked_responses)
    mocked_responses.get(CATEGORY_ID_URL, json={"category": {"id": 42, "name": f"{EXAMPLE_NAME}-updated"}})
    mocked_responses.put(CATEGORY_ID_URL, status=201, body="<category><id>42</id></category>")
    mocked_responses.delete(CATEGORY_ID_URL, status=200)
    mocked_responses.post(INVALIDATE_URL, status=204)

    run_example("classic_write_lifecycle")

    assert sent(mocked_responses) == [
        ("POST", TOKEN_URL), ("POST", f"{CLASSIC}/categories/id/0"), ("GET", CATEGORY_ID_URL), ("PUT", CATEGORY_ID_URL),
        ("GET", CATEGORY_ID_URL), ("DELETE", CATEGORY_ID_URL), ("POST", INVALIDATE_URL),
    ]
    assert mocked_responses.calls[1].request.body == f"<category><name>{EXAMPLE_NAME}</name><priority>9</priority></category>"
    assert mocked_responses.calls[3].request.body == f"<category><name>{EXAMPLE_NAME}-updated</name><priority>5</priority></category>"
    out = capsys.readouterr().out
    assert f"Created category 42: {EXAMPLE_NAME}" in out
    assert f"Read back: {EXAMPLE_NAME}-updated" in out
    assert "Delete: 200" in out
    assert "Cleanup" not in out


def test_classic_write_lifecycle_deletes_the_category_when_a_step_raises(mocked_responses, monkeypatch, capsys):
    """An exception after the create still leaves the tenant clean: the finally block deletes the record."""
    monkeypatch.setattr(secrets, "token_hex", lambda nbytes: "0badc0de")
    register_category_create(mocked_responses)
    # SSLError is never retried, so the update fails on its first attempt.
    mocked_responses.put(CATEGORY_ID_URL, body=requests.exceptions.SSLError("certificate verify failed"))
    mocked_responses.delete(CATEGORY_ID_URL, status=200)
    mocked_responses.post(INVALIDATE_URL, status=204)

    with pytest.raises(requests.exceptions.SSLError):
        run_example("classic_write_lifecycle")

    assert sent(mocked_responses)[-2:] == [("DELETE", CATEGORY_ID_URL), ("POST", INVALIDATE_URL)]
    assert "Cleanup delete: 200" in capsys.readouterr().out


def test_pro_write_lifecycle(mocked_responses, monkeypatch, capsys):
    """Create, read, update, read and delete one script, with JSON bodies."""
    monkeypatch.setattr(secrets, "token_hex", lambda nbytes: "0badc0de")
    script_url = f"{PRO}/scripts/7"
    register_oauth_token(mocked_responses)
    mocked_responses.post(f"{PRO}/scripts", status=201, json={"id": "7", "href": script_url})
    mocked_responses.get(script_url, json={"id": "7", "name": EXAMPLE_NAME})
    mocked_responses.get(script_url, json={"id": "7", "name": f"{EXAMPLE_NAME}-updated"})
    mocked_responses.put(script_url, json={"id": "7", "name": f"{EXAMPLE_NAME}-updated"})
    mocked_responses.delete(script_url, status=204)
    mocked_responses.post(INVALIDATE_URL, status=204)

    run_example("pro_write_lifecycle")

    assert sent(mocked_responses) == [
        ("POST", TOKEN_URL), ("POST", f"{PRO}/scripts"), ("GET", script_url), ("PUT", script_url), ("GET", script_url),
        ("DELETE", script_url), ("POST", INVALIDATE_URL),
    ]
    created = json.loads(mocked_responses.calls[1].request.body)
    updated = json.loads(mocked_responses.calls[3].request.body)
    assert created["name"] == EXAMPLE_NAME
    assert updated["name"] == f"{EXAMPLE_NAME}-updated"
    assert set(created) == set(updated) == {"name", "notes", "priority", "scriptContents"}
    out = capsys.readouterr().out
    assert f"Created script 7: {EXAMPLE_NAME}" in out
    assert "Delete: 204" in out
    assert "Cleanup" not in out


def test_every_example_has_a_test():
    """Each ``examples/<name>.py`` is covered by a ``test_<name>`` in this module."""
    stems = sorted(path.stem for path in EXAMPLES.glob("*.py"))
    assert stems, f"no examples found in {EXAMPLES}"
    untested = [stem for stem in stems if not callable(globals().get(f"test_{stem}"))]
    assert not untested, f"examples without a test_<name> in {Path(__file__).name}: {untested}"
