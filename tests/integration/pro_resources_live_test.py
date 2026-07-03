"""Live min/max lifecycle tests for every CRUD-capable Pro resource.

Same spec pattern as the Classic suite, JSON both ways. Not covered here (see
COVERAGE.md → *Live integration test coverage*): ``pro.mdm`` is a verb endpoint
with no CRUD surface, and ``pro.app_installers`` needs an App Installers
catalog title + accepted T&Cs on the instance.
"""
# pylint: disable=redefined-outer-name
import pytest

from .lifecycle import run_pro_lifecycle

pytestmark = pytest.mark.integration


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
]


def _params():
    return [pytest.param(spec, id=spec["id"]) for spec in SPECS]


@pytest.mark.parametrize("spec", _params())
def test_pro_lifecycle_min(tenant, unique_name, janitor, spec):
    """Full CRUD cycle with only the resource's required fields."""
    run_pro_lifecycle(tenant.pro, spec, spec["min"], unique_name, janitor)


@pytest.mark.parametrize("spec", _params())
def test_pro_lifecycle_max(tenant, unique_name, janitor, spec):
    """Full CRUD cycle with every writable field populated."""
    run_pro_lifecycle(tenant.pro, spec, spec["max"], unique_name, janitor)
