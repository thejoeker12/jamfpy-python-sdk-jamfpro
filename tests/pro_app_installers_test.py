"""Unit tests for the Pro App Installers endpoint (full ProEndpoint CRUD + pagination)."""
# pylint: disable=missing-function-docstring
import json

from conftest import FQDN, sent_headers, with_bearer

from jamfpy.client.constants import DEFAULT_HTTP_CONFIG_HEADERS as H

BASE = f"{FQDN}/api/v1/app-installers/deployments"


def test_get_by_id_builds_deployment_url(pro_api, mocked_responses):
    mocked_responses.get(f"{BASE}/5", json={"id": "5"})
    pro_api.app_installers.get_by_id(5)
    req = mocked_responses.calls[-1].request
    assert req.method == "GET"
    assert req.url == f"{BASE}/5"
    # Standardised: reads now use the read json header (was create-update).
    assert sent_headers(req) == with_bearer(H["crud"]["read"]["json"])


def test_create_posts_json_payload(pro_api, mocked_responses):
    mocked_responses.post(BASE, status=201, json={"id": "6"})
    pro_api.app_installers.create({"name": "app"})
    req = mocked_responses.calls[-1].request
    assert req.method == "POST"
    assert req.url == BASE
    assert sent_headers(req) == with_bearer(H["crud"]["create-update"]["json"])
    assert json.loads(req.body) == {"name": "app"}


def test_delete_by_id_uses_delete_header(pro_api, mocked_responses):
    mocked_responses.delete(f"{BASE}/5", status=204)
    pro_api.app_installers.delete_by_id(5)
    req = mocked_responses.calls[-1].request
    assert req.method == "DELETE"
    assert req.url == f"{BASE}/5"
    assert sent_headers(req) == with_bearer(H["crud"]["delete"]["json"])


def test_get_all_builds_paginated_url(pro_api, mocked_responses):
    # Construction-only: the probe shows GET on the collection, but nothing documents its paging or body shape, so
    # we assert only the request the (inherited) get_all builds for the first page.
    mocked_responses.get(f"{BASE}?page=0&page-size=100", json={"totalCount": 1, "results": [{"id": 1}]})
    pro_api.app_installers.get_all()
    req = mocked_responses.calls[-1].request
    assert req.method == "GET"
    assert req.url == f"{BASE}?page=0&page-size=100"
    assert sent_headers(req) == with_bearer(H["crud"]["read"]["json"])
