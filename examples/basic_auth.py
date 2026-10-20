"""Basic authentication: a tenant built from a Jamf Pro user's username and password.

jamfpy exchanges the credentials for a bearer token (``POST /api/v1/auth/token``) and keeps it alive as it nears
expiry; API requests carry the bearer token, never the credentials.

Run it from the repository root (it only reads):

    uv run --env-file .env python examples/basic_auth.py

Needs ``JAMFPRO_INSTANCE_FQDN``, ``JAMFPRO_USERNAME`` and ``JAMFPRO_PASSWORD``. The last two are not in
``.env.example``: only this example reads them, so add them to your ``.env`` or export them.
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
    """Authenticate with a username and password, then list the Classic categories."""
    tenant = jamfpy.Tenant(
        fqdn=tenant_fqdn(),
        auth_method="basic",
        username=require_env("JAMFPRO_USERNAME"),
        password=require_env("JAMFPRO_PASSWORD"),
    )
    try:
        tenant.authenticate()
        print("Authenticated as a Jamf Pro user")

        categories = tenant.classic.categories.get_all()
        if categories.ok:
            print(f"{len(categories.json()['categories'])} categories")
        else:
            print("Listing categories failed with", categories.status_code)
    finally:
        tenant.classic.close()


if __name__ == "__main__":
    main()
