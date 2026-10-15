"""Live min/max lifecycle tests for every CRUD-capable Pro resource.

Same spec pattern as the Classic suite, JSON both ways. A spec may also have a
``setup``: a function of the ``ProAPI`` returning keyword arguments for its
builders, for a payload that must name tenant state (``app_installers`` needs a
catalog title id). A spec without a ``max`` builder runs only the min test. Not
covered here (see COVERAGE.md → *Live integration test coverage*): ``pro.mdm``
is a verb endpoint with no CRUD surface.
"""
# pylint: disable=redefined-outer-name
import pytest
from requests import Request

from .lifecycle import run_pro_lifecycle

pytestmark = pytest.mark.integration


def _first_catalog_title_id(pro) -> str:
    """Any App Installers catalog title's id. The catalog is Jamf's, so it is read here, never created."""
    resp = pro.do(Request(
        "GET", pro.url("1") + "/app-installers/titles?page=0&page-size=1", headers=pro.header("read")["json"],
    ))
    assert resp.status_code == 200, f"app-installers titles: {resp.status_code} {resp.text}"
    results = resp.json()["results"]
    assert results, "the App Installers catalog lists no titles"
    return results[0]["id"]


SPECS = [
    {
        "id": "scripts",
        "accessor": "scripts",
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
        # The required fields are those a 400 on an empty body names: name, appTitleId, deploymentType and
        # updateBehavior. /v1/app-installers is in no published schema (only pro-supplement.json, which has no
        # bodies), so the writable fields are unknown and there is no max spec.
        "id": "app_installers",
        "accessor": "app_installers",
        "setup": lambda pro: {"title_id": _first_catalog_title_id(pro)},
        "min": lambda n, title_id: {
            "name": n,
            "appTitleId": title_id,
            "deploymentType": "SELF_SERVICE",
            "updateBehavior": "MANUAL",
            # Not required: sent so the deployment is never offered to a device, whatever the tenant defaults to.
            "enabled": False,
        },
    },
]


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
