"""Pagination: a Pro ``get_all`` pages through the whole collection and returns one Response.

``get_all(page_size=..., sort=...)`` fetches page 0, then the remaining pages, up to ``parallelism`` at a time
on worker threads (``Tenant(parallelism=5)`` by default, ``1`` for one page at a time on the calling thread).
When every page is ok the result is one Response whose body is ``{"totalCount": N, "results": [...]}``, in the
server's order. When a page fails, no further pages are started and that page's own Response comes back raw,
so check ``.ok`` before reading the body.

The example lists the Pro scripts in pages of 50, sorted by name, once in parallel and once sequentially, and
checks both give the same records in the same order.

Run it from the repository root (it only reads):

    uv run --env-file .env python examples/pagination.py

Needs ``JAMFPRO_INSTANCE_FQDN``, ``JAMFPRO_CLIENT_ID`` and ``JAMFPRO_CLIENT_SECRET`` (see ``.env.example``).
"""

import os

import jamfpy

PAGE_SIZE = 50
SORT = "name:asc"


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


def script_ids(parallelism: int) -> list[str] | None:
    """Every script id, in name order, fetched with ``parallelism``; ``None`` when a page failed."""
    tenant = jamfpy.Tenant(
        fqdn=tenant_fqdn(),
        auth_method="oauth2",
        client_id=require_env("JAMFPRO_CLIENT_ID"),
        client_secret=require_env("JAMFPRO_CLIENT_SECRET"),
        parallelism=parallelism,
    )
    try:
        scripts = tenant.pro.scripts.get_all(page_size=PAGE_SIZE, sort=SORT)
        if not scripts.ok:
            # The failed page itself: its URL names the page, its body says why.
            print(f"parallelism={parallelism}: a page failed with {scripts.status_code} at {scripts.url}")
            return None
        body = scripts.json()
        names = [script["name"] for script in body["results"]]
        print(f"parallelism={parallelism}: {body['totalCount']} scripts, first {names[:3]}")
        return [script["id"] for script in body["results"]]
    finally:
        tenant.pro.close()


def main() -> None:
    """List the scripts in parallel and sequentially, and compare."""
    parallel = script_ids(parallelism=5)
    sequential = script_ids(parallelism=1)
    if parallel is not None and sequential is not None:
        print("Same records in the same order:", parallel == sequential)


if __name__ == "__main__":
    main()
