"""Quickstart: an OAuth tenant, one Classic read and one Pro read, checking ``.ok`` on each.

Builds a ``jamfpy.Tenant`` from the API client in the environment, fetches the token up front with
``authenticate()`` so bad credentials fail at once, lists the Classic buildings and the Pro scripts, and
invalidates the token at the end.

Run it from the repository root (it only reads):

    uv run --env-file .env python examples/quickstart.py

Needs ``JAMFPRO_INSTANCE_FQDN``, ``JAMFPRO_CLIENT_ID`` and ``JAMFPRO_CLIENT_SECRET`` (see ``.env.example``).
"""

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


def main() -> None:
    """List the Classic buildings and the Pro scripts."""
    tenant = jamfpy.Tenant(
        fqdn=tenant_fqdn(),
        auth_method="oauth2",
        client_id=require_env("JAMFPRO_CLIENT_ID"),
        client_secret=require_env("JAMFPRO_CLIENT_SECRET"),
    )
    try:
        # Building the tenant sent nothing; without this the first request would fetch the token.
        tenant.authenticate()

        buildings = tenant.classic.buildings.get_all()
        if buildings.ok:
            names = [building["name"] for building in buildings.json()["buildings"]]
            print(f"Classic: {len(names)} buildings {names[:5]}")
        else:
            # A non-2xx never raises: the Response comes back like any other.
            print("Classic: listing buildings failed with", buildings.status_code)

        scripts = tenant.pro.scripts.get_all()
        if scripts.ok:
            body = scripts.json()
            names = [script["name"] for script in body["results"]]
            print(f"Pro: {body['totalCount']} scripts {names[:5]}")
        else:
            print("Pro: listing scripts failed with", scripts.status_code, "at", scripts.url)
    finally:
        # Both APIs share one token, so closing either invalidates it for both.
        tenant.classic.close()


if __name__ == "__main__":
    main()
