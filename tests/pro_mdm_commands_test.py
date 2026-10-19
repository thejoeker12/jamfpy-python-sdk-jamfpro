"""Unit tests for the Pro MDM commands endpoint."""
# pylint: disable=missing-function-docstring,redefined-outer-name
import json

import pytest
from conftest import FQDN, sent_headers, with_bearer

from jamfpy.client.constants import DEFAULT_HTTP_CONFIG_HEADERS as H

URL = f"{FQDN}/api/v2/mdm/commands"


@pytest.fixture
def send(pro_api, mocked_responses):
    """Call an MDMCommands method through the real ProAPI; returns the request sent and its decoded JSON body."""
    mocked_responses.post(URL, status=201, json=[{"id": "1", "href": "/v2/mdm/commands/1"}])

    def _send(method_name, *args, **kwargs):
        getattr(pro_api.mdm, method_name)(*args, **kwargs)
        req = mocked_responses.calls[-1].request
        return req, json.loads(req.body)

    return _send


def test_send_command_builds_payload_and_targets_v2(send):
    req, payload = send("send_command", "DEVICE_LOCK", ["m1", "m2"], pin="1234", message="hi")
    assert req.method == "POST"
    assert req.url == URL
    # Characterises current behaviour: send_command passes the read header set (no content-type);
    # requests adds one for the json= body.
    assert sent_headers(req) == with_bearer({**H["crud"]["read"]["json"], "Content-Type": "application/json"})
    assert payload == {
        "clientData": [{"managementId": "m1"}, {"managementId": "m2"}],
        "commandData": {"commandType": "DEVICE_LOCK", "pin": "1234", "message": "hi"},
    }


# Wrappers that take only management_ids: assert commandType + single->list coercion.
NO_ARG_WRAPPERS = [
    ("certificate_list", "CERTIFICATE_LIST"),
    ("clear_restrictions_password", "CLEAR_RESTRICTIONS_PASSWORD"),
    ("device_location", "DEVICE_LOCATION"),
    ("disable_remote_desktop", "DISABLE_REMOTE_DESKTOP"),
    ("enable_remote_desktop", "ENABLE_REMOTE_DESKTOP"),
    ("log_out_user", "LOG_OUT_USER"),
    ("managed_media_list", "MANAGED_MEDIA_LIST"),
    ("play_lost_mode_sound", "PLAY_LOST_MODE_SOUND"),
    ("security_info", "SECURITY_INFO"),
    ("stop_mirroring", "STOP_MIRRORING"),
    ("shut_down_device", "SHUT_DOWN_DEVICE"),
    ("validate_applications", "VALIDATE_APPLICATIONS"),
]


@pytest.mark.parametrize("method_name,command_type", NO_ARG_WRAPPERS)
def test_no_arg_wrapper_coerces_single_id(send, method_name, command_type):
    req, payload = send(method_name, "m1")  # single string, not a list
    assert req.url == URL
    assert payload["clientData"] == [{"managementId": "m1"}]
    assert payload["commandData"]["commandType"] == command_type


def test_lock_device_maps_camel_case_kwargs(send):
    _, payload = send("lock_device", ["m1"], message="locked", pin="9999", phone_number="+15550000")
    data = payload["commandData"]
    assert data["commandType"] == "DEVICE_LOCK"
    assert data["message"] == "locked"
    assert data["pin"] == "9999"
    assert data["phoneNumber"] == "+15550000"


def test_erase_device_defaults_return_to_service(send):
    _, payload = send("erase_device", ["m1"])
    data = payload["commandData"]
    assert data["commandType"] == "ERASE_DEVICE"
    assert data["returnToService"] == {"enabled": True}
    assert data["pin"] == "1234"
    assert data["obliterationBehavior"] == "Default"


def test_disable_lost_mode_defaults_return_to_service(send):
    _, payload = send("disable_lost_mode", ["m1"])
    assert payload["commandData"]["returnToService"] == {"enabled": True}


def test_clear_passcode_maps_unlock_token(send):
    _, payload = send("clear_passcode", ["m1"], unlock_token="tok")
    assert payload["commandData"]["unlockToken"] == "tok"


def test_delete_user_maps_kwargs(send):
    _, payload = send("delete_user", ["m1"], user_name="bob", force_deletion=True, delete_all_users=False)
    data = payload["commandData"]
    assert data["userName"] == "bob"
    assert data["forceDeletion"] is True
    assert data["deleteAllUsers"] is False


def test_restart_device_uses_schema_kernel_cache_key(send):
    # RestartDeviceCommand in pro.json spells it rebuildKernelCache.
    _, payload = send("restart_device", ["m1"])
    data = payload["commandData"]
    assert data["rebuildKernelCache"] is True
    assert "rebuildKernalCache" not in data
    assert data["kextPaths"] == []
    assert data["notifyUser"] is True


def test_declerative_management_sends_declarative_command(send):
    _, payload = send("declerative_management", ["m1"], data="payload")
    data = payload["commandData"]
    assert data["commandType"] == "DECLARATIVE_MANAGEMENT"
    assert data["data"] == "payload"
