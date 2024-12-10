"""
Jamf API Client Main
"""

from typing import Any
from requests import Session, Request, Response, HTTPError
from logging import Logger

from .auth import OAuth, BearerAuth
from .exceptions import jamfpyConfigError
from .logger import get_logger

from ..endpoints.classic.clc_computers import ClassicComputers
from ..endpoints.classic.clc_computer_groups import ComputerGroups
from ..endpoints.classic.clc_policies import Policies
from ..endpoints.classic.clc_osxconfiguration_profiles import ConfigurationProfiles
from ..endpoints.classic.clc_computer_extension_attributes import ExtensionAttributes
from ..endpoints.classic.clc_categories import Categories
from ..endpoints.classic.clc_dock_items import DockItems

from ..endpoints.pro.pro_api_management import (
    APIRolePrivileges,
    APIIntegrations,
    APIRoles
)
from ..endpoints.pro.pro_scripts import Scripts
from ..endpoints.pro.pro_sso_certificate import SsoCertificates
from ..endpoints.pro.pro_icon import Icons
from ..endpoints.pro.pro_computers_inventory import ComputersInventory


VALID_AUTH_METHODS = ["oauth2", "basic"]


class API:
    """Parent class for Jamf API"""

    _headers_dict = {}
    _is_closed = False
    _short_name = None

    def __init__(
            self,
            config: dict[str: Any],
            version: str
    ) -> None:
        
        self._version: str = version
        self._libconfig: dict = config["libconfig"]
        self._logger_config: dict = config["logging"]
        self._auth_method: str = config["auth_method"]
        self._session: Session = config["session"]
        self._safe_mode: bool = config["safe_mode"]

        self.tenant: str = config["tenant"]
        self.auth: OAuth | BearerAuth = config["auth"]

        self._init_logging()
        self.logger.debug("API initialising...")

        self._init_baseurl()
        self._init_headers()

        self.logger.debug("%s API for %s init complete", self._version, self.tenant)


    # Private Methods - Init

    def _init_logging(self) -> None:
        """Inits loggers for API Object"""

        self.logger = self._logger_config["custom_logger"] or get_logger(
            name=f"{self.tenant}-{self._short_name}",
            config=self._logger_config
        )

        self.logger.debug("Logger successfully initiated")


    def _init_baseurl(self) -> None:
        """
        Sets object vars for urls for readability.
        
        E.g
        self._base_url = https://your_server.jamfcloud.com/JSSResource
        or
        self._base_url = https://your_server.jamfcloud.com/api/v{version}
        """

        self.logger.debug("FUNCTION: _init_baseurl")

        template: str = self._libconfig.urls["base"].format(tenant=self.tenant)
        endpoint: str = self._libconfig.urls["api"][self._version]
        self.base_url = template + endpoint



    def _init_headers(self) -> None:
        """
        Loads headers into object
        """
        self.logger.debug("FUNCTION: _init_headers")
        self._headers = self._libconfig.headers[self._version]


    # Private Methods - Normal

    def _refresh_session_headers(self) -> None:
        """Clears all session headers and replaces with new Auth header"""

        self._check_closed()

        self.logger.debug("Refreshing session headers (Clear + Re-set)")

        self._session.headers.clear()

        token = self.auth.token()
        self._session.headers.update({"Authorization": f"Bearer {token}"})

        self.logger.debug("Session headers refreshed successfully")


    def _check_closed(self) -> None:
        """Checks if object has been closed and therefore is unusable"""


        if self._is_closed:
            self.logger.error("API CLOSED")
            raise RuntimeError(str(self) + " is closed")


    # Public Methods


    def close(self) -> None:
        """Invalidates tokens and deletes self"""

        self.logger.info("Closing %s", str(self))

        self.auth.invalidate()
        self._is_closed = True

        self.logger.info("%s closed", str(self))


    def url(self, target=None) -> str:
        """
        Allows access to base url from endpoint
        Universal interface across API versions
        """

        self._check_closed()
        if self._version == "classic":
            return self.base_url

        if self._version == "pro":
            return self.base_url.format(jamfapiversion=target)

        raise jamfpyConfigError("Invalid API version")


    def header(self, key: str) -> str:
        """Returns given set of headers from config"""
        self._check_closed()
        try:
            return self._headers[key]

        except KeyError as ve:
            raise KeyError("Invalid header key provided") from ve


    def do(self, request: Request, timeout=10, error_on_fail: bool = True) -> Response:
        """Takes request, preps and sends"""
        self._check_closed()
        self._refresh_session_headers()

        do_debug_string = "%s: Method: %s at: %s with headers: %s"

        request_header_log = "no headers supplied"
        if request.headers:
            request_header_log = request.headers if not self._safe_mode else "[redacted]"

        self.logger.debug(do_debug_string, "prepping", request.method, request.url, request_header_log)
        prepped = self._session.prepare_request(request)

        prepped_header_log = "no headers supplied"
        if prepped.headers:
            prepped_header_log = prepped.headers if not self._safe_mode else "[redacted]"

        self.logger.debug(do_debug_string, "sending", prepped.method, prepped.url, prepped_header_log)
        response = self._session.send(prepped, timeout=timeout)

        # Logging

        if not response.ok:
            error_text = response.text or "no error supplied"

            if error_on_fail:
                self.logger.critical("Request failed. Response: %s, error: %s", response, error_text)
                raise HTTPError("Bad response:", response.status_code)

            self.logger.debug("Request failed. Response: %s, error: %s", response, error_text)

        else:
            self.logger.debug("Success: Code: %s Req: %s %s", response.status_code, prepped.method, response.url)

        return response


class ClassicAPI(API):
    """Classic API child object"""

    _version = "classic"
    _short_name = "clc"

    def __init__(self, config):
        super().__init__(config, self._version)

        # Endpoints
        self.computers = ClassicComputers(self)
        self.computergroups = ComputerGroups(self)
        self.policies = Policies(self)
        self.configuration_profiles = ConfigurationProfiles(self)
        self.computer_extension_attributes = ExtensionAttributes(self)
        self.categories = Categories(self)
        self.dockitems = DockItems(self)


    # Magic Methods
    def __str__(self) -> str:
        return f"Jamf {self._version} API Client for {self.tenant}"


class ProAPI(API):
    """Pro API child object"""

    _version = "pro"
    _short_name = "pro"

    def __init__(self, config):
        super().__init__(config, self._version)
        self.apiintegrations = APIIntegrations(self)
        self.apiroleprivileges = APIRolePrivileges(self)
        self.apiroles = APIRoles(self)
        self.scripts = Scripts(self)
        self.sso = SsoCertificates(self)
        self.icons = Icons(self)
        self.computers_inventory = ComputersInventory(self)


    # Magic Methods
    def __str__(self) -> str:
        return f"Jamf {self._version} API Client for {self.tenant}"


class CustomAPI(API):
    """Custom API Endpoint for dynamic endpoint assignment"""

    _version = "custom"
    _short_name = "ctm"

    def __init__(
            self,
            config: dict ,
            version: str,
            endpoints: list
    ):
        super().__init__(config, version)
        self._version = version

        for ep in endpoints:
            setattr(self, ep.__name__, ep(self))

    def __str__(self) -> str:
        return f"Jamf {self._version} Custom Endpoint for {self.tenant}"


class Tenant:
    """Jamf parent object"""
    initiated_tenants = []

    def __init__(
      self,
      jp_fqdn: str,
      auth_method: str,
      client_id: str = None,
      client_secret: str = None,
      username: str = None,
      password: str = None,
      custom_session: Session = None,
      custom_logger: Logger = None,
      token_exp_threshold_mins: int = 5,
      mode: str = None,
      safe_mode: bool = True
    ):
        self.jp_fqdn = jp_fqdn
        self.token_exp_threshold_mins = token_exp_threshold_mins

        auth = self._init_validate_auth(
            self,
            auth_method,
            client_id,
            client_secret,
            username,
            password,
        )



    def _init_validate_auth(
            self,
            auth_method,
            client_id,
            client_secret,
            username,
            password
    ):
        """
        Method to validate the supplied configuration of auth credentials
        and instantialise an Auth object with them if valid

        Returns Auth or errors
        """

        if auth_method not in VALID_AUTH_METHODS:
            raise jamfpyConfigError("invalid auth method supplied: %s", auth_method)

        self.auth_method = auth_method

        match auth_method:

            case "oauth2":
                if not client_id or not client_secret:
                    raise jamfpyConfigError("invalid credential combination supplied for auth method")

                return OAuth(
                    tenant=self.jp_fqdn,
                    libconfig=libconfig,
                    logger_cfg=logger_config,
                    token_exp_thold_mins=self.token_exp_threshold_mins,
                    oauth_cid=client_id,
                    oauth_cs=client_secret
                )

            case "basic":

                if not username or not password:
                   raise jamfpyConfigError("invalid credential combination supplied for auth method")

                return BearerAuth(
                    tenant=self.jp_fqdn,
                    libconfig=libconfig,
                    logger_cfg=logger_config,
                    token_exp_thold_mins=self.token_exp_threshold_mins,
                    username=username,
                    password=password
                )

            case _:
                raise jamfpyConfigError("invalid auth method supplied: %s", auth_method)

    # Methods
    def __str__(self) -> str:
        return f"Jamf API Client for Tenant: {self.tenant} using {self._auth_method}"


    def close(self) -> None:
        """Closes all initied apis"""

        self._logger.warning("Closing APIs")

        if self.pro: 
            self.pro.close()
        
        if self.classic:
            self.classic.close()
