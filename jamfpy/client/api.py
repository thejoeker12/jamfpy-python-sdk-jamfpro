"""api model"""

from logging import Logger
from requests import Session, Request, Response

from .auth import Auth
from .http_config import HTTPConfig
from .logger import new_logger
from .utility import extract_cloud_tenant_name_from_url
from .exceptions import JamfpyConfigError


class API:
    """Base class providing core functionality for interacting with Jamf Pro APIs."""

    _headers_dict = {}
    _is_closed = False
    _short_name = None
    _version: str
    _http_config: HTTPConfig
    _logger: Logger

    def __init__(
            self,
            *,
            fqdn: str,
            auth: Auth,
            log_level,
            http_config: HTTPConfig,
            safe_mode: bool,
            session: Session,
            logger: Logger,
            cert_path: str = None,
            verify_path: str = None,

    ) -> None:

        self._fqdn = fqdn
        self.auth = auth
        self._http_config: HTTPConfig = http_config
        self.cert_path = cert_path
        self.verify_path = verify_path

        self._session = session or Session()
        self._safe_mode = safe_mode

        self._logger = self._init_logging(logger, log_level)

        self._init_baseurl()
        self._init_headers()

        self._logger.debug("%s API for %s init complete", self._version, self._fqdn)


    # Private Methods - Init

    def _init_logging(self, logger, log_level) -> None:
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
        self._headers = self._http_config.headers["crud"]



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

        self.auth.invalidate()
        self._is_closed = True

        self._logger.info("%s closed", str(self))


    # @_check_closed
    def url(self, target=None) -> str:
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
    def header(self, key: str) -> str:
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

        request_header_log = "no headers supplied"
        if request.headers:
            request_header_log = request.headers if not self._safe_mode else "[redacted]"

        self._logger.debug(do_debug_string, "prepping", request.method, request.url, request_header_log)

        prepped = self._session.prepare_request(request)

        prepped_header_log = "no headers supplied"
        if prepped.headers:
            prepped_header_log = prepped.headers if not self._safe_mode else "[redacted]"

        self._logger.debug(do_debug_string, "sending", prepped.method, prepped.url, prepped_header_log)

        response = self._session.send(prepped, timeout=timeout, cert=self.cert_path, verify=self.verify_path)

        self._logger.debug("Success: Code: %s Req: %s %s", response.status_code, prepped.method, response.url)

        return response
