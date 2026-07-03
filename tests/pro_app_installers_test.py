"""Unit tests for the Pro App Installers endpoint (inherits ProEndpoint CRUD + pagination)."""
# pylint: disable=missing-function-docstring
from conftest import FakeAPI, FQDN

from jamfpy.endpoints.pro_app_installers import AppInstallers
from jamfpy.client.constants import DEFAULT_HTTP_CONFIG_HEADERS as H

BASE = f"{FQDN}/api/v1/app-installers/deployments"


def test_get_by_id_builds_deployment_url():
    api = FakeAPI()
    AppInstallers(api).get_by_id(5)
    req = api.last_request
    assert req.method == "GET"
    assert req.url == f"{BASE}/5"
    # Standardised: reads now use the read json header (was create-update).
    assert req.headers == H["crud"]["read"]["json"]


def test_create_posts_json_payload():
    api = FakeAPI()
    AppInstallers(api).create({"name": "app"})
    req = api.last_request
    assert req.method == "POST"
    assert req.url == BASE
    assert req.headers == H["crud"]["create-update"]["json"]
    assert req.json == {"name": "app"}


def test_delete_by_id_uses_delete_header():
    api = FakeAPI()
    AppInstallers(api).delete_by_id(5)
    req = api.last_request
    assert req.method == "DELETE"
    assert req.url == f"{BASE}/5"
    assert req.headers == H["crud"]["delete"]["json"]


def test_get_all_builds_paginated_url():
    # Construction-only: the deployments response shape is unverified, so we assert only the
    # request the (inherited) get_all builds for the first page.
    from conftest import make_response  # pylint: disable=import-outside-toplevel
    api = FakeAPI(responses=[make_response({"totalCount": 1, "results": [{"id": 1}]})])
    AppInstallers(api).get_all()
    req = api.last_request
    assert req.method == "GET"
    assert req.url == f"{BASE}?page=0&page-size=100"
    assert req.headers == H["crud"]["read"]["json"]
