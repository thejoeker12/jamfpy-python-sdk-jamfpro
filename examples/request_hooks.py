"""Request hooks: counting and timing every request jamfpy sends, without wrapping the SDK.

``tenant.hooks`` is shared by both APIs. ``before_request``, ``after_response`` and ``on_retry`` register a
function and return it, so each works as a decorator; ``remove`` unregisters it. Every hook gets a
``jamfpy.RequestContext``: the tenant's FQDN, the API (``"pro"`` or ``"classic"``), the attempt number and the
monotonic time the attempt started.

Hooks fire per HTTP attempt, for API requests only (never the token fetch), and can run on several threads at
once: a Pro ``get_all`` fetches its pages on worker threads. So the shared counters here sit behind a lock.

Run it from the repository root (it only reads):

    uv run --env-file .env python examples/request_hooks.py

Needs ``JAMFPRO_INSTANCE_FQDN``, ``JAMFPRO_CLIENT_ID`` and ``JAMFPRO_CLIENT_SECRET`` (see ``.env.example``).
"""

import os
import threading
import time
from collections import Counter

from requests import PreparedRequest, Response

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


class RequestStats:
    """Counts of requests, statuses and retries, and the slowest attempt, safe to update from any thread."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.sent: Counter[str] = Counter()
        self.statuses: Counter[int] = Counter()
        self.retries = 0
        self.slowest_ms = 0.0

    def request_sent(self, api: str) -> None:
        """Count one attempt sent through ``api``."""
        with self._lock:
            self.sent[api] += 1

    def response_received(self, status: int, elapsed_ms: float) -> None:
        """Count one response and keep the slowest time seen."""
        with self._lock:
            self.statuses[status] += 1
            self.slowest_ms = max(self.slowest_ms, elapsed_ms)

    def retry_scheduled(self) -> None:
        """Count one retry."""
        with self._lock:
            self.retries += 1


def main() -> None:
    """Register three hooks, send some requests, print what they saw and remove them."""
    tenant = jamfpy.Tenant(
        fqdn=tenant_fqdn(),
        auth_method="oauth2",
        client_id=require_env("JAMFPRO_CLIENT_ID"),
        client_secret=require_env("JAMFPRO_CLIENT_SECRET"),
    )
    stats = RequestStats()

    @tenant.hooks.before_request
    def count_request(_prepared: PreparedRequest, ctx: jamfpy.RequestContext) -> None:
        """Count each attempt before it is sent."""
        stats.request_sent(ctx.api)

    @tenant.hooks.after_response
    def record_response(_prepared: PreparedRequest, response: Response, ctx: jamfpy.RequestContext) -> None:
        """Count each response, whatever its status, with how long its attempt took."""
        stats.response_received(response.status_code, (time.monotonic() - ctx.started) * 1000)

    @tenant.hooks.on_retry
    def record_retry(prepared: PreparedRequest, ctx: jamfpy.RequestContext, reason: Response | Exception, delay: float) -> None:
        """Count each retry and say why it happens."""
        stats.retry_scheduled()
        # The prepared request carries the real Authorization header, so only the method and URL are printed.
        cause = f"HTTP {reason.status_code}" if isinstance(reason, Response) else type(reason).__name__
        print(f"retrying {prepared.method} {prepared.url} after attempt {ctx.attempt} ({cause}) in {delay:.1f} s")

    try:
        tenant.classic.categories.get_all()
        # Small pages, so a tenant with a handful of scripts still shows one hook call per page.
        tenant.pro.scripts.get_all(page_size=10)
    finally:
        for hook in (count_request, record_response, record_retry):
            tenant.hooks.remove(hook)
        tenant.classic.close()

    print("Attempts sent per API:", dict(stats.sent))
    print("Responses per status:", dict(stats.statuses))
    print("Retries:", stats.retries)
    print(f"Slowest attempt: {stats.slowest_ms:.0f} ms")


if __name__ == "__main__":
    main()
