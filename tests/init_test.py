"""Smoke test for the jamfpy public surface (formalizes the AGENTS.md import check)."""
# pylint: disable=missing-function-docstring
import pytest

import jamfpy

PUBLIC_NAMES = ["Tenant", "OAuth", "BasicAuth", "API", "ProAPI", "ClassicAPI", "new_logger"]


@pytest.mark.parametrize("name", PUBLIC_NAMES)
def test_public_name_is_exported(name):
    assert hasattr(jamfpy, name)


def test_tenant_is_a_class():
    assert isinstance(jamfpy.Tenant, type)
