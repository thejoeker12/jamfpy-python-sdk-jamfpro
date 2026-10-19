"""Logging: seeing what jamfpy does, as text at INFO and as JSON at DEBUG.

jamfpy prints nothing until asked. ``jamfpy.configure_logging()`` attaches one handler to the ``jamfpy``
logger (calling it again replaces that handler), and ``Tenant(log_level=...)`` sets what the tenant's own
loggers emit. DEBUG output needs both turned down to DEBUG.

At DEBUG jamfpy logs each request's headers and body. ``safe_mode=True`` (the default, kept here) redacts the
``Authorization`` header, cookies and credential fields such as ``client_secret`` before they are written.

Run it from the repository root (it only reads):

    uv run --env-file .env python examples/logging_output.py

Needs ``JAMFPRO_INSTANCE_FQDN``, ``JAMFPRO_CLIENT_ID`` and ``JAMFPRO_CLIENT_SECRET`` (see ``.env.example``).
"""

import logging
import os

import jamfpy


def require_env(name: str) -> str:
    """The value of an environment variable this example needs, or exit naming the one that is missing."""
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"Set {name}: copy .env.example to .env and run with uv run --env-file .env")
    return value


def tenant_fqdn() -> str:
    """The tenant URL from ``JAMFPRO_INSTANCE_FQDN``.

    ``Tenant`` needs the scheme, and a ``.env`` often holds the bare host, so ``https://`` is added when missing.
    """
    fqdn = require_env("JAMFPRO_INSTANCE_FQDN")
    return fqdn if fqdn.startswith("http") else f"https://{fqdn}"


def build_tenant(log_level: int) -> jamfpy.Tenant:
    """A tenant whose three loggers (``jamfpy.<name>-auth``, ``-pro`` and ``-clc``) emit at ``log_level``."""
    return jamfpy.Tenant(
        fqdn=tenant_fqdn(),
        auth_method="oauth2",
        client_id=require_env("JAMFPRO_CLIENT_ID"),
        client_secret=require_env("JAMFPRO_CLIENT_SECRET"),
        log_level=log_level,
        # False would log the bearer token, the client secret and the issued tokens in full:
        # only ever against a development tenant.
        safe_mode=True,
    )


def text_at_info() -> None:
    """One INFO line per request attempt, in the text format."""
    print("--- text, INFO ---")
    jamfpy.configure_logging(level=logging.INFO, fmt="text")
    tenant = build_tenant(logging.INFO)
    try:
        tenant.classic.categories.get_all()
    finally:
        tenant.classic.close()


def json_at_debug() -> None:
    """The same request in JSON at DEBUG: the token fetch and the redacted headers and bodies as well."""
    print("--- JSON, DEBUG ---")
    # Replaces the text handler installed above rather than adding a second one.
    jamfpy.configure_logging(level=logging.DEBUG, fmt="json")
    tenant = build_tenant(logging.DEBUG)
    try:
        tenant.classic.categories.get_all()
    finally:
        tenant.classic.close()


def main() -> None:
    """Log the same request in both formats."""
    text_at_info()
    json_at_debug()


if __name__ == "__main__":
    main()
