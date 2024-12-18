"""Python Jamf OAuth Handler

This module provides a handler for managing OAuth authentication with the Jamf API. 
It supports both OAuth and Bearer token methods, handling token generation, renewal, 
and invalidation to ensure seamless interaction with Jamf API endpoints.

Classes:
    Auth: Base class for handling common authentication tasks.
    OAuth: Subclass for handling OAuth specific authentication.
    BearerAuth: Subclass for handling Bearer Token specific authentication.
"""

# Libs
import datetime
from typing import Callable, Optional
from base64 import b64encode
from requests import request
from logging import Logger

# This module
from .logger import get_logger
from .http_config import HTTPConfig
from .exceptions import JamfAuthError
from .utility import fix_jamf_time_to_iso, extract_cloud_tenant_name_from_url

from .constants import (
    DEFAULT_LOG_LEVEL,
    AUTH_REQUEST_TIMEOUT,
    TIME_ROUNDING_AMOUNT,
    DEFAULT_TOKEN_BUFFER
)

# Seconds

class Auth:
    _token_str: str
    _method: str
    _keep_alive_token: Callable
    _logger: Logger

    token_expiry: datetime.time
    set_new_token: Callable

    def __init__(
            self,
            fqdn: str,
            http_config,
            logger,
            token_exp_thold_mins,
            log_level
    ):
        self._fqdn = fqdn
        self._http_config = http_config
        self._logger = self._init_logging(logger, log_level)
        self._auth_url = self._init_urls()

        self.token_exp_thold_mins = token_exp_thold_mins


    def _init_logging(self, logger, log_level) -> Logger:
        """Inits loggers for API Object"""

        if logger:
            return logger

        # Everything after the slashes, before the first dot of an fqdn
        # This is where the unique identifier of a Jamf Pro Cloud instance is found.
        shortname = extract_cloud_tenant_name_from_url(self._fqdn)
        
        return get_logger(
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

        now = round(datetime.datetime.now(datetime.timezone.utc).timestamp(), TIME_ROUNDING_AMOUNT)

        self._logger.debug("Now: %s", now)

        expiry_delta_secs = round(self.token_expiry - now, TIME_ROUNDING_AMOUNT)
        expiry_delta_mins = round(expiry_delta_secs / 60, TIME_ROUNDING_AMOUNT)

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

        match now > self.token_expiry:

            case True:
                self._logger.warning("Token expired")
                return True

            case False:
                self._logger.debug("Token not expired")
                return False

            case _:
                raise RuntimeError("an error occured")


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
            timeout=AUTH_REQUEST_TIMEOUT
        )

        if call.ok:
            return True

        return False


class OAuth(Auth):
    _method = "oauth"

    def __init__(
            self,
            fqdn,
            client_id,
            client_secret,
            http_config = HTTPConfig(),
            logger = None,
            log_level = DEFAULT_LOG_LEVEL,
            token_exp_thold_mins = DEFAULT_TOKEN_BUFFER,

    ) -> None:

        super().__init__(
            fqdn,
            http_config,
            logger,
            log_level,
            token_exp_thold_mins
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
            timeout=AUTH_REQUEST_TIMEOUT
        )

        if not call.ok:
            raise JamfAuthError("Error getting token.", call, call.text)

        call_json = call.json()
        self._token_str = call_json["access_token"]
        now = datetime.datetime.now(datetime.timezone.utc)
        self.token_expiry = (now + datetime.timedelta(seconds=call_json["expires_in"])).timestamp()
        self.token_expiry = round(self.token_expiry, TIME_ROUNDING_AMOUNT)

        self._logger.debug("Token set successfully")



    def _keep_alive_token(self) -> None:
        """Placeholder method for OAuth, raises an error as it's not applicable."""
        raise JamfAuthError("Action not available with OAuth interface.")


class BearerAuth(Auth):
    """
    Subclass for handling Bearer Token authentication with Jamf API.

    This class extends the Auth class, providing specific implementations for Bearer Token authentication, 
    including token generation, renewal, and keep-alive functionality.

    Attributes:
        [Inherited attributes remain unchanged]
        username (str, optional): The username for basic authentication.
        password (str, optional): The password for basic authentication.
        basic_auth_token (str, optional): The basic auth token if provided.

    Methods:
    """
    _method = "bearer"

    def __init__(
            self,
            tenant,
            libconfig,
            logger_cfg,
            token_exp_thold_mins,
            username: Optional[str] = None,
            password: Optional[str] = None,
            basic_auth_token: Optional[str] = None,
    ) -> None:

        """
        """

        super().__init__(
            tenant=tenant,
            libconfig=libconfig,
            logger_cfg=logger_cfg,
            token_exp_thold_mins=token_exp_thold_mins
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
        elif self.basic_auth_token:
            pass


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
            timeout=AUTH_REQUEST_TIMEOUT
        )
        if call.ok:
            call_json = call.json()
            self._token_str = call_json["token"]
            expiry_str = call_json["expires"]
            self.token_expiry = datetime.datetime.fromisoformat(expiry_str.replace('Z', '+00:00')).timestamp()
            self._logger.debug("_keep_alive_token complete")

        else:
            raise JamfAuthError("Error keeping token alive")


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
            timeout=AUTH_REQUEST_TIMEOUT
        )

        if call.ok:
            call_json = call.json()
            self._token_str = call_json["token"]
            expiry_str = call_json["expires"]
            fixed_expiry_str = fix_jamf_time_to_iso(expiry_str)
            self.token_expiry = datetime.datetime.fromisoformat(fixed_expiry_str).timestamp()
        else:

            raise JamfAuthError("Error getting new token")
