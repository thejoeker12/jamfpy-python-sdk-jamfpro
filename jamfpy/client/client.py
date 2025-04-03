"""
Jamf API Client Main
"""

from typing import Any
from requests import Session, Request, Response, HTTPError
from logging import Logger

from .auth import Auth
from .exceptions import jamfpyConfigError
from .logger import get_logger
from .http_config import HTTPConfig
from .constants import DEFAULT_LOG_LEVEL
from .utility import extract_cloud_tenant_name_from_url

from ..endpoints.clc_computer_groups import ComputerGroups
from ..endpoints.clc_policies import Policies
from ..endpoints.clc_osxconfiguration_profiles import ConfigurationProfiles
from ..endpoints.clc_computer_extension_attributes import ExtensionAttributes
from ..endpoints.clc_categories import Categories
from ..endpoints.clc_advanced_computer_searches import AdvancedComputerSearches
from ..endpoints.clc_scripts import Scripts
from ..endpoints.clc_buildings import Buildings
from ..endpoints.clc_packages import Packages
from ..endpoints.clc_computers import Computers
from ..endpoints.clc_sites import Sites
from ..endpoints.clc_departments import Departments
from ..endpoints.clc_static_computer_groups import StaticComputerGroups

# from ..endpoints.refactor_queue.clc_dock_items import DockItems

# from ..endpoints.refactor_queue.pro_api_management import (
#     APIRolePrivileges,
#     APIIntegrations,
#     APIRoles
# )
# from ..endpoints.pro_scripts import Scripts
# from ..endpoints.refactor_queue.pro_sso_certificate import SsoCertificates
# from ..endpoints.refactor_queue.pro_icon import Icons
# from ..endpoints.refactor_queue.pro_computers_inventory import ComputersInventory


class API:
    """Parent class for Jamf API"""

    _headers_dict = {}
    _is_closed = False
    _short_name = None
    _version: str
    _http_config: HTTPConfig
    _logger: Logger

    def __init__(
            self,
            fqdn: str,
            auth: Auth,
            log_level,
            http_config: HTTPConfig,
            safe_mode: bool,
            session: Session,
            logger: Logger,

    ) -> None:

        self._fqdn = fqdn
        self.auth = auth
        self._http_config: HTTPConfig = http_config

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
        shortname = extract_cloud_tenant_name_from_url(self._fqdn)

        return logger or get_logger(
            name=f"{shortname}-{shortname}",
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



    # Private Methods - Normal

    # def _check_closed(self, func):
    #     """Checks if object has been closed and therefore is unusable"""

    #     def wrapper(*args, **kwargs):
    #         if self._is_closed:
    #             raise RuntimeError(str(self) + " is closed")
            
    #         return func(*args, **kwargs)

    #     return wrapper


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

        raise jamfpyConfigError("Invalid API version")


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

        response = self._session.send(prepped, timeout=timeout)

        # response.raise_for_status()

        self._logger.debug("Success: Code: %s Req: %s %s", response.status_code, prepped.method, response.url)

        return response


class ClassicAPI(API):
    """Classic API child object"""

    _version = "classic"
    _short_name = "clc"

    def __init__(
            self,
            fqdn: str,
            auth: Auth,
            log_level = DEFAULT_LOG_LEVEL,
            http_config: HTTPConfig = HTTPConfig(),
            safe_mode: bool = True,
            session: Session = None,
            logger: Logger = None,
    ):

        # no dynamic args here to preserve the hints.
        super().__init__(
            fqdn=fqdn,
            auth=auth,
            log_level=log_level,
            http_config=http_config,
            safe_mode=safe_mode,
            session=session,
            logger=logger
        )

        # Endpoints
        self.computergroups = ComputerGroups(self)
        self.policies = Policies(self)
        self.configuration_profiles = ConfigurationProfiles(self)
        self.computer_extension_attributes = ExtensionAttributes(self)
        self.categories = Categories(self)
        self.computer_searches = AdvancedComputerSearches(self)
        self.scripts = Scripts(self)
        self.buildings = Buildings(self)
        self.packages = Packages(self)
        self.computers = Computers(self)
        self.sites = Sites(self)
        self.departments = Departments(self)
        self.static_computer_groups = StaticComputerGroups(self)
        # self.dockitems = DockItems(self)


    # Magic Methods
    def __str__(self) -> str:
        return f"Jamf {self._version} API Client for {self._fqdn}"


class ProAPI(API):
    """Pro API child object"""

    _version = "pro"
    _short_name = "pro"

    def __init__(
            self,
            fqdn: str,
            auth: Auth,
            log_level = DEFAULT_LOG_LEVEL,
            http_config: HTTPConfig = HTTPConfig(),
            safe_mode: bool = True,
            session: Session = None,
            logger: Logger = None,
    ):

        # no dynamic args here to preserve the hints.
        super().__init__(
            fqdn=fqdn,
            auth=auth,
            log_level=log_level,
            http_config=http_config,
            safe_mode=safe_mode,
            session=session,
            logger=logger
        )

        # self.apiintegrations = APIIntegrations(self)
        # self.apiroleprivileges = APIRolePrivileges(self)
        # self.apiroles = APIRoles(self)
        # self.scripts = Scripts(self)
        # self.sso = SsoCertificates(self)
        # self.icons = Icons(self)
        # self.computers_inventory = ComputersInventory(self)


    # Magic Methods
    def __str__(self) -> str:
        return f"Jamf {self._version} API Client for {self._fqdn}"
