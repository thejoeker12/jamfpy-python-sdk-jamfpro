"""Live min/max lifecycle tests for every CRUD-capable Pro resource.

Same spec pattern as the Classic suite, JSON both ways. A spec may also have a
``setup``: a function of the ``ProAPI`` returning keyword arguments for its
builders, for a payload that must name tenant state (``app_installers`` needs a
catalog title's id and version). A spec without a ``max`` builder runs only the min test, and
its optional ``notes`` is the Notes cell of COVERAGE.md's live table. A wired
endpoint with no spec has the reason in ``LIVE_NOT_COVERED`` instead (``pro.mdm``
is a verb endpoint); ``make coverage-doc`` refuses an endpoint with neither.
"""
# pylint: disable=redefined-outer-name
import pytest
from requests import Request

from .lifecycle import run_pro_lifecycle

pytestmark = pytest.mark.integration


def first_catalog_title(pro) -> dict:
    """The first App Installers catalog title's id and current version, as builder arguments.

    The catalog is Jamf's, so it is read here, never created.
    """
    resp = pro.do(Request(
        "GET", pro.url("1") + "/app-installers/titles?page=0&page-size=1", headers=pro.header("read")["json"],
    ))
    assert resp.status_code == 200, f"app-installers titles: {resp.status_code} {resp.text}"
    results = resp.json()["results"]
    assert results, "the App Installers catalog lists no titles"
    return {"title_id": results[0]["id"], "title_version": results[0]["version"]}


SPECS = [
    {
        "id": "scripts",
        "accessor": "scripts",
        "notes": "categoryId/categoryName omitted (instance-state dependent)",
        "min": lambda n: {"name": n},
        "max": lambda n: {
            "name": n,
            "info": f"info for {n}",
            "notes": f"notes for {n}",
            "priority": "AFTER",
            **{f"parameter{i}": f"{n}-p{i}" for i in range(4, 12)},
            "osRequirements": "15",
            "scriptContents": f'#!/bin/bash\necho "{n}"\n',
        },
        # categoryId/categoryName deliberately omitted — instance-state dependent.
    },
    {
        # All three fields are required and nothing else is writable
        # (`contents` is readOnly) — min and max are legitimately identical.
        "id": "dock_items",
        "accessor": "dock_items",
        "notes": "All fields required; min ≡ max",
        "min": lambda n: {
            "name": n,
            "type": "APP",
            "path": "file://localhost/Applications/Safari.app/",
        },
        "max": lambda n: {
            "name": n,
            "type": "APP",
            "path": "file://localhost/Applications/Safari.app/",
        },
    },
    {
        "id": "app_installers",
        "accessor": "app_installers",
        "notes": (
            "Undocumented by Jamf; the shapes are the probe's (`make schema-path API=pro PATH=/v1/app-installers/deployments`). "
            "Every deployment is `enabled: false`, so nothing reaches a device, and uses the first catalog title from "
            "`GET /v1/app-installers/titles` (the spec's `setup`). Min sends the four fields a 400 on `{}` names as required "
            "(`name`, `appTitleId`, `deploymentType`, `updateBehavior`). Max adds every other writable field the read-back "
            "has, with `updateBehavior: MANUAL` and the title's current version as `selectedVersion` (under `AUTOMATIC` the "
            "server blanks `selectedVersion`); `categoryId` and `siteId` are `-1`, the server's none. Left out: "
            "`smartGroupId` (the server takes `-1`, but a real group is tenant state the spec's `setup` cannot create and "
            "clean up), a non-empty `selfServiceSettings.categories` (the same), and the read-only `titleAvailableInAis`, "
            "`latestAvailableVersion` and `versionRemoved`. `get_all`'s pagination is proven live in "
            "`sdk_behaviour_live_test.py`."
        ),
        "setup": first_catalog_title,
        # title_version is only for max: min takes whatever setup returns and uses the id.
        "min": lambda n, title_id, **_: {
            "name": n,
            "appTitleId": title_id,
            "deploymentType": "SELF_SERVICE",
            "updateBehavior": "MANUAL",
            # Not required: sent so the deployment is never offered to a device, whatever the tenant defaults to.
            "enabled": False,
        },
        "max": lambda n, title_id, title_version: {
            "name": n,
            "appTitleId": title_id,
            "enabled": False,
            "deploymentType": "SELF_SERVICE",
            "updateBehavior": "MANUAL",
            "selectedVersion": title_version,
            "categoryId": "-1",
            "siteId": "-1",
            "installPredefinedConfigProfiles": True,
            "triggerAdminNotifications": True,
            "notificationSettings": {
                "notificationMessage": f"notification for {n}",
                "notificationInterval": 4,
                "deadlineMessage": f"deadline for {n}",
                "deadline": 2,
                "quitDelay": 3,
                "completeMessage": f"complete for {n}",
                "relaunch": True,
                "suppress": True,
            },
            "selfServiceSettings": {
                "includeInFeaturedCategory": True,
                "includeInComplianceCategory": True,
                "forceViewDescription": True,
                "description": f"description for {n}",
                "categories": [],
            },
        },
    },
]

# Wired endpoints with no spec, and why; COVERAGE.md shows them as N/A rows.
LIVE_NOT_COVERED: dict[str, str] = {
    "mdm": "Verb endpoint (send-command) with no CRUD surface to lifecycle-test",
}


def _params(kind):
    return [pytest.param(spec, id=spec["id"]) for spec in SPECS if kind in spec]


def _builder(spec, kind, pro):
    """The spec's ``kind`` payload builder, given whatever its ``setup`` fetched from the tenant."""
    build = spec[kind]
    if "setup" not in spec:
        return build
    state = spec["setup"](pro)
    return lambda name: build(name, **state)


@pytest.mark.parametrize("spec", _params("min"))
def test_pro_lifecycle_min(tenant, unique_name, janitor, spec):
    """Full CRUD cycle with only the resource's required fields."""
    run_pro_lifecycle(tenant.pro, spec, _builder(spec, "min", tenant.pro), unique_name, janitor)


@pytest.mark.parametrize("spec", _params("max"))
def test_pro_lifecycle_max(tenant, unique_name, janitor, spec):
    """Full CRUD cycle with every writable field populated."""
    run_pro_lifecycle(tenant.pro, spec, _builder(spec, "max", tenant.pro), unique_name, janitor)
