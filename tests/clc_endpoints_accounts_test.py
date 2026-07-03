"""Unit tests for the Accounts composite endpoint (response transforms)."""
# pylint: disable=missing-function-docstring
import json

import pytest
from requests import HTTPError
from conftest import FakeAPI, FQDN, make_response

from jamfpy.endpoints.clc_endpoints_accounts import (
    AccountUsers,
    AccountGroups,
    Accounts,
)
from jamfpy.client.constants import DEFAULT_HTTP_CONFIG_HEADERS as H

BASE = f"{FQDN}/JSSResource"
ACCOUNTS_PAYLOAD = {"accounts": {"users": [{"id": 1, "name": "u"}], "groups": [{"id": 2}]}}


def test_pass_response_repackages_json():
    users = AccountUsers(FakeAPI())
    original = make_response({"ignored": True}, status=201, headers={"X-Test": "1"})
    new = users.pass_response(original, {"users": [{"id": 9}]})

    assert new.status_code == 201
    assert new.json() == {"users": [{"id": 9}]}
    assert new.headers["X-Test"] == "1"  # copied from original
    expected_len = str(len(json.dumps({"users": [{"id": 9}]}).encode("utf-8")))
    assert new.headers["Content-Length"] == expected_len


def test_users_get_all_strips_payload_to_users():
    api = FakeAPI(responses=[make_response(ACCOUNTS_PAYLOAD)])
    resp = AccountUsers(api).get_all()
    assert resp.json() == {"users": [{"id": 1, "name": "u"}]}
    # The underlying read hit the shared /accounts resource.
    assert api.last_request.url == f"{BASE}/accounts"


def test_groups_get_all_strips_payload_to_groups():
    api = FakeAPI(responses=[make_response(ACCOUNTS_PAYLOAD)])
    resp = AccountGroups(api).get_all()
    assert resp.json() == {"groups": [{"id": 2}]}


def test_users_get_all_raises_for_status():
    api = FakeAPI(responses=[make_response({}, status=500)])
    with pytest.raises(HTTPError):
        AccountUsers(api).get_all()


def test_account_child_get_by_id_uses_by_id_uri():
    api = FakeAPI()
    AccountUsers(api).get_by_id(5)
    req = api.last_request
    assert req.method == "GET"
    assert req.url == f"{BASE}/accounts/userid/5"
    assert req.headers == H["crud"]["read"]["json"]


def test_account_groups_by_id_uri():
    api = FakeAPI()
    AccountGroups(api).get_by_id(5)
    assert api.last_request.url == f"{BASE}/accounts/groupid/5"


def test_account_child_create_posts_to_by_id_uri_zero():
    api = FakeAPI()
    AccountUsers(api).create("<user/>")
    req = api.last_request
    assert req.method == "POST"
    assert req.url == f"{BASE}/accounts/userid/0"
    assert req.data == "<user/>"


def test_accounts_wires_users_and_groups():
    accounts = Accounts(FakeAPI())
    assert isinstance(accounts.users, AccountUsers)
    assert isinstance(accounts.groups, AccountGroups)


def test_accounts_get_all_hits_accounts_resource():
    api = FakeAPI()
    Accounts(api).get_all()
    assert api.last_request.url == f"{BASE}/accounts"
