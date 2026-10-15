"""api model"""

import logging
import random
import time
from collections.abc import Callable
from logging import Logger
from typing import Any

from requests import PreparedRequest, Session, Request, Response
from requests.exceptions import ConnectionError as RequestsConnectionError, ReadTimeout

from .auth import Auth
from .constants import DEFAULT_TIMEOUT, Timeout
from .hooks import Hooks, RequestContext
from .http_config import HTTPConfig
from .logger import render_body, render_headers, tenant_logger
from .retry import RetryConfig, RetryPolicy, describe_outcome
from .utility import extract_cloud_tenant_name_from_url, user_agent
from .exceptions import JamfpyConfigError


class API:
    """Base class providing core functionality for interacting with Jamf Pro APIs.

    Safe to share between threads: ``do()`` puts the Authorization header on each request rather than on the
    session, so the session holds only the connection pool (which urllib3 guards), the cookie jar, the
    redirect cache and the headers set once here; nothing on it changes per request.

    ``retries`` sets how ``do()`` retries a failed attempt (``None`` turns retries off) and ``hooks`` the
    request hooks it fires (``None`` means none). ``sleep`` and ``random_source`` exist so tests can run the
    retry loop without waiting or randomness.
    """

    _headers_dict: dict[str, str] = {}
    _is_closed = False
    _short_name: str
    _version: str
    _http_config: HTTPConfig
    _logger: Logger

    def __init__(
            self,
            *,
            fqdn: str,
            auth: Auth,
            log_level: int,
            http_config: HTTPConfig,
            safe_mode: bool,
            session: Session | None,
            logger: Logger | None,
            cert_path: str | None = None,
            verify_path: str | None = None,
            timeout: Timeout = DEFAULT_TIMEOUT,
            retries: RetryConfig | None = RetryConfig(),
            hooks: Hooks | None = None,
            sleep: Callable[[float], None] = time.sleep,
            random_source: Callable[[], float] = random.random,
    ) -> None:

        self._fqdn = fqdn
        self.auth = auth
        self._http_config: HTTPConfig = http_config
        self.cert_path = cert_path
        self.verify_path = verify_path
        self._timeout = timeout
        self._retry = RetryPolicy(retries, sleep, random_source) if retries is not None else None
        self._hooks = hooks if hooks is not None else Hooks()

        self._session = session or Session()
        # do() resolves verify/cert through merge_environment_settings, which falls back to these when neither an
        # explicit path nor an env CA bundle is set, so the default is always verified, including on a caller's session.
        self._session.verify = verify_path if verify_path else True
        self._session.cert = cert_path
        # Set once, never per request: requests merges session headers under each request's own, so an endpoint's
        # accept/content-type still win over the session's default Accept.
        self._session.headers["User-Agent"] = user_agent()
        self._safe_mode = safe_mode

        self._logger = self._init_logging(logger, log_level)

        self._init_baseurl()
        self._init_headers()

        self._logger.debug("%s API for %s init complete", self._version, self._fqdn)


    # Private Methods - Init

    def _init_logging(self, logger: Logger | None, log_level: int) -> Logger:
        """The caller's logger as-is, or this API's ``jamfpy.{tenant}-{pro|clc}`` child logger set to ``log_level``."""
        if logger is not None:
            return logger
        return tenant_logger(extract_cloud_tenant_name_from_url(self._fqdn), self._short_name, log_level)


    def _init_baseurl(self) -> None:
        """
        Sets object vars for urls for readability.
        
        E.g
        self._base_url = https://your_server.jamfcloud.com/JSSResource
        or
        self._base_url = https://your_server.jamfcloud.com/api/v{version}
        """

        api_suffix: str = self._http_config.urls["api"][self._version]
        self.base_url = self._fqdn + api_suffix


    def _init_headers(self) -> None:
        """
        Loads headers into object
        """
        self._headers: dict[str, dict[str, Any]] = self._http_config.headers["crud"]



    # Public Methods


    def close(self) -> None:
        """Invalidates tokens and deletes self"""

        self._logger.info("Closing %s", str(self))

        if not self.auth.invalidate():
            self._logger.warning("Token invalidation failed for %s", self._fqdn)
        self._is_closed = True

        self._logger.info("%s closed", str(self))


    # @_check_closed
    def url(self, target: str | None = None) -> str:
        """
        Allows access to base url from endpoint
        Universal interface across API versions
        """
        if self._version == "classic":
            return self.base_url

        if self._version == "pro":
            return self.base_url.format(jamfapiversion=target)

        raise JamfpyConfigError("Invalid API version")


    # @_check_closed
    def header(self, key: str) -> dict[str, Any]:
        """Returns given set of headers from config"""
        try:
            return self._headers[key]

        except KeyError as e:
            raise KeyError("Invalid header key provided") from e


    # @_check_closed
    def do(self, request: Request, timeout: Timeout | None = None) -> Response:
        """
        Adds the Authorization header, preps and sends the request, retrying as the configured RetryConfig allows.

        ``timeout`` overrides the configured timeout for this call only; ``None`` uses the configured one.
        Returns the last response, whatever its status. Raises the send's exception when it isn't retryable
        or the retries run out.

        Logs one INFO line per attempt (method, URL, status, duration) and, at DEBUG, the request and response
        headers and bodies, redacted under ``safe_mode``. Every line carries the fields as ``extra``.
        """
        send_timeout = self._timeout if timeout is None else timeout
        retry = self._retry
        attempt = 1

        while True:
            # Prepared afresh each attempt, so a token that expired during the backoff is refreshed before the resend.
            prepped = self._prepare(request)
            ctx = RequestContext(tenant=self._fqdn, api=self._version, attempt=attempt, started=time.monotonic())
            # Firing is internal to the API; Hooks keeps it private so consumers can only register and remove.
            self._hooks._fire_before_request(self._logger, prepped, ctx)  # pylint: disable=protected-access

            fields: dict[str, object] = {"method": prepped.method, "url": prepped.url, "attempt": attempt}
            self._log_request(prepped, fields)
            sent = time.monotonic()
            outcome: Response | Exception
            try:
                outcome = self._send(prepped, send_timeout)
            # The only exceptions the retry rules cover (SSLError, a ConnectionError, is ruled out by RetryPolicy);
            # anything else, such as InvalidURL, propagates from here at once.
            except (RequestsConnectionError, ReadTimeout) as exc:
                outcome = exc
            fields["duration_ms"] = round((time.monotonic() - sent) * 1000)
            self._log_outcome(outcome, fields)
            if isinstance(outcome, Response):
                self._hooks._fire_after_response(self._logger, prepped, outcome, ctx)  # pylint: disable=protected-access

            delay = None if retry is None else retry.delay(self._logger, prepped, outcome, attempt, extra=fields)
            if retry is None or delay is None:
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome

            self._logger.warning(
                "Retrying %s %s: attempt %d failed with %s; next attempt in %.2f s",
                prepped.method, prepped.url, attempt, describe_outcome(outcome), delay, extra=fields
            )
            self._hooks._fire_on_retry(self._logger, prepped, ctx, outcome, delay)  # pylint: disable=protected-access
            retry.sleep(delay)
            attempt += 1

    def _prepare(self, request: Request) -> PreparedRequest:
        """Put the current token on the request and prepare it against the session."""
        # On the request, never the shared session, so concurrent callers can't see each other's header changes. A new
        # dict, not an in-place update: endpoints pass the configured header sets, which must never carry a token.
        request.headers = {**(request.headers or {}), "Authorization": f"Bearer {self.auth.token()}"}
        return self._session.prepare_request(request)

    def _send(self, prepped: PreparedRequest, timeout: Timeout) -> Response:
        """Send one attempt with the environment's TLS and proxy settings."""
        # Session.send bypasses the env merge that Session.request does (CA bundle and proxy env vars); auth calls go
        # through requests.request and already honour it, so resolve the same settings here.
        # prepare_request always sets the URL (it raises otherwise); requests only types it as optional.
        assert prepped.url is not None
        settings = self._session.merge_environment_settings(prepped.url, {}, None, self.verify_path, self.cert_path)
        return self._session.send(prepped, timeout=timeout, **settings)

    def _log_request(self, prepped: PreparedRequest, fields: dict[str, object]) -> None:
        """DEBUG: the request's headers and body, as sent."""
        # Checked first: rendering redacts and serialises the body, which is wasted work when DEBUG is off.
        if not self._logger.isEnabledFor(logging.DEBUG):
            return
        self._logger.debug(
            "Request %s %s (attempt %d): headers=%s body=%s",
            prepped.method, prepped.url, fields["attempt"],
            render_headers(prepped.headers, self._safe_mode), render_body(prepped.body, self._safe_mode), extra=fields
        )

    def _log_outcome(self, outcome: Response | Exception, fields: dict[str, object]) -> None:
        """INFO: one line for the attempt; DEBUG: the response's headers and body. Adds ``status`` to ``fields``."""
        # The attempt number only appears from the first retry on, so a clean request reads as a single plain line.
        retry_note = f", attempt {fields['attempt']}" if fields["attempt"] != 1 else ""
        if isinstance(outcome, Exception):
            # No status to report: the exception's class stands in for it. The WARNING or ERROR that follows, or the
            # exception itself, gives the detail.
            self._logger.info(
                "%s %s -> %s (%d ms%s)", fields["method"], fields["url"], type(outcome).__name__, fields["duration_ms"],
                retry_note, extra=fields
            )
            return

        fields["status"] = outcome.status_code
        self._logger.info(
            "%s %s -> %d (%d ms%s)", fields["method"], fields["url"], outcome.status_code, fields["duration_ms"],
            retry_note, extra=fields
        )
        if self._logger.isEnabledFor(logging.DEBUG):
            self._logger.debug(
                "Response %s %s -> %d (attempt %d): headers=%s body=%s",
                fields["method"], fields["url"], outcome.status_code, fields["attempt"],
                render_headers(outcome.headers, self._safe_mode), render_body(outcome.content, self._safe_mode),
                extra=fields
            )
