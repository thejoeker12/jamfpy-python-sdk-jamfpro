"""Live min/max lifecycle tests for every CRUD-capable Classic resource.

One spec per resource: ``min`` builds a payload with only required fields,
``max`` with every writable field we can assert. Builders derive varying values
from the resource name so the update phase (re-run with a mutated name) changes
real content, not just the name. Keys the server reshapes on read-back (e.g.
``criteria`` dicts that come back as lists) are listed in ``unassertable`` —
they are still sent, just not echo-asserted.

Coverage tracker: COVERAGE.md → *Live integration test coverage*.
"""
# pylint: disable=redefined-outer-name
import uuid

import pytest

from .lifecycle import run_classic_lifecycle

pytestmark = pytest.mark.integration


def _stable(name: str) -> str:
    """Deterministic per-resource seed that survives the update-phase rename."""
    return uuid.uuid5(uuid.NAMESPACE_DNS, name.removesuffix("-upd")).hex


def _password(name: str) -> str:
    """Generated account password satisfying typical complexity policies."""
    return f"Jp1!{uuid.uuid5(uuid.NAMESPACE_DNS, name).hex}"


def _plist(name: str) -> str:
    """Minimal but valid configuration-profile payload plist."""
    payload_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, name)).upper()
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">'
        '<plist version="1"><dict>'
        "<key>PayloadContent</key><array/>"
        f"<key>PayloadDisplayName</key><string>{name}</string>"
        f"<key>PayloadIdentifier</key><string>com.jamfpy.it.{name}</string>"
        "<key>PayloadType</key><string>Configuration</string>"
        f"<key>PayloadUUID</key><string>{payload_uuid}</string>"
        "<key>PayloadVersion</key><integer>1</integer>"
        "</dict></plist>"
    )


def _computer_criteria(name: str) -> dict:
    return {"criterion": {
        "name": "Computer Name", "priority": 0, "and_or": "and",
        "search_type": "like", "value": name,
    }}


SPECS = [
    {
        "id": "categories",
        "accessor": "categories",
        "root": "category",
        "min": lambda n: {"name": n},
        "max": lambda n: {"name": n, "priority": 5},
    },
    {
        "id": "buildings",
        "accessor": "buildings",
        "root": "building",
        "min": lambda n: {"name": n},
        "max": lambda n: {
            "name": n,
            "streetAddress1": f"1 {n} Street",
            "streetAddress2": "Suite 4",
            "city": "Testville",
            "stateProvince": "Testshire",
            "zipPostalCode": "TE5 7ST",
            "country": "United Kingdom",
        },
    },
    {
        # Departments only have a name — min and max are legitimately identical.
        "id": "departments",
        "accessor": "departments",
        "root": "department",
        "min": lambda n: {"name": n},
        "max": lambda n: {"name": n},
    },
    {
        # Sites only have a name — min and max are legitimately identical.
        "id": "sites",
        "accessor": "sites",
        "root": "site",
        "min": lambda n: {"name": n},
        "max": lambda n: {"name": n},
    },
    {
        "id": "scripts",
        "accessor": "scripts",
        "root": "script",
        "min": lambda n: {"name": n},
        "max": lambda n: {
            "name": n,
            "filename": f"{n}.sh",
            "info": f"info for {n}",
            "notes": f"notes for {n}",
            "priority": "After",
            "parameters": {f"parameter{i}": f"{n}-p{i}" for i in range(4, 12)},
            "os_requirements": "15",
            "script_contents": f'#!/bin/bash\necho "{n}"\n',
        },
    },
    {
        "id": "packages",
        "accessor": "packages",
        "root": "package",
        "min": lambda n: {"name": n, "filename": f"{n}.pkg"},
        "max": lambda n: {
            "name": n,
            "filename": f"{n}.pkg",
            "info": f"info for {n}",
            "notes": f"notes for {n}",
            "priority": 10,
            "reboot_required": False,
            "fill_user_template": False,
            "fill_existing_users": False,
        },
    },
    {
        "id": "computer_extension_attributes",
        "accessor": "computer_extension_attributes",
        "root": "computer_extension_attribute",
        "min": lambda n: {"name": n, "input_type": {"type": "Text Field"}},
        "max": lambda n: {
            "name": n,
            "description": f"description for {n}",
            "data_type": "String",
            "inventory_display": "General",
            "input_type": {"type": "Text Field"},
        },
    },
    {
        "id": "computer_groups",
        "accessor": "computer_groups",
        "root": "computer_group",
        "min": lambda n: {"name": n, "is_smart": False},
        "max": lambda n: {"name": n, "is_smart": True, "criteria": _computer_criteria(n)},
        "unassertable": ("criteria",),  # reads back as a list, not the sent dict
    },
    {
        "id": "mobile_device_groups",
        "accessor": "mobile_device_groups",
        "root": "mobile_device_group",
        "min": lambda n: {"name": n, "is_smart": False},
        "max": lambda n: {"name": n, "is_smart": True, "criteria": {"criterion": {
            "name": "Display Name", "priority": 0, "and_or": "and",
            "search_type": "like", "value": n,
        }}},
        "unassertable": ("criteria",),
    },
    {
        "id": "policies",
        "accessor": "policies",
        "root": "policy",
        "min": lambda n: {"general": {"name": n}},
        "max": lambda n: {"general": {
            "name": n,
            "enabled": False,
            "frequency": "Once per computer",
            "trigger_checkin": False,
        }},
    },
    {
        "id": "configuration_profiles",
        "accessor": "configuration_profiles",
        "root": "os_x_configuration_profile",
        "min": lambda n: {"general": {"name": n, "payloads": _plist(n)}},
        "max": lambda n: {"general": {
            "name": n,
            "description": f"description for {n}",
            "distribution_method": "Install Automatically",
            "user_removable": False,
            "level": "computer",
            "payloads": _plist(n),
        }},
        "unassertable": ("payloads",),  # server normalizes the plist on read-back
    },
    {
        "id": "computer_searches",
        "accessor": "computer_searches",
        "root": "advanced_computer_search",
        "min": lambda n: {"name": n},
        "max": lambda n: {
            "name": n,
            "view_as": "Standard",
            "criteria": _computer_criteria(n),
            "display_fields": {"display_field": {"name": "Computer Name"}},
        },
        "unassertable": ("criteria", "display_fields"),
    },
    {
        "id": "computers",
        "accessor": "computers",
        "root": "computer",
        "min": lambda n: {"general": {"name": n}},
        "max": lambda n: {
            "general": {
                "name": n,
                "asset_tag": f"AT-{_stable(n)[:8]}",
                "barcode_1": f"B1-{_stable(n)[:8]}",
            },
            "location": {
                "real_name": f"Jamfpy IT {n[-8:]}",
                "email_address": f"{n}@example.com",
                "position": "Test Fixture",
                "room": "101",
            },
        },
    },
    {
        # udid/serial are fabricated but deterministic per test, so the
        # update-phase rename does not try to change the device's identity.
        "id": "mobile_devices",
        "accessor": "mobile_devices",
        "root": "mobile_device",
        "min": lambda n: {"general": {
            "name": n,
            "udid": str(uuid.uuid5(uuid.NAMESPACE_DNS, n.removesuffix("-upd"))).upper(),
            "serial_number": f"JPIT{_stable(n)[:8].upper()}",
        }},
        "max": lambda n: {"general": {
            "name": n,
            "udid": str(uuid.uuid5(uuid.NAMESPACE_DNS, n.removesuffix("-upd"))).upper(),
            "serial_number": f"JPIT{_stable(n)[:8].upper()}",
            "asset_tag": f"AT-{_stable(n)[:8]}",
        }},
    },
    {
        "id": "restricted_software",
        "accessor": "restricted_software",
        "root": "restricted_software",
        "min": lambda n: {"general": {"name": n, "process_name": f"{n}.app"}},
        "max": lambda n: {"general": {
            "name": n,
            "process_name": f"{n}.app",
            "match_exact_process_name": True,
            "send_notification": False,
            "kill_process": False,
            "delete_executable": False,
            "display_message": f"blocked by {n}",
        }},
    },
    {
        "id": "account_users",
        "accessor": "accounts.users",
        "root": "account",
        "min": lambda n: {
            "name": n,
            "password": _password(n),
            "access_level": "Full Access",
            "privilege_set": "Custom",
        },
        "max": lambda n: {
            "name": n,
            "password": _password(n),
            "access_level": "Full Access",
            "privilege_set": "Custom",
            "full_name": f"Jamfpy IT {n[-8:]}",
            "email": f"{n}@example.com",
            "force_password_change": False,
        },
        "unassertable": ("password", "email"),  # password never echoes; email reshapes
    },
    {
        "id": "account_groups",
        "accessor": "accounts.groups",
        "root": "group",
        "min": lambda n: {
            "name": n,
            "access_level": "Full Access",
            "privilege_set": "Custom",
        },
        "max": lambda n: {
            "name": n,
            "access_level": "Full Access",
            "privilege_set": "Custom",
            "privileges": {"jss_objects": {"privilege": "Read Categories"}},
        },
        "unassertable": ("privileges",),  # reads back as lists
    },
]


def _params():
    return [pytest.param(spec, id=spec["id"]) for spec in SPECS]


@pytest.mark.parametrize("spec", _params())
def test_classic_lifecycle_min(tenant, unique_name, janitor, spec):
    """Full CRUD cycle with only the resource's required fields."""
    run_classic_lifecycle(tenant.classic, spec, spec["min"], unique_name, janitor)


@pytest.mark.parametrize("spec", _params())
def test_classic_lifecycle_max(tenant, unique_name, janitor, spec):
    """Full CRUD cycle with every writable field populated."""
    run_classic_lifecycle(tenant.classic, spec, spec["max"], unique_name, janitor)
