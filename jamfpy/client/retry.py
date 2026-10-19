"""Retry policy for API requests: what ``API.do()`` retries, and how long it waits between attempts."""

import datetime
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from logging import Logger

from requests import PreparedRequest, Response
from requests.exceptions import ConnectTimeout, ConnectionError as RequestsConnectionError, ReadTimeout, SSLError


@dataclass(frozen=True)
class RetryConfig:
    """How ``API.do()`` retries a failed attempt. Pass ``retries=None`` to ``Tenant`` to turn retries off.

    ``total`` is the number of retries after the first attempt, so the default makes at most four attempts.
    A status in ``statuses`` is retried for a method in ``methods``, and for POST only when ``retry_post``
    is set: POST is not idempotent, so a second one can create a second record. ``ReadTimeout`` and
    ``ConnectionError`` (``ProxyError`` included) follow the same method rule, because the server may have
    processed the request. ``ConnectTimeout`` is retried for every method, POST included, because the
    connection never opened. ``SSLError`` and every other exception propagate at once.

    The delay before retry ``n`` (``n`` being the attempt that just failed) is
    ``backoff_factor * 2 ** (n - 1)`` capped at ``max_backoff``, then, with ``jitter``, drawn uniformly
    between 0 and that value. A ``Retry-After`` header on a retried response replaces the delay; one longer
    than ``max_backoff`` ends the retries and the response is returned.

    The fields are validated when the config is built: ``total`` must be an integer and ``backoff_factor`` and
    ``max_backoff`` numbers, none of them negative, and ``statuses`` (ints) and ``methods`` (strings) must be
    collections, not a bare string such as ``methods="GET"``. They are stored as tuples. A bad value raises
    ``ValueError``.
    """

    total: int = 3
    backoff_factor: float = 0.5
    max_backoff: float = 30.0
    jitter: bool = True
    statuses: tuple[int, ...] = (429, 500, 502, 503, 504)
    methods: tuple[str, ...] = ("GET", "HEAD", "OPTIONS", "PUT", "DELETE")
    retry_post: bool = False

    def __post_init__(self) -> None:
        # Checked here rather than at the first retry, so a typo fails at construction instead of surfacing mid-outage.
        _require_non_negative("total", self.total, int)
        _require_non_negative("backoff_factor", self.backoff_factor, (int, float))
        _require_non_negative("max_backoff", self.max_backoff, (int, float))
        # The dataclass is frozen, so plain assignment raises; object.__setattr__ is the supported way to normalise
        # in __post_init__. Tuples keep the config hashable however the caller spelled the collection.
        object.__setattr__(self, "statuses", _as_tuple("statuses", self.statuses, int))
        object.__setattr__(self, "methods", _as_tuple("methods", self.methods, str))


class RetryPolicy:
    """A ``RetryConfig`` with the sleep and random source it runs on: the decisions behind ``API.do()``'s retry loop.

    jamfpy-internal. ``API`` builds one from its ``retries``, ``sleep`` and ``random_source`` arguments.
    """

    def __init__(self, config: RetryConfig, sleep: Callable[[float], None], random_source: Callable[[], float]) -> None:
        self.config = config
        self.sleep = sleep
        self._random_source = random_source

    def delay(
            self, logger: Logger, prepped: PreparedRequest, outcome: Response | Exception, attempt: int,
            *, extra: Mapping[str, object] | None = None,
    ) -> float | None:
        """Seconds to wait before resending after ``attempt`` (1-based) ended in ``outcome``; ``None`` to stop.

        Stopping hands ``outcome`` back to the caller: a response is returned, an exception raised. Giving up on an
        outcome that was otherwise retryable (retries exhausted, or a ``Retry-After`` beyond ``max_backoff``) is
        logged at ERROR, with ``extra`` (the attempt's structured log fields) on the record.
        """
        # prepare_request always sets the method; requests only types it as optional.
        method = prepped.method or ""
        if not self._is_retryable(method, outcome):
            return None

        if attempt > self.config.total:
            logger.error(
                "Giving up on %s %s after %d attempt(s): %s", method, prepped.url, attempt, describe_outcome(outcome), extra=extra
            )
            return None

        retry_after = None
        if isinstance(outcome, Response):
            retry_after = parse_retry_after(outcome.headers.get("Retry-After"), datetime.datetime.now(datetime.timezone.utc))
        if retry_after is None:
            return backoff_delay(self.config, attempt, self._random_source)

        if retry_after > self.config.max_backoff:
            # Sleeping less than the server asked for would only earn another 429 or 503.
            logger.error(
                "Giving up on %s %s at attempt %d: %s asked to retry after %.1f s, beyond max_backoff of %.1f s",
                method, prepped.url, attempt, describe_outcome(outcome), retry_after, self.config.max_backoff, extra=extra
            )
            return None
        return retry_after

    def _method_allowed(self, method: str) -> bool:
        """True when a request with this method may be resent after a status, read timeout or connection error."""
        method = method.upper()
        if method == "POST" and self.config.retry_post:
            return True
        return method in {allowed.upper() for allowed in self.config.methods}

    def _is_retryable(self, method: str, outcome: Response | Exception) -> bool:
        if isinstance(outcome, Response):
            return outcome.status_code in self.config.statuses and self._method_allowed(method)
        # Order matters: SSLError and ConnectTimeout both subclass ConnectionError. A TLS failure won't fix itself on a
        # resend, and a connect timeout never reached the server, so it is safe to resend even a POST.
        if isinstance(outcome, SSLError):
            return False
        if isinstance(outcome, ConnectTimeout):
            return True
        if isinstance(outcome, (ReadTimeout, RequestsConnectionError)):
            return self._method_allowed(method)
        return False


def _require_non_negative(name: str, value: float, kinds: type | tuple[type, ...]) -> None:
    """Raise ``ValueError`` unless ``value`` is a number of ``kinds`` that is zero or more."""
    # The annotation is what the field declares; the isinstance check is for callers who ignore it. bool is an int
    # subclass, but total=True is a mistake, not a request for one retry. ``not value >= 0`` also rejects NaN.
    if isinstance(value, bool) or not isinstance(value, kinds) or not value >= 0:
        raise ValueError(f"{name} must be {'an integer' if kinds is int else 'a number'} that is zero or more, got {value!r}")


def _as_tuple[T](name: str, value: object, kind: type[T]) -> tuple[T, ...]:
    """Return ``value`` as a tuple of ``kind``, or raise ``ValueError`` if it isn't a collection of them."""
    if isinstance(value, (str, bytes)):
        # A bare string is iterable, so it would otherwise be split into characters and silently never match.
        one = repr(value) if isinstance(value, str) and kind is str else f"<{kind.__name__}>"
        raise ValueError(f"{name} must be a tuple of {kind.__name__}, not a bare string; for one value write {name}=({one},)")
    if not isinstance(value, Iterable):
        raise ValueError(f"{name} must be a tuple of {kind.__name__}, got {value!r}")
    items = tuple(value)
    wrong = [item for item in items if isinstance(item, bool) or not isinstance(item, kind)]
    if wrong:
        raise ValueError(f"{name} must hold only {kind.__name__} values, got {wrong!r}")
    return items


def describe_outcome(outcome: Response | Exception) -> str:
    """Short reason for a retry or give-up log line: ``HTTP 503``, or the exception's class and message."""
    if isinstance(outcome, Response):
        return f"HTTP {outcome.status_code}"
    return f"{type(outcome).__name__}: {outcome}"


def backoff_delay(config: RetryConfig, attempt: int, random_source: Callable[[], float]) -> float:
    """Seconds to wait after ``attempt`` (1-based) failed, when the response gives no ``Retry-After``."""
    # Capped before the jitter is applied ("full jitter"), so later retries still spread across the whole window
    # instead of piling up at the cap.
    delay: float = min(config.backoff_factor * 2 ** (attempt - 1), config.max_backoff)
    if config.jitter:
        delay *= random_source()
    return delay


def parse_retry_after(value: str | None, now: datetime.datetime) -> float | None:
    """Seconds a ``Retry-After`` value asks for: delay-seconds, or an HTTP-date relative to ``now`` (RFC 9110).

    Returns ``None`` when there is no header or it can't be parsed, so the caller falls back to its own backoff.
    A date in the past means no wait.
    """
    if value is None:
        return None

    value = value.strip()
    # isascii as well: isdigit also passes other scripts' digits and superscripts, but delay-seconds is ASCII DIGITs only.
    if value.isascii() and value.isdigit():
        return float(value)

    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None

    # An HTTP-date is always GMT; parsedate_to_datetime leaves a "-0000" zone naive.
    if when.tzinfo is None:
        when = when.replace(tzinfo=datetime.timezone.utc)
    return max(0.0, (when - now).total_seconds())
