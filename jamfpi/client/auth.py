"""Python Jamf OAuth Handler

This module provides a handler for managing OAuth authentication with the Jamf API. 
It supports both OAuth and Bearer token methods, handling token generation, renewal, 
and invalidation to ensure seamless interaction with Jamf API endpoints.

Classes:
    Auth: Base class for handling common authentication tasks.
    OAuth: Subclass for handling OAuth specific authentication.
    BearerAuth: Subclass for handling Bearer Token specific authentication.
"""

# // NOTE Above pylint flags disabled for this file only on purpose.

# Libs
import datetime
from typing import Callable, Optional
from base64 import b64encode
from requests import request

# This module
from .logger import get_logger
from .exceptions import JamfAuthError
from ..config.defaultconfig import ROUND_AMOUNT
from .utility import fix_jamf_time_to_iso

AUTH_REQUEST_TIMEOUT = 20

class Auth:
    """
    Base authentication class for Jamf API interactions.

    This class handles common authentication tasks such as token checking,
    expiration monitoring, and URL initialization. It serves as a parent class
    for specific authentication methods like OAuth and Bearer Token.

    Attributes:
        _token_str (str, optional): The current authentication token.
        token_expiry (datetime.time): Token expiration time.
        _method (str): The authentication method used ('oauth' or 'bearer').
        _keep_alive_token (Callable): Method reference to keep the token alive.
        _set_new_token (Callable): Method reference to set a new token.

    """

    # Type assertions
    _token_str: Optional[str]
    token_expiry: datetime.time
    _method: str
    _keep_alive_token: Callable
    _set_new_token: Callable

    def __init__(
            self,
            tenant: str,
            libconfig: dict,
            logger_cfg: dict,
            token_exp_thold_mins: int
    ):
        """
        Initializes the Auth object with the necessary configuration.

        Args:
        tenant (str): The name of the tenant.
        libconfig (dict): Library configuration parameters.
        logger_cfg (dict): Logger configuration.
        token_exp_thold_mins (int): Threshold in minutes for token expiration.
        """
        self._tenant = tenant
        self._libconfig = libconfig
        self._logger_cfg = logger_cfg
        self.token_exp_thold_mins = token_exp_thold_mins or 2

        self._init_logger()
        self._init_urls()


    def _init_logger(self) -> None:
        """Initializes the logger using provided or default configuration."""

        self.logger = self._logger_cfg["custom_logger"] or get_logger (
            name=f"{self._tenant}-auth-{self._method}",
            config=self._logger_cfg
        )
        self.logger.debug("Logger initialised")


    def _init_urls(self) -> None:
        """
        Sets object vars for urls for readability.
        
        E.g
        self._base_url = https://your_server.jamfcloud.com
        self._auth_url = https://your_server.jamfcloud.com/api/oauth/token
        """

        self.logger.debug("FUNCTION: _init_urls")

        self._base_url = self._libconfig.urls["base"].format(tenant=self._tenant)
        self.logger.debug("Base URL set %s", self._base_url)

        endpoint = self._libconfig.urls["auth"][self._method]
        self._auth_url = self._base_url + endpoint
        self.logger.debug("Auth URL set: %s", self._auth_url)


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
        self.logger.debug("FUNCTION: check_token_in_buffer")

        self.logger.debug("Expiry time: %s", self.token_expiry)

        now = round(datetime.datetime.utcnow().timestamp(), ROUND_AMOUNT)
        self.logger.debug("Now: %s", now)

        expiry_delta_secs = round(self.token_expiry - now, ROUND_AMOUNT)
        expiry_delta_mins = round(expiry_delta_secs / 60, ROUND_AMOUNT)

        self.logger.debug("Expiry Delta mins/secs: %s/%s", expiry_delta_mins, expiry_delta_secs)

        if expiry_delta_mins < self.token_exp_thold_mins:
            self.logger.warn("Token in buffer")
            return True

        self.logger.debug("Token not in buffer")
        return False


    def check_token_is_expired(self) -> bool:
        """
        Checks if the current token has expired.

        Returns:
            bool: True if the token has expired, False otherwise.
        """
        self.logger.debug("FUNCTION: check_token_is_expired")

        now = datetime.datetime.utcnow().timestamp()
        if now > self.token_expiry:
            self.logger.warn("Token expired")
            return True

        self.logger.debug("Token not expired")
        return False


    def check_token(self) -> None:
        """
        Proccess of checking and refreshing token
        Occurs before every request to ensure no usage of old tokens
        """
        self.logger.debug("FUNCTION: check_token")

        if self.check_token_is_expired():
            self._set_new_token()
            if self.check_token_in_buffer():
                raise JamfAuthError("Buffer longer than token lifetime")

        elif self.check_token_in_buffer():
            if self. _method == "bearer":
                self._keep_alive_token()
            elif self._method == "oauth":
                self._set_new_token()

            if self.check_token_in_buffer():
                raise JamfAuthError("Buffer longer than token lifetime")


    def token(self) -> str:
        """Checks token validity and returns token string if valid"""
        self.logger.debug("FUNCTION: token")
        self.check_token()
        return self._token_str


    def invalidate(self) -> bool:
        """
        invalidates token
        """
        url = self._libconfig.urls["invalidate-token"]
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
    """
    Subclass for handling OAuth authentication with Jamf API.

    This class extends the Auth class, providing specific implementations for OAuth authentication, including token generation and validation.

    Attributes:
        [Inherited attributes remain unchanged]
        _oauth_cid (str): OAuth client ID.
        _oauth_cs (str): OAuth client secret.

    Methods:
        [Method docstrings remain unchanged]
    """

    _method = "oauth"

    def __init__(
            self,
            tenant,
            libconfig,
            logger_cfg,
            token_exp_thold_mins,
            oauth_cid,
            oauth_cs
    ) -> None:
        """Initializes the OAuth object with necessary configuration and credentials.

        Args:
        tenant (str): The name of the tenant.
        libconfig (dict): Library configuration parameters.
        logger_cfg (dict): Logger configuration.
        token_exp_thold_mins (int): Threshold in minutes for token expiration.
        oauth_cid (str): OAuth client ID.
        oauth_cs (str): OAuth client secret.
        """

        super().__init__(
            tenant,
            libconfig,
            logger_cfg,
            token_exp_thold_mins
        )

        self._oauth_cid = oauth_cid
        self._oauth_cs = oauth_cs

    # Magic

    def __str__(self) -> str:
        """Returns a string representation of the OAuth object."""
        return f"OAuth Object for {self._tenant}"

    # Private

    def _set_new_token(self) -> None:
        """Requests and sets a new OAuth token."""
        self.logger.debug("FUNCTION: _set_new_token")

        endpoint = self._libconfig.urls["auth"]["oauth"]
        url = self._base_url + endpoint
        headers = self._libconfig.headers["auth"]["oauth"]
        data = {
            "client_id": self._oauth_cid,
            "client_secret": self._oauth_cs,
            "grant_type": "client_credentials"
        }

        call = request(
            method="POST",
            url=url,
            headers=headers,
            data=data,
            timeout=AUTH_REQUEST_TIMEOUT
        )

        if call.ok:
            call_json = call.json()
            self._token_str = call_json["access_token"]
            now = datetime.datetime.utcnow()
            self.token_expiry = (now + datetime.timedelta(seconds=call_json["expires_in"])).timestamp()
            self.token_expiry = round(self.token_expiry, ROUND_AMOUNT)
            self.logger.debug("Token set successfully")

        else:
            raise JamfAuthError("Error getting token.", call, call.text)


    def _keep_alive_token(self) -> None:
        """Placeholder method for OAuth, raises an error as it's not applicable."""
        raise JamfAuthError("Action not available with OAuth interface.")




class BearerAuth(Auth):
    """
    Subclass for handling Bearer Token authentication with Jamf API.

    This class extends the Auth class, providing specific implementations for Bearer Token authentication, including token generation, renewal, and keep-alive functionality.

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
        Initializes the BearerAuth object with necessary configuration and credentials.

        Args:
        tenant (str): The name of the tenant.
        libconfig (dict): Library configuration parameters.
        logger_cfg (dict): Logger configuration.
        token_exp_thold_mins (int): Threshold in minutes for token expiration.
        username (str, optional): Username for basic authentication.
        password (str, optional): Password for basic authentication.
        basic_auth_token (str, optional): Precomputed basic auth token.
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

        return f"Bearer Token Object for {self._tenant}"


    # Private
    def _init_auth(self) -> None:
        """Initializes the authentication by setting the basic auth token."""
        self.logger.debug("FUNCTION: _init_auth")
        if self.username and self.password:
            credstring = f"{self.username}:{self.password}"
            self.basic_auth_token = b64encode(bytes(credstring, encoding="UTF-8")).decode()
        elif self.basic_auth_token:
            pass


    def _set_new_token(self) -> None:
        """Requests and sets a new Bearer token using stored credentials."""
        self.logger.debug("FUNCTION: _set_new_token")
        url = self._base_url + self._libconfig.urls["auth"]["bearer"]

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


    def _keep_alive_token(self) -> None:
        """Keeps the current Bearer token alive and updates its expiration time."""
        self.logger.debug("_keep_alive_token starting")

        url = self._base_url + self._libconfig.urls["auth"]["keep-alive"]
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
            self.logger.debug("_keep_alive_token complete")

        else:
            raise JamfAuthError("Error keeping token alive")
