"""Tenant management module for handling Jamf Pro tenant configurations and operations."""

# pylint: disable=broad-exception-raised, unused-argument

# External
from pathlib import Path

# This Lib
from .client import ProAPI, ClassicAPI
from .auth import OAuth, BasicAuth
from .hooks import Hooks
from .http_config import HTTPConfig
from .retry import RetryConfig
from .constants import DEFAULT_LOG_LEVEL, DEFAULT_PARALLELISM, DEFAULT_TIMEOUT, DEFAULT_TOKEN_BUFFER, VALID_AUTH_METHODS, Timeout
from .exceptions import JamfpyConfigError
from .utility import normalise_fqdn



class Tenant:
    """Main entry point for Jamf Pro API interactions, managing authentication and API endpoints.

    Construction makes no network call: the first request fetches a token. Call ``authenticate()`` to fetch one
    up front, so bad credentials or an unreachable FQDN fail there instead.

    ``timeout`` (seconds, or a ``(connect, read)`` pair) applies to every API and auth request.

    ``retries`` sets how API requests are retried (``None`` turns retries off); auth calls are never retried.
    ``hooks`` holds the request hooks both APIs fire on every API request attempt.

    ``parallelism`` (default 5, Jamf's recommended ceiling on concurrent connections from one client) caps the
    requests the SDK runs at once for one operation it fans out, today the page fetches of a Pro ``get_all``; ``1``
    makes them sequential. It is not a rate limiter: requests the caller makes concurrently are never throttled,
    queued or serialised. Less than 1 raises ``ValueError``.

    ``log_level`` sets the tenant's three loggers (``jamfpy.{tenant}-auth``, ``-pro`` and ``-clc``); call
    ``jamfpy.configure_logging()`` to see their output. ``safe_mode`` (the default) redacts every logged header set
    and body: the values of the ``Authorization`` (its Bearer or Basic scheme is kept), ``Proxy-Authorization``,
    ``X-Auth-Token``, ``Cookie`` and ``Set-Cookie`` headers, and of the ``password``, ``client_secret``,
    ``client_id``, ``access_token`` and ``token`` keys in JSON, form, XML and raw text. It does not touch URLs
    (query strings included) or other key names such as ``pin``. ``safe_mode=False`` logs everything in full and
    is for a dev tenant only.
    """

    def __init__(
      self,
      *,
      fqdn: str,
      auth_method: str,
      client_id: str | None = None,
      client_secret: str | None = None,
      username: str | None = None,
      password: str | None = None,
      http_config: HTTPConfig = HTTPConfig(),
      token_exp_threshold_mins: int = DEFAULT_TOKEN_BUFFER,
      log_level: int = DEFAULT_LOG_LEVEL,
      safe_mode: bool = True,
      cert_path: str | None = None,
      verify_path: str | None = None,
      timeout: Timeout = DEFAULT_TIMEOUT,
      retries: RetryConfig | None = RetryConfig(),
      parallelism: int = DEFAULT_PARALLELISM,
    ) -> None:
        # Every URL is built by appending a path to it, so it needs a scheme.
        fqdn = normalise_fqdn(fqdn)
        self.fqdn = fqdn
        self.token_exp_threshold_mins = token_exp_threshold_mins
        self.cert_path = cert_path
        self.verify_path = verify_path

        self._validate_path(
            cert_path=cert_path,
            verify_path=verify_path
        )

        self._auth = self._init_validate_auth(
            auth_method=auth_method,
            client_id=client_id,
            client_secret=client_secret,
            username=username,
            password=password,
            log_level=log_level,
            http_config=http_config,
            timeout=timeout,
            safe_mode=safe_mode,
        )

        # One registry for both APIs, so a hook sees every request whichever API sends it.
        self.hooks = Hooks()

        self._init_apis(
            fqdn=fqdn,
            auth=self._auth,
            log_level=log_level,
            http_config=http_config,
            safe_mode=safe_mode,
            timeout=timeout,
            retries=retries,
            parallelism=parallelism,
        )

    def authenticate(self) -> None:
        """
        Fetch a token now instead of on the first request.

        Raises JamfAuthError on bad credentials, or the requests exception when the FQDN is unreachable.
        """
        # set_new_token() holds the auth lock, so this never swaps the token mid-refresh in another thread.
        self._auth.set_new_token()

    def _validate_path(
            self,
            *,
            cert_path: str | None = None,
            verify_path: str | None = None
            ) -> None:
        """
        Method to validate the supplied configuration of certificate paths
        and set the attributes of the class

        Returns errors or sets certificate attributes
        """
        if cert_path is not None:
            cert_path_obj = Path(cert_path)
            if not cert_path_obj.exists():
                raise JamfpyConfigError(f"Cert Path: {cert_path_obj} does not exist")
            if cert_path_obj.is_dir():
                raise JamfpyConfigError(f"{cert_path_obj} is a directory")
            # Stored as str: requests and every downstream signature take str paths.
            self.cert_path = str(cert_path_obj)

        if verify_path is not None:
            verify_path_obj = Path(verify_path)
            if not verify_path_obj.exists():
                raise JamfpyConfigError(f"Verify Path: {verify_path_obj} does not exist")
            if verify_path_obj.is_dir():
                raise JamfpyConfigError(f"{verify_path_obj} is a directory")
            self.verify_path = str(verify_path_obj)

    def _init_validate_auth(
            self,
            *,
            auth_method: str,
            client_id: str | None,
            client_secret: str | None,
            username: str | None,
            password: str | None,
            log_level: int,
            http_config: HTTPConfig,
            timeout: Timeout,
            safe_mode: bool,
    ) -> OAuth | BasicAuth:
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
                    http_config=http_config,
                    cert_path=self.cert_path,
                    verify_path=self.verify_path,
                    timeout=timeout,
                    safe_mode=safe_mode,
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
                    http_config=http_config,
                    cert_path=self.cert_path,
                    verify_path=self.verify_path,
                    timeout=timeout,
                    safe_mode=safe_mode,
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
            timeout: Timeout,
            retries: RetryConfig | None,
            parallelism: int,
    ) -> None:
        self.pro = ProAPI(
            fqdn=fqdn,
            auth=auth,
            log_level=log_level,
            http_config=http_config,
            safe_mode=safe_mode,
            cert_path=self.cert_path,
            verify_path=self.verify_path,
            timeout=timeout,
            retries=retries,
            hooks=self.hooks,
            parallelism=parallelism,
        )

        self.classic = ClassicAPI(
            fqdn=fqdn,
            auth=auth,
            log_level=log_level,
            http_config=http_config,
            safe_mode=safe_mode,
            cert_path=self.cert_path,
            verify_path=self.verify_path,
            timeout=timeout,
            retries=retries,
            hooks=self.hooks,
            parallelism=parallelism,
        )
