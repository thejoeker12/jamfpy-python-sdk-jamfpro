"""Authentication module for Jamf Pro API, providing OAuth and Basic Authentication functionality for secure API access."""

# Libs
from base64 import b64encode
import datetime
from logging import Logger
import threading
from typing import Optional
from requests import request

# This module
from .logger import new_logger
from .http_config import HTTPConfig
from .exceptions import JamfAuthError
from .utility import extract_cloud_tenant_name_from_url, user_agent

from .constants import (
    DEFAULT_LOG_LEVEL,
    DEFAULT_TIMEOUT,
    TIME_ROUNDING_DECIMAL_COUNT,
    DEFAULT_TOKEN_BUFFER,
    Timeout,
)


def _parse_jamf_expiry(expires: str) -> float:
    """Convert a Jamf token ``expires`` timestamp (e.g. ``2026-10-15T14:34:41.571Z``) to a UTC epoch timestamp."""
    # Jamf varies the number of fractional digits; fromisoformat takes any count plus a trailing Z on Python 3.11+.
    return datetime.datetime.fromisoformat(expires).timestamp()


class Auth:
    """Base authentication class providing token management and validation for Jamf Pro API.

    Lazy: no token is fetched until the first ``token()`` call (or an explicit ``set_new_token()``).
    Thread-safe: a re-entrant lock serialises every fetch, keep-alive and invalidation, so one Auth can
    serve concurrent requests and only one of them refreshes an expiring token.
    """

    _token_str: str | None
    _method: str
    _logger: Logger
    _token_lifetime_secs: float | None

    token_expiry: float

    def __init__(
            self,
            *,
            fqdn: str,
            http_config: HTTPConfig,
            logger: Logger | None,
            token_exp_thold_mins: int = DEFAULT_TOKEN_BUFFER,
            log_level: int = DEFAULT_LOG_LEVEL,
            cert_path: str | None = None,
            verify_path: str | None = None,
            timeout: Timeout = DEFAULT_TIMEOUT,
    ) -> None:
        self._fqdn = fqdn
        self._http_config = http_config
        self._logger = logger or self._init_logging(log_level)
        self._auth_url = self._init_urls()
        self.token_exp_thold_mins = token_exp_thold_mins
        self.cert_path = cert_path
        self.verify_path = verify_path
        self._timeout = timeout
        self._user_agent = user_agent()
        self._token_lifetime_secs = None
        self._buffer_clamp_warned = False
        self._token_str = None
        # Epoch 0 reads as expired, so the expiry checks agree there is no usable token yet.
        self.token_expiry = 0.0
        # Re-entrant because token() holds it while check_token() calls set_new_token()/_keep_alive_token(), which
        # take it themselves so that direct callers such as Tenant.authenticate() are serialised too.
        self._lock = threading.RLock()


    def set_new_token(self) -> None:
        """Request and store a new token; subclasses implement this."""

    def _keep_alive_token(self) -> None:
        """Extend the current token's lifetime; subclasses implement this."""

    def _init_logging(self, log_level: int) -> Logger:
        """Inits loggers for API Object"""

        shortname = extract_cloud_tenant_name_from_url(self._fqdn)

        return new_logger(
            name=f"{shortname}-auth",
            level=log_level
        )


    def _init_urls(self) -> str:
        self._logger.debug("FUNCTION: _init_urls")

        auth_endpoint: str = self._http_config.urls["auth"][self._method]

        auth_url = self._fqdn + auth_endpoint
        self._logger.debug("Auth URL set: %s", auth_url)

        return auth_url


    def _record_token_lifetime(self, lifetime_secs: float) -> None:
        """Store the lifetime of the token just issued and warn, once per instance, if the buffer covers all of it."""
        self._token_lifetime_secs = lifetime_secs

        # Only a buffer covering the whole lifetime is a misconfiguration (it used to raise); halving a buffer that
        # merely exceeds half the lifetime is routine for short-lived API client tokens, so that stays silent.
        if self.token_exp_thold_mins * 60 >= lifetime_secs and not self._buffer_clamp_warned:
            self._buffer_clamp_warned = True
            self._logger.warning(
                "Configured token buffer of %s min is not shorter than the token lifetime of %.0f s; using a %.0f s buffer instead",
                self.token_exp_thold_mins, lifetime_secs, self._buffer_secs()
            )


    def _buffer_secs(self) -> float:
        """Effective refresh buffer: the configured minutes, capped at half the current token's lifetime (floor 0)."""
        configured_secs = float(self.token_exp_thold_mins * 60)
        if self._token_lifetime_secs is None:
            return configured_secs

        # API clients can issue tokens shorter than the configured buffer; uncapped, every fresh token would
        # already sit inside it. At half the lifetime a new token always starts outside the buffer.
        return max(0.0, min(configured_secs, self._token_lifetime_secs / 2))


    def check_token_in_buffer(self) -> bool:
        """
        Checks if token is within the buffer period.

        The buffer is token_exp_thold_mins, capped at half the token's lifetime when the token is shorter-lived.

        Returns:
            bool: True if token is within the buffer period, False otherwise.
        """
        self._logger.debug("FUNCTION: check_token_in_buffer")

        self._logger.debug("Expiry time: %s", self.token_expiry)

        now = round(datetime.datetime.now(datetime.timezone.utc).timestamp(), TIME_ROUNDING_DECIMAL_COUNT)

        self._logger.debug("Now: %s", now)

        expiry_delta_secs = round(self.token_expiry - now, TIME_ROUNDING_DECIMAL_COUNT)
        buffer_secs = self._buffer_secs()

        self._logger.debug("Token buffer: %s sec(s)", buffer_secs)
        self._logger.debug("Expiry delta: %s sec(s)", expiry_delta_secs)

        if expiry_delta_secs < buffer_secs:
            self._logger.warning("Token in buffer")
            return True

        self._logger.debug("Token not in buffer")
        return False


    def check_token_is_expired(self) -> bool:
        """
        Checks if the current token has expired.

        Returns:
            bool: True if the token has expired, False otherwise.
        """
        self._logger.debug("FUNCTION: check_token_is_expired")

        now = datetime.datetime.now(datetime.timezone.utc).timestamp()

        if now >= self.token_expiry:
            self._logger.warning("Token expired")
            return True

        self._logger.debug("Token not expired")
        return False


    def check_token(self) -> None:
        """
        Proccess of checking and refreshing token
        Occurs before every request to ensure no usage of old tokens
        """
        self._logger.debug("FUNCTION: check_token")

        if self._token_str is None:
            # The first fetch is routine under lazy auth, so it is not reported as an expired token.
            self._logger.debug("No token yet; fetching one")
            self.set_new_token()

        elif self.check_token_is_expired():
            self.set_new_token()

        elif self.check_token_in_buffer():
            if self._method == "bearer":
                self._keep_alive_token()

            elif self._method == "oauth":
                self.set_new_token()


    def _refresh_needed(self) -> bool:
        """Lock-free, log-free pre-check for token(): no token yet, or one that is expired or inside the buffer."""
        if self._token_str is None:
            return True

        remaining_secs = self.token_expiry - datetime.datetime.now(datetime.timezone.utc).timestamp()
        return remaining_secs <= 0 or remaining_secs < self._buffer_secs()


    def token(self) -> str:
        """Return a valid token, fetching one first if there is none yet or it is expired or inside the buffer."""
        self._logger.debug("FUNCTION: token")

        # Double-checked so the common case (a valid token) never waits on the lock. A thread that sees a refresh
        # is due re-checks under the lock, because another thread may have refreshed while it waited.
        if self._refresh_needed():
            with self._lock:
                self.check_token()

        token = self._token_str
        # check_token() always leaves a token behind or raises; the attribute is only optional before the first fetch.
        assert token is not None
        return token


    def invalidate(self) -> bool:
        """
        Invalidates the current token on the server.

        Returns True when the server accepted it, or when no token has been fetched yet (nothing to invalidate).
        """
        with self._lock:
            if self._token_str is None:
                self._logger.debug("No token to invalidate")
                return True

            url = self._fqdn + self._http_config.urls["auth"]["invalidate-token"]
            headers = {
                "accept": "application/json",
                "Authorization": f"Bearer {self._token_str}",
                "User-Agent": self._user_agent,
            }
            call = request(
                method="POST",
                url=url,
                headers=headers,
                timeout=self._timeout,
                cert=self.cert_path,
                verify=self.verify_path
            )

            if call.ok:
                return True

            return False


class OAuth(Auth):
    """OAuth2 authentication implementation for Jamf Pro API using client credentials."""

    _method = "oauth"

    def __init__(
            self,
            *,
            fqdn: str,
            client_id: str,
            client_secret: str,
            log_level: int = DEFAULT_LOG_LEVEL,
            token_exp_thold_mins: int = DEFAULT_TOKEN_BUFFER,
            http_config: HTTPConfig = HTTPConfig(),
            logger: Logger | None = None,
            cert_path: str | None = None,
            verify_path: str | None = None,
            timeout: Timeout = DEFAULT_TIMEOUT,

    ) -> None:

        super().__init__(
            fqdn=fqdn,
            http_config=http_config,
            logger=logger,
            token_exp_thold_mins=token_exp_thold_mins,
            log_level=log_level,
            cert_path=cert_path,
            verify_path=verify_path,
            timeout=timeout,
        )

        self._oauth_cid = client_id
        self._oauth_cs = client_secret

    # Magic

    def __str__(self) -> str:
        """Returns a string representation of the OAuth object."""
        return f"OAuth Object for {self._fqdn}"

    # methods

    def set_new_token(self) -> None:
        """Requests and sets a new OAuth token."""
        self._logger.debug("FUNCTION: set_new_token")

        # A new dict: the configured header set is shared and must not carry per-call values.
        headers = {**self._http_config.headers["auth"]["oauth"], "User-Agent": self._user_agent}
        data = {
            "client_id": self._oauth_cid,
            "client_secret": self._oauth_cs,
            "grant_type": "client_credentials"
        }

        with self._lock:
            call = request(
                method="POST",
                url=self._auth_url,
                headers=headers,
                data=data,
                timeout=self._timeout,
                cert=self.cert_path,
                verify=self.verify_path
            )

            if not call.ok:
                raise JamfAuthError("Error getting token.", call, call.text)

            call_json = call.json()
            self._token_str = call_json["access_token"]
            now = datetime.datetime.now(datetime.timezone.utc)
            expiry = (now + datetime.timedelta(seconds=call_json["expires_in"])).timestamp()
            self.token_expiry = round(expiry, TIME_ROUNDING_DECIMAL_COUNT)
            self._record_token_lifetime(call_json["expires_in"])

        self._logger.debug("Token set successfully")



    def _keep_alive_token(self) -> None:
        """Placeholder method for OAuth, raises an error as it's not applicable."""
        raise JamfAuthError("Action not available with OAuth interface.")


class BasicAuth(Auth):
    """Basic authentication implementation for Jamf Pro API using username and password credentials."""

    _method = "bearer"

    def __init__(
            self,
            *,
            fqdn: str,
            token_exp_thold_mins: int,
            http_config: HTTPConfig = HTTPConfig(),
            username: Optional[str] = None,
            password: Optional[str] = None,
            basic_auth_token: Optional[str] = None,
            log_level: int = DEFAULT_LOG_LEVEL,
            logger: Logger | None = None,
            cert_path: str | None = None,
            verify_path: str | None = None,
            timeout: Timeout = DEFAULT_TIMEOUT,
    ) -> None:

        super().__init__(
            fqdn=fqdn,
            http_config=http_config,
            token_exp_thold_mins=token_exp_thold_mins,
            logger=logger,
            log_level=log_level,
            cert_path=cert_path,
            verify_path=verify_path,
            timeout=timeout,
        )

        self.username = username
        self.password = password
        self.basic_auth_token = basic_auth_token
        self._init_auth()


    # Magic
    def __str__(self) -> str:
        """Returns a string representation of the BearerAuth object."""

        return f"Bearer Token Object for {self._fqdn}"


    # Methods

    # Private
    def _init_auth(self) -> None:
        """Initializes the authentication by setting the basic auth token."""
        self._logger.debug("FUNCTION: _init_auth")
        if self.username and self.password:
            credstring = f"{self.username}:{self.password}"
            self.basic_auth_token = b64encode(bytes(credstring, encoding="UTF-8")).decode()


    def _keep_alive_token(self) -> None:
        """Keeps the current Bearer token alive and updates its expiration time."""
        self._logger.debug("_keep_alive_token starting")

        url = self._fqdn + self._http_config.urls["auth"]["keep-alive"]

        with self._lock:
            # Read under the lock: the token being extended must be the one this call then replaces.
            headers = {
                "accept": "application/json",
                "Authorization": f"Bearer {self._token_str}",
                "User-Agent": self._user_agent,
            }

            call = request(
                method="POST",
                url=url,
                headers=headers,
                timeout=self._timeout,
                cert=self.cert_path,
                verify=self.verify_path
            )

            if not call.ok:
                raise JamfAuthError("Error keeping token alive")

            call_json = call.json()
            self._token_str = call_json["token"]
            self.token_expiry = _parse_jamf_expiry(call_json["expires"])
            self._record_token_lifetime(self.token_expiry - datetime.datetime.now(datetime.timezone.utc).timestamp())

        self._logger.debug("_keep_alive_token complete")


    # Public
    def set_new_token(self) -> None:
        """Requests and sets a new Bearer token using stored credentials."""

        self._logger.debug("FUNCTION: set_new_token")
        url = self._fqdn + self._http_config.urls["auth"]["bearer"]

        headers = {
            "accept": "application/json",
            "Authorization": f"Basic {self.basic_auth_token}",
            "User-Agent": self._user_agent,
        }

        with self._lock:
            call = request(
                method="POST",
                url=url,
                headers=headers,
                timeout=self._timeout,
                cert=self.cert_path,
                verify=self.verify_path
            )

            if not call.ok:
                raise JamfAuthError("Error getting new token", call.status_code, call)

            call_json = call.json()
            self._token_str = call_json["token"]
            self.token_expiry = _parse_jamf_expiry(call_json["expires"])
            self._record_token_lifetime(self.token_expiry - datetime.datetime.now(datetime.timezone.utc).timestamp())
