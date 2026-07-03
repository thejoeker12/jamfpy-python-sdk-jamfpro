"""Unit tests for the Pro App Installers endpoint."""
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
    # Documented quirk: reads use the create-update json header set.
    assert req.headers == H["crud"]["create-update"]["json"]


def test_create_posts_json_payload():
    api = FakeAPI()
    AppInstallers(api).create({"name": "app"})
    req = api.last_request
    assert req.method == "POST"
    assert req.url == BASE
    assert req.headers == H["crud"]["create-update"]["json"]
    assert req.json == {"name": "app"}


def test_delete_uses_delete_header():
    api = FakeAPI()
    AppInstallers(api).delete(5)
    req = api.last_request
    assert req.method == "DELETE"
    assert req.url == f"{BASE}/5"
    assert req.headers == H["crud"]["delete"]["json"]
