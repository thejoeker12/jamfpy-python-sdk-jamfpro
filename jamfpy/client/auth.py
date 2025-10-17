"""Authentication module for Jamf Pro API, providing OAuth and Basic Authentication functionality for secure API access."""

# Libs
from base64 import b64encode
import datetime
from logging import Logger
from typing import Optional
from requests import request

# This module
from .logger import new_logger
from .http_config import HTTPConfig
from .exceptions import JamfAuthError
from .utility import fix_jamf_time_to_iso, extract_cloud_tenant_name_from_url

from .constants import (
    DEFAULT_LOG_LEVEL,
    AUTH_REQUEST_TIMEOUT,
    TIME_ROUNDING_DECIMAL_COUNT,
    DEFAULT_TOKEN_BUFFER
)


class Auth:
    """Base authentication class providing token management and validation for Jamf Pro API."""

    _token_str: str
    _method: str
    _logger: Logger

    token_expiry: datetime.time

    def __init__(
            self,
            *,
            fqdn: str,
            http_config: HTTPConfig,
            logger: Logger,
            token_exp_thold_mins: int = DEFAULT_TOKEN_BUFFER,
            log_level: int = DEFAULT_LOG_LEVEL,
            cert_path: str = None,
            verify_path: str = None,
    ):
        self._fqdn = fqdn
        self._http_config = http_config
        self._logger = logger or self._init_logging(log_level)
        self._auth_url = self._init_urls()
        self.token_exp_thold_mins = token_exp_thold_mins
        self.cert_path = cert_path
        self.verify_path = verify_path


    def set_new_token(self):
        """todo"""

    def _keep_alive_token(self):
        """todo"""

    def _init_logging(self, log_level) -> Logger:
        """Inits loggers for API Object"""

        shortname = extract_cloud_tenant_name_from_url(self._fqdn)

        return new_logger(
            name=f"{shortname}-auth",
            level=log_level
        )


    def _init_urls(self) -> None:
        self._logger.debug("FUNCTION: _init_urls")

        auth_endpoint = self._http_config.urls["auth"][self._method]

        auth_url = self._fqdn + auth_endpoint
        self._logger.debug("Auth URL set: %s", auth_url)

        return auth_url


    def check_token_in_buffer(self) -> bool:
        """
        Checks if token is within the buffer period.

        example:
        self.token_exp_thold_mins = 2
        now = 10:30am
        self.token_expiry = 10:31
        Returns:
            bool: True if token is within the buffer period, False otherwise.
        """
        self._logger.debug("FUNCTION: check_token_in_buffer")

        self._logger.debug("Expiry time: %s", self.token_expiry)

        now = round(datetime.datetime.now(datetime.timezone.utc).timestamp(), TIME_ROUNDING_DECIMAL_COUNT)

        self._logger.debug("Now: %s", now)

        expiry_delta_secs = round(self.token_expiry - now, TIME_ROUNDING_DECIMAL_COUNT)
        expiry_delta_mins = round(expiry_delta_secs / 60, TIME_ROUNDING_DECIMAL_COUNT)

        self._logger.debug("Token buffer: %s min(s)", self.token_exp_thold_mins)
        self._logger.debug("Expiry Delta mins/secs: %s/%s", expiry_delta_mins, expiry_delta_secs)

        if expiry_delta_mins < self.token_exp_thold_mins:
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

        if self.check_token_is_expired():
            self.set_new_token()

            if self.check_token_in_buffer():
                raise JamfAuthError("Buffer longer than token lifetime")

        elif self.check_token_in_buffer():
            if self. _method == "bearer":
                self._keep_alive_token()

            elif self._method == "oauth":
                self.set_new_token()

            if self.check_token_in_buffer():
                raise JamfAuthError("Buffer longer than token lifetime")


    def token(self) -> str:
        """Checks token validity and returns token string if valid"""
        self._logger.debug("FUNCTION: token")
        self.check_token()
        return self._token_str


    def invalidate(self) -> bool:
        """
        invalidates token
        """
        url = self._http_config.urls["auth"]["invalidate-token"]
        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {self._token_str}"
        }
        call = request(
            method="POST",
            url=url,
            headers=headers,
            timeout=AUTH_REQUEST_TIMEOUT,
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
            log_level = DEFAULT_LOG_LEVEL,
            token_exp_thold_mins = DEFAULT_TOKEN_BUFFER,
            http_config = HTTPConfig(),
            logger = None,
            cert_path: str = None,
            verify_path: str = None,

    ) -> None:

        super().__init__(
            fqdn=fqdn,
            http_config=http_config,
            logger=logger,
            token_exp_thold_mins=token_exp_thold_mins,
            log_level=log_level,
            cert_path=cert_path,
            verify_path=verify_path
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

        headers = self._http_config.headers["auth"]["oauth"]
        data = {
            "client_id": self._oauth_cid,
            "client_secret": self._oauth_cs,
            "grant_type": "client_credentials"
        }

        call = request(
            method="POST",
            url=self._auth_url,
            headers=headers,
            data=data,
            timeout=AUTH_REQUEST_TIMEOUT,
            cert=self.cert_path,
            verify=self.verify_path
        )

        if not call.ok:
            raise JamfAuthError("Error getting token.", call, call.text)

        call_json = call.json()
        self._token_str = call_json["access_token"]
        now = datetime.datetime.now(datetime.timezone.utc)
        self.token_expiry = (now + datetime.timedelta(seconds=call_json["expires_in"])).timestamp()
        self.token_expiry = round(self.token_expiry, TIME_ROUNDING_DECIMAL_COUNT)

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
            fqdn,
            token_exp_thold_mins,
            http_config: HTTPConfig = HTTPConfig(),
            username: Optional[str] = None,
            password: Optional[str] = None,
            basic_auth_token: Optional[str] = None,
            log_level: int = DEFAULT_LOG_LEVEL,
            logger: Logger = None,
            cert_path: str = None,
            verify_path: str = None,
    ) -> None:

        super().__init__(
            fqdn=fqdn,
            http_config=http_config,
            token_exp_thold_mins=token_exp_thold_mins,
            logger=logger,
            log_level=log_level,
            cert_path=cert_path,
            verify_path=verify_path
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

        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {self._token_str}"
        }

        call = request(
            method="POST",
            url=url,
            headers=headers,
            timeout=AUTH_REQUEST_TIMEOUT,
            cert=self.cert_path,
            verify=self.verify_path
        )

        if not call.ok:
            raise JamfAuthError("Error keeping token alive")

        call_json = call.json()
        self._token_str = call_json["token"]
        expiry_str = call_json["expires"]
        self.token_expiry = datetime.datetime.fromisoformat(expiry_str.replace('Z', '+00:00')).timestamp()
        self._logger.debug("_keep_alive_token complete")


    # Public
    def set_new_token(self) -> None:
        """Requests and sets a new Bearer token using stored credentials."""

        self._logger.debug("FUNCTION: set_new_token")
        url = self._fqdn + self._http_config.urls["auth"]["bearer"]

        headers = {
            "accept": "application/json",
            "Authorization": f"Basic {self.basic_auth_token}"  
        }

        call = request(
            method="POST",
            url=url,
            headers=headers,
            timeout=AUTH_REQUEST_TIMEOUT,
            cert=self.cert_path,
            verify=self.verify_path
        )

        if not call.ok:
            raise JamfAuthError("Error getting new token", call.status_code, call)


        call_json = call.json()
        self._token_str = call_json["token"]
        expiry_str = call_json["expires"]
        fixed_expiry_str = fix_jamf_time_to_iso(expiry_str)
        self.token_expiry = datetime.datetime.fromisoformat(fixed_expiry_str).timestamp()
