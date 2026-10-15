"""api model"""

from logging import Logger
from typing import Any

from requests import Session, Request, Response

from .auth import Auth
from .http_config import HTTPConfig
from .logger import new_logger
from .utility import extract_cloud_tenant_name_from_url
from .exceptions import JamfpyConfigError


class API:
    """Base class providing core functionality for interacting with Jamf Pro APIs."""

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

    ) -> None:

        self._fqdn = fqdn
        self.auth = auth
        self._http_config: HTTPConfig = http_config
        self.cert_path = cert_path
        self.verify_path = verify_path

        self._session = session or Session()
        # do() resolves verify/cert through merge_environment_settings, which falls back to these when neither an
        # explicit path nor an env CA bundle is set, so the default is always verified, including on a caller's session.
        self._session.verify = verify_path if verify_path else True
        self._session.cert = cert_path
        self._safe_mode = safe_mode

        self._logger = self._init_logging(logger, log_level)

        self._init_baseurl()
        self._init_headers()

        self._logger.debug("%s API for %s init complete", self._version, self._fqdn)


    # Private Methods - Init

    def _init_logging(self, logger: Logger | None, log_level: int) -> Logger:
        """Inits loggers for API Object"""

        # Everything after the slashes, before the first dot of an fqdn
        # This is where the unique identifier of a Jamf Pro Cloud instance is found.
        tenant_name = extract_cloud_tenant_name_from_url(self._fqdn)

        return logger or new_logger(
            name=f"{tenant_name}-{self._short_name}",
            level=log_level
        )


    def _init_baseurl(self) -> None:
        """
        Sets object vars for urls for readability.
        
        E.g
        self._base_url = https://your_server.jamfcloud.com/JSSResource
        or
        self._base_url = https://your_server.jamfcloud.com/api/v{version}
        """

        self._logger.debug("FUNCTION: _init_baseurl")

        api_suffix: str = self._http_config.urls["api"][self._version]
        self.base_url = self._fqdn + api_suffix


    def _init_headers(self) -> None:
        """
        Loads headers into object
        """
        self._logger.debug("FUNCTION: _init_headers")
        self._headers: dict[str, dict[str, Any]] = self._http_config.headers["crud"]



    # @_check_closed
    def _refresh_session_headers(self) -> None:
        """Clears all session headers and replaces with new Auth header"""

        self._logger.debug("Refreshing session headers (Clear + Re-set)")

        self._session.headers.clear()

        token = self.auth.token()
        self._session.headers.update({"Authorization": f"Bearer {token}"})

        self._logger.debug("Session headers refreshed successfully")


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
    def do(self, request: Request, timeout: int = 10) -> Response:
        """Takes request, preps and sends"""
        self._refresh_session_headers()

        do_debug_string = "%s: Method: %s at: %s with headers: %s"

        # Logging accepts any object, and the value is either a header mapping or a marker string.
        request_header_log: object = "no headers supplied"
        if request.headers:
            request_header_log = request.headers if not self._safe_mode else "[redacted]"

        self._logger.debug(do_debug_string, "prepping", request.method, request.url, request_header_log)

        prepped = self._session.prepare_request(request)

        prepped_header_log: object = "no headers supplied"
        if prepped.headers:
            prepped_header_log = prepped.headers if not self._safe_mode else "[redacted]"

        self._logger.debug(do_debug_string, "sending", prepped.method, prepped.url, prepped_header_log)

        # Session.send bypasses the env merge that Session.request does (CA bundle and proxy env vars); auth calls go
        # through requests.request and already honour it, so resolve the same settings here.
        # prepare_request always sets the URL (it raises otherwise); requests only types it as optional.
        assert prepped.url is not None
        settings = self._session.merge_environment_settings(prepped.url, {}, None, self.verify_path, self.cert_path)
        response = self._session.send(prepped, timeout=timeout, **settings)

        self._logger.debug("Success: Code: %s Req: %s %s", response.status_code, prepped.method, response.url)

        return response
