"""Concurrency: many ``get_by_id`` calls from a thread pool, all sharing one ``Tenant``.

One tenant is safe to share between threads: the ``Authorization`` header goes on each request rather than on
the shared session, and the token is refreshed under a lock, so threads that find it due together make one
token request.

``Tenant(parallelism=...)`` does not limit this. It caps only the fan-out jamfpy starts itself (the pages of a
Pro ``get_all``) and never throttles, queues or serialises requests the caller makes. Here the pool's
``max_workers`` is the only limit, so keep it modest: Jamf recommends no more than five concurrent connections
from one client.

Run it from the repository root (it only reads):

    uv run --env-file .env python examples/concurrent_requests.py

Needs ``JAMFPRO_INSTANCE_FQDN``, ``JAMFPRO_CLIENT_ID`` and ``JAMFPRO_CLIENT_SECRET`` (see ``.env.example``).
"""

import os
from concurrent.futures import ThreadPoolExecutor

import jamfpy

MAX_WORKERS = 5
MAX_RECORDS = 20


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
    """List the Classic categories, then read up to ``MAX_RECORDS`` of them by id in parallel."""
    tenant = jamfpy.Tenant(
        fqdn=tenant_fqdn(),
        auth_method="oauth2",
        client_id=require_env("JAMFPRO_CLIENT_ID"),
        client_secret=require_env("JAMFPRO_CLIENT_SECRET"),
    )
    try:
        listing = tenant.classic.categories.get_all()
        if not listing.ok:
            print("Listing categories failed with", listing.status_code)
            return
        ids = [int(category["id"]) for category in listing.json()["categories"]][:MAX_RECORDS]

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            # map keeps the input order, so each response lines up with its id.
            responses = list(pool.map(tenant.classic.categories.get_by_id, ids))

        for category_id, response in zip(ids, responses):
            if response.ok:
                print(category_id, response.json()["category"]["name"])
            else:
                print(category_id, "failed with", response.status_code)
        print(f"Read {len(responses)} categories on up to {MAX_WORKERS} threads")
    finally:
        tenant.classic.close()


if __name__ == "__main__":
    main()
