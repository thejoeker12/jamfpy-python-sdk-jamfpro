"""Calling an endpoint jamfpy does not wrap: build the request yourself and send it through ``api.do()``.

``do()`` is the one place every jamfpy request goes through, so a request sent this way gets the token, the
retries, the logging and the hooks exactly as an endpoint method's would. ``api.url()`` gives the base URL
(the Pro API needs the version, here ``"1"`` for ``/api/v1``) and ``api.header()`` the configured header sets.

The path is ``GET /v1/jamf-pro-version`` (``make schema-paths API=pro MATCH=jamf-pro-version``), which is
read-only. The example also passes ``timeout=`` to ``do()``, which overrides the tenant's timeout for that one
request.

Run it from the repository root (it only reads):

    uv run --env-file .env python examples/unwrapped_endpoint.py

Needs ``JAMFPRO_INSTANCE_FQDN``, ``JAMFPRO_CLIENT_ID`` and ``JAMFPRO_CLIENT_SECRET`` (see ``.env.example``).
"""

import os

from requests import Request

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


def main() -> None:
    """Read the Jamf Pro version through ``do()`` with a per-call timeout."""
    tenant = jamfpy.Tenant(
        fqdn=tenant_fqdn(),
        auth_method="oauth2",
        client_id=require_env("JAMFPRO_CLIENT_ID"),
        client_secret=require_env("JAMFPRO_CLIENT_SECRET"),
    )
    try:
        request = Request(
            "GET",
            tenant.pro.url("1") + "/jamf-pro-version",
            headers=tenant.pro.header("read")["json"],
        )
        # A short connect phase and a longer read phase, for this request only; a token fetch it triggers
        # still uses the tenant's own timeout.
        response = tenant.pro.do(request, timeout=(5.0, 30.0))
        if response.ok:
            print("Jamf Pro version:", response.json().get("version"))
        else:
            print("Reading the version failed with", response.status_code)
    finally:
        tenant.pro.close()


if __name__ == "__main__":
    main()
