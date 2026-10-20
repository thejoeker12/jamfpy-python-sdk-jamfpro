"""Timeouts and retries: the ``timeout`` and ``retries`` options of ``Tenant``.

- ``timeout`` is seconds for both the connect and the read phase, or a ``(connect, read)`` tuple. It applies to
  every API request and every auth call (default 30 seconds).
- ``retries`` takes a ``jamfpy.RetryConfig`` (the default retries 429 and 5xx three times with jittered
  exponential backoff, and never retries POST), or ``None`` for one attempt per request. Auth calls are never
  retried.

The example builds three tenants with different settings and sends the same read with each.

Run it from the repository root (it only reads):

    uv run --env-file .env python examples/timeouts_and_retries.py

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


def list_categories(label: str, timeout: jamfpy.Timeout, retries: jamfpy.RetryConfig | None) -> None:
    """Build a tenant with ``timeout`` and ``retries``, list the Classic categories once and close it."""
    tenant = jamfpy.Tenant(
        fqdn=tenant_fqdn(),
        auth_method="oauth2",
        client_id=require_env("JAMFPRO_CLIENT_ID"),
        client_secret=require_env("JAMFPRO_CLIENT_SECRET"),
        timeout=timeout,
        retries=retries,
    )
    try:
        response = tenant.classic.categories.get_all()
        print(f"{label}: {response.status_code}")
    finally:
        tenant.classic.close()


def main() -> None:
    """Send one read under each of three timeout and retry settings."""
    # One number covers both phases; the default retries apply.
    list_categories("timeout=10.0, default retries", 10.0, jamfpy.RetryConfig())

    # Fail fast on an unreachable host but give a slow response time to arrive. More, longer retries, and
    # retry_post=True, which resends a POST after a 5xx or a read timeout: only safe when a duplicate create is
    # harmless, because the first POST may already have created the record.
    patient = jamfpy.RetryConfig(
        total=5,
        backoff_factor=1.0,
        max_backoff=20.0,
        statuses=(429, 502, 503, 504),
        retry_post=True,
    )
    list_categories("timeout=(5.0, 60.0), RetryConfig(total=5, retry_post=True)", (5.0, 60.0), patient)

    # One attempt per request: the caller decides what to do with a 503 or a timeout.
    list_categories("timeout=30.0, retries=None", 30.0, None)


if __name__ == "__main__":
    main()
