"""Certificates and proxies: ``verify_path``, ``cert_path`` and the environment variables requests honours.

Requests are TLS-verified by default and never sent unverified.

- ``verify_path`` is a CA bundle to verify the server's certificate against, for a private CA. When it is set
  it wins over ``REQUESTS_CA_BUNDLE`` and ``CURL_CA_BUNDLE``, which are honoured otherwise.
- ``cert_path`` is one PEM file holding a client certificate and its key, for mutual TLS.
- ``HTTP_PROXY``, ``HTTPS_PROXY`` and ``NO_PROXY`` are honoured for API and auth calls alike.

Both paths must be existing files, or ``Tenant`` raises ``JamfpyConfigError``. This example takes them from two
optional variables of its own and runs without them when they are unset.

Run it from the repository root (it only reads):

    uv run --env-file .env python examples/certificates.py

Needs ``JAMFPRO_INSTANCE_FQDN``, ``JAMFPRO_CLIENT_ID`` and ``JAMFPRO_CLIENT_SECRET`` (see ``.env.example``).
Optional, read only by this example: ``JAMFPY_EXAMPLE_CA_BUNDLE`` (a CA bundle, passed as ``verify_path``) and
``JAMFPY_EXAMPLE_CLIENT_CERT`` (a PEM with certificate and key, passed as ``cert_path``).
"""

import os

import jamfpy

CA_BUNDLE_VAR = "JAMFPY_EXAMPLE_CA_BUNDLE"
CLIENT_CERT_VAR = "JAMFPY_EXAMPLE_CLIENT_CERT"
# Read by requests itself; listed so the example can say which ones apply to this run.
REQUESTS_ENV_VARS = ("REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY")


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


def optional_path(name: str, unset_note: str) -> str | None:
    """The path in environment variable ``name``, or ``None`` after saying what happens without it."""
    path = os.environ.get(name) or None
    print(f"{name}: {path}" if path else f"{name} not set: {unset_note}")
    return path


def main() -> None:
    """Build a tenant with whatever certificates are configured and send one read."""
    verify_path = optional_path(CA_BUNDLE_VAR, "verifying against the default CA bundle")
    cert_path = optional_path(CLIENT_CERT_VAR, "no client certificate")
    # Values are left out: a proxy URL can carry credentials.
    for name in REQUESTS_ENV_VARS:
        print(f"{name}: {'set' if os.environ.get(name) else 'not set'}")

    tenant = jamfpy.Tenant(
        fqdn=tenant_fqdn(),
        auth_method="oauth2",
        client_id=require_env("JAMFPRO_CLIENT_ID"),
        client_secret=require_env("JAMFPRO_CLIENT_SECRET"),
        verify_path=verify_path,
        cert_path=cert_path,
    )
    try:
        response = tenant.classic.categories.get_all()
        print("Categories read over verified TLS:", response.status_code)
    finally:
        tenant.classic.close()


if __name__ == "__main__":
    main()
