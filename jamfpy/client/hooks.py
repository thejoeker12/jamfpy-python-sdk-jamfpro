"""Request hooks: callables the API runs around every HTTP attempt it makes, for metrics, tracing or auditing.

Hooks fire per HTTP attempt, not per SDK operation, and for API requests only, never for auth calls. Per
attempt: ``before_request``, then the send, then exactly one of ``after_response`` (any response, whatever
its status, including one about to be retried) or nothing, when the send raised. If a retry follows,
``on_retry`` fires after that, before the sleep, with the response or exception as ``reason``. Return values
are ignored and mutating the arguments is unsupported. A hook that raises is logged at WARNING with its
``__qualname__`` and the request carries on. Hooks may be called from several threads at once and must be
thread-safe. The prepared request carries the real ``Authorization`` header; a consumer that persists
requests redacts it itself.
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass
from logging import Logger

from requests import PreparedRequest, Response


@dataclass(frozen=True)
class RequestContext:
    """What a hook knows about the attempt it is called for.

    ``tenant`` is the tenant's FQDN, a plain string, so hooks also work for an API built without a ``Tenant``
    and never hold the object that carries the credentials. ``api`` is ``"pro"`` or ``"classic"``.
    ``attempt`` is 1 for the first attempt and goes up by one per retry. ``started`` is ``time.monotonic()``
    when the attempt started (after the request is prepared, so a token fetch is not counted).
    """

    tenant: str
    api: str
    attempt: int
    started: float


BeforeRequestHook = Callable[[PreparedRequest, RequestContext], None]
AfterResponseHook = Callable[[PreparedRequest, Response, RequestContext], None]
OnRetryHook = Callable[[PreparedRequest, RequestContext, Response | Exception, float], None]


class Hooks:
    """The hooks registered for one tenant (or one API). Safe to register and remove from any thread.

    Each registration method returns the function it was given, so it also works as a decorator::

        @tenant.hooks.after_response
        def record(prepared, response, ctx):
            ...
    """

    def __init__(self) -> None:
        # Guards the lists against concurrent register/remove; held only to change or copy a list, never while a hook
        # runs. The snapshot each _fire_* dispatches over is what makes registering or removing from inside a hook
        # safe, and why a hook that re-registers itself cannot loop.
        self._lock = threading.Lock()
        self._before_request: list[BeforeRequestHook] = []
        self._after_response: list[AfterResponseHook] = []
        self._on_retry: list[OnRetryHook] = []

    def before_request[F: BeforeRequestHook](self, fn: F) -> F:
        """Register ``fn(prepared, ctx)`` to run before each attempt is sent; returns ``fn``."""
        with self._lock:
            self._before_request.append(fn)
        return fn

    def after_response[F: AfterResponseHook](self, fn: F) -> F:
        """Register ``fn(prepared, response, ctx)`` to run after each attempt that got a response; returns ``fn``."""
        with self._lock:
            self._after_response.append(fn)
        return fn

    def on_retry[F: OnRetryHook](self, fn: F) -> F:
        """Register ``fn(prepared, ctx, reason, delay)`` to run before each retry's sleep; returns ``fn``."""
        with self._lock:
            self._on_retry.append(fn)
        return fn

    def remove(self, fn: Callable[..., None]) -> None:
        """Unregister ``fn`` from every hook list it is in. Removing a function that isn't registered does nothing."""
        with self._lock:
            # Filtered rather than list.remove'd, so a function registered more than once goes in one call.
            self._before_request = [hook for hook in self._before_request if hook != fn]
            self._after_response = [hook for hook in self._after_response if hook != fn]
            self._on_retry = [hook for hook in self._on_retry if hook != fn]

    def _fire_before_request(self, logger: Logger, prepared: PreparedRequest, ctx: RequestContext) -> None:
        with self._lock:
            hooks = tuple(self._before_request)
        _call_each(logger, hooks, prepared, ctx)

    def _fire_after_response(self, logger: Logger, prepared: PreparedRequest, response: Response, ctx: RequestContext) -> None:
        with self._lock:
            hooks = tuple(self._after_response)
        _call_each(logger, hooks, prepared, response, ctx)

    def _fire_on_retry(
            self, logger: Logger, prepared: PreparedRequest, ctx: RequestContext, reason: Response | Exception, delay: float
    ) -> None:
        with self._lock:
            hooks = tuple(self._on_retry)
        _call_each(logger, hooks, prepared, ctx, reason, delay)


def _call_each(logger: Logger, hooks: tuple[Callable[..., None], ...], *args: object) -> None:
    """Call every hook in turn; a hook that raises is logged and skipped so the request carries on."""
    for hook in hooks:
        try:
            hook(*args)
        # A broken metrics or audit hook must never fail the API call it observes.
        except Exception:  # pylint: disable=broad-exception-caught
            name = getattr(hook, "__qualname__", repr(hook))
            logger.warning("Request hook %s raised; continuing with the request", name, exc_info=True)
