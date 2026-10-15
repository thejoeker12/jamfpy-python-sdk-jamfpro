"""Smoke test for the jamfpy public surface (formalizes the AGENTS.md import check)."""
# pylint: disable=missing-function-docstring
import pytest

import jamfpy
from jamfpy.client import logger as jamfpy_logger

PUBLIC_NAMES = [
    "Tenant", "OAuth", "BasicAuth", "API", "ProAPI", "ClassicAPI", "configure_logging", "Timeout", "RetryConfig", "Hooks",
    "RequestContext",
]


@pytest.mark.parametrize("name", PUBLIC_NAMES)
def test_public_name_is_exported(name):
    assert hasattr(jamfpy, name)
    assert name in jamfpy.__all__


def test_tenant_is_a_class():
    assert isinstance(jamfpy.Tenant, type)


def test_new_logger_is_gone():
    # Removed in favour of configure_logging(); a leftover export would hand out handler-stacking loggers again.
    assert not hasattr(jamfpy, "new_logger")
    assert "new_logger" not in jamfpy.__all__
    assert not hasattr(jamfpy_logger, "new_logger")
