"""Unit tests for the Accounts composite endpoint (response transforms)."""
# pylint: disable=missing-function-docstring
import json

import pytest
from requests import HTTPError
from conftest import FQDN, sent_headers, with_bearer

from jamfpy.endpoints.clc_endpoints_accounts import (
    AccountChild,
    AccountUsers,
    AccountGroups,
)
from jamfpy.client.constants import DEFAULT_HTTP_CONFIG_HEADERS as H

BASE = f"{FQDN}/JSSResource"
ACCOUNTS_URL = f"{BASE}/accounts"
ACCOUNTS_PAYLOAD = {"accounts": {"users": [{"id": 1, "name": "u"}], "groups": [{"id": 2}]}}


def test_account_child_uses_base_repackage_helper():
    # The near-duplicate pass_response is gone; Endpoint._repackage_response is the one helper.
    assert not hasattr(AccountChild, "pass_response")


@pytest.mark.parametrize("child, key, expected", [
    ("users", "users", [{"id": 1, "name": "u"}]),
    ("groups", "groups", [{"id": 2}]),
])
def test_get_all_repackage_preserves_response_metadata(classic_api, mocked_responses, child, key, expected):
    mocked_responses.get(ACCOUNTS_URL, json=ACCOUNTS_PAYLOAD, status=203, headers={"X-Test": "1"})
    resp = getattr(classic_api.accounts, child).get_all()

    assert resp.json() == {key: expected}
    assert resp.status_code == 203
    assert resp.headers["X-Test"] == "1"
    assert resp.url == ACCOUNTS_URL
    assert resp.headers["Content-Length"] == str(len(json.dumps({key: expected}).encode("utf-8")))


def test_users_get_all_strips_payload_to_users(classic_api, mocked_responses):
    mocked_responses.get(ACCOUNTS_URL, json=ACCOUNTS_PAYLOAD)
    resp = classic_api.accounts.users.get_all()
    assert resp.json() == {"users": [{"id": 1, "name": "u"}]}
    # The underlying read hit the shared /accounts resource.
    req = mocked_responses.calls[-1].request
    assert req.url == ACCOUNTS_URL
    assert sent_headers(req) == with_bearer(H["crud"]["read"]["json"])


def test_groups_get_all_strips_payload_to_groups(classic_api, mocked_responses):
    mocked_responses.get(ACCOUNTS_URL, json=ACCOUNTS_PAYLOAD)
    resp = classic_api.accounts.groups.get_all()
    assert resp.json() == {"groups": [{"id": 2}]}


@pytest.mark.parametrize("child", ["users", "groups"])
def test_get_all_raises_for_status(classic_api, mocked_responses, child):
    # Characterises current behaviour: both accounts get_alls call raise_for_status before repackaging.
    mocked_responses.get(ACCOUNTS_URL, json={}, status=500)
    with pytest.raises(HTTPError):
        getattr(classic_api.accounts, child).get_all()


def test_account_child_get_by_id_uses_by_id_uri(classic_api, mocked_responses):
    mocked_responses.get(f"{BASE}/accounts/userid/5", json={})
    classic_api.accounts.users.get_by_id(5)
    req = mocked_responses.calls[-1].request
    assert req.method == "GET"
    assert req.url == f"{BASE}/accounts/userid/5"
    assert sent_headers(req) == with_bearer(H["crud"]["read"]["json"])


def test_account_groups_by_id_uri(classic_api, mocked_responses):
    mocked_responses.get(f"{BASE}/accounts/groupid/5", json={})
    classic_api.accounts.groups.get_by_id(5)
    assert mocked_responses.calls[-1].request.url == f"{BASE}/accounts/groupid/5"


def test_account_child_create_posts_to_by_id_uri_zero(classic_api, mocked_responses):
    mocked_responses.post(f"{BASE}/accounts/userid/0", status=201, body="<user><id>6</id></user>")
    classic_api.accounts.users.create("<user/>")
    req = mocked_responses.calls[-1].request
    assert req.method == "POST"
    assert req.url == f"{BASE}/accounts/userid/0"
    assert sent_headers(req) == with_bearer(H["crud"]["create-update"]["xml"])
    assert req.body == "<user/>"


def test_accounts_wires_users_and_groups(classic_api):
    accounts = classic_api.accounts
    assert isinstance(accounts.users, AccountUsers)
    assert isinstance(accounts.groups, AccountGroups)


def test_accounts_get_all_hits_accounts_resource(classic_api, mocked_responses):
    mocked_responses.get(ACCOUNTS_URL, json=ACCOUNTS_PAYLOAD)
    classic_api.accounts.get_all()
    req = mocked_responses.calls[-1].request
    assert req.url == ACCOUNTS_URL
    assert sent_headers(req) == with_bearer(H["crud"]["read"]["json"])
