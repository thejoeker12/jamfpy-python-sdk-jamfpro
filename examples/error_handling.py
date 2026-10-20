"""Error handling: what comes back as a Response and what raises.

Shows the four kinds of failure a caller meets:

1. A non-2xx status never raises: a ``get_by_id`` of an id that cannot exist returns a 404 ``Response``.
2. A bad configuration raises ``JamfpyConfigError`` when the ``Tenant`` is built, before anything is sent.
3. Credentials the server refuses raise ``JamfAuthError`` from ``authenticate()`` (or from the first request).
4. A network failure raises the ``requests`` exception once jamfpy has stopped retrying.

Run it from the repository root (it only reads; step 3 sends one token request with a wrong secret, and step 4
contacts a host under the reserved ``.invalid`` domain, which never resolves):

    uv run --env-file .env python examples/error_handling.py

Needs ``JAMFPRO_INSTANCE_FQDN``, ``JAMFPRO_CLIENT_ID`` and ``JAMFPRO_CLIENT_SECRET`` (see ``.env.example``).
"""

import os

import requests

import jamfpy
from jamfpy.client.exceptions import JamfAuthError, JamfpyConfigError

# Jamf assigns ids in sequence from 1, so no tenant holds this many categories.
MISSING_ID = 2**31 - 1
UNREACHABLE_FQDN = "https://jamfpy-example.invalid"


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


def missing_record() -> None:
    """Read a record that does not exist and branch on the status, as for any Response."""
    tenant = jamfpy.Tenant(
        fqdn=tenant_fqdn(),
        auth_method="oauth2",
        client_id=require_env("JAMFPRO_CLIENT_ID"),
        client_secret=require_env("JAMFPRO_CLIENT_SECRET"),
    )
    try:
        response = tenant.classic.categories.get_by_id(MISSING_ID)
        if response.status_code == 404:
            print(f"Category {MISSING_ID}: not found (404), as expected")
        elif not response.ok:
            print(f"Category {MISSING_ID}: failed with {response.status_code}")
        else:
            print(f"Category {MISSING_ID}: unexpectedly found")
    finally:
        tenant.classic.close()


def bad_configuration() -> None:
    """An empty secret is refused locally: ``Tenant`` validates its arguments before any request."""
    try:
        jamfpy.Tenant(fqdn=tenant_fqdn(), auth_method="oauth2", client_id=require_env("JAMFPRO_CLIENT_ID"), client_secret="")
    except JamfpyConfigError as exc:
        print("Configuration refused:", exc)


def refused_credentials() -> None:
    """A wrong secret gets past validation and is refused by the server's token endpoint."""
    tenant = jamfpy.Tenant(
        fqdn=tenant_fqdn(),
        auth_method="oauth2",
        client_id=require_env("JAMFPRO_CLIENT_ID"),
        client_secret="not-the-real-secret",
    )
    try:
        tenant.authenticate()
        print("Credentials: unexpectedly accepted")
    except JamfAuthError as exc:
        # str(exc) is redacted whatever safe_mode says; exc.args can hold the raw Response, so never log those.
        print("Credentials refused:", exc)
    finally:
        tenant.classic.close()


def unreachable_host() -> None:
    """A host that never answers: the requests exception reaches the caller.

    An API request that fails to connect is retried under ``RetryConfig`` first and raises the last exception
    when the retries run out. Here the first request has to fetch a token, and auth calls are never retried,
    so the token fetch raises at once.
    """
    tenant = jamfpy.Tenant(
        fqdn=UNREACHABLE_FQDN,
        auth_method="oauth2",
        client_id="example-client-id",
        client_secret="example-client-secret",
        timeout=5.0,
    )
    try:
        tenant.classic.categories.get_all()
        print("Unreachable host: unexpectedly answered")
    except requests.ConnectionError as exc:
        print("Unreachable host:", type(exc).__name__)
    except requests.RequestException as exc:
        # Timeouts and other transport failures share this base class.
        print("Unreachable host: other transport failure:", type(exc).__name__)
    finally:
        tenant.classic.close()


def main() -> None:
    """Run each failure in turn."""
    missing_record()
    bad_configuration()
    refused_credentials()
    unreachable_host()


if __name__ == "__main__":
    main()
