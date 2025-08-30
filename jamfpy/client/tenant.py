"""Tenant management module for handling Jamf Pro tenant configurations and operations."""

# pylint: disable=broad-exception-raised, unused-argument

# This Lib
from .client import ProAPI, ClassicAPI
from .auth import OAuth, BasicAuth
from .http_config import HTTPConfig
from .constants import DEFAULT_LOG_LEVEL, DEFAULT_TOKEN_BUFFER, VALID_AUTH_METHODS
from .exceptions import JamfpyConfigError



class Tenant:
    """Main entry point for Jamf Pro API interactions, managing authentication and API endpoints."""

    def __init__(
      self,
      *,
      fqdn: str,
      auth_method: str,
      client_id: str = None,
      client_secret: str = None,
      username: str = None,
      password: str = None,
      http_config: HTTPConfig = HTTPConfig(),
      token_exp_threshold_mins: int = DEFAULT_TOKEN_BUFFER,
      log_level: int = DEFAULT_LOG_LEVEL,
      safe_mode: bool = True
    ):
        self.fqdn = fqdn
        self.token_exp_threshold_mins = token_exp_threshold_mins

        auth = self._init_validate_auth(
            auth_method=auth_method,
            client_id=client_id,
            client_secret=client_secret,
            username=username,
            password=password,
            log_level=log_level,
            http_config=http_config
        )

        auth.set_new_token()

        self._init_apis(
            fqdn=fqdn,
            auth=auth,
            log_level=log_level,
            http_config=http_config,
            safe_mode=safe_mode
        )



    def _init_validate_auth(
            self,
            *,
            auth_method: str,
            client_id: str,
            client_secret: str,
            username: str,
            password: str,
            log_level: int,
            http_config: HTTPConfig,
    ):
        """
        Method to validate the supplied configuration of auth credentials
        and instantialise an Auth object with them if valid

        Returns Auth or errors
        """

        if auth_method not in VALID_AUTH_METHODS:
            raise JamfpyConfigError(f"invalid auth method supplied: {auth_method}")

        match auth_method:

            case "oauth2":
                if not client_id or not client_secret:
                    raise JamfpyConfigError("one or more auth strings are empty")

                return OAuth(
                    fqdn=self.fqdn,
                    client_id=client_id,
                    client_secret=client_secret,
                    token_exp_thold_mins=self.token_exp_threshold_mins,
                    log_level=log_level,
                    http_config=http_config
                )

            case "basic":

                if not username or not password:
                    raise JamfpyConfigError("one or more auth methods are empty")

                return BasicAuth(
                    fqdn=self.fqdn,
                    username=username,
                    password=password,
                    token_exp_thold_mins=self.token_exp_threshold_mins,
                    log_level=log_level,
                    http_config=http_config
                )

            case _:
                raise JamfpyConfigError(f"invalid auth method supplied: {auth_method}")


    def _init_apis(
            self,
            *,
            fqdn: str,
            auth: OAuth | BasicAuth,
            log_level: int,
            http_config: HTTPConfig,
            safe_mode: bool,
    ):
        self.pro = ProAPI(
            fqdn=fqdn,
            auth=auth,
            log_level=log_level,
            http_config=http_config,
            safe_mode=safe_mode,
        )

        self.classic = ClassicAPI(
            fqdn=fqdn,
            auth=auth,
            log_level=log_level,
            http_config=http_config,
            safe_mode=safe_mode,
        )
