"""
Jamf API Client Main
"""

# pylint: disable=relative-beyond-top-level

# Libraries
from typing import Any
import requests

# This lib
from .auth import OAuth, BearerAuth
from .exceptions import ConfigError

# Endpoints
from ..resources.classic.clc_computers import ClassicComputers
from ..resources.pro.pro_api_management import (
    APIRolePrivileges,
    APIIntegrations,
    APIRoles
)
from ..resources.pro.pro_scripts import Scripts
from ..resources.classic.clc_computer_groups import ComputerGroups
from ..resources.pro.pro_sso_certificate import SsoCertificates
from .logger import get_logger


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

        # Private
        self._version: str = version
        self._libconfig: dict = config["libconfig"]
        self._logger_config: dict = config["logging"]
        self._auth_method: str = config["auth_method"]
        self._session: requests.Session = config["session"]

        # Public
        self.tenant: str = config["tenant"]
        self.auth: OAuth or BearerAuth = config["auth"]

        # Init Methods - Logging
        self._init_logging()
        self.logger.debug("API initialising...")

        # Init Methods
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

        self._check_if_closed()

        self.logger.debug("Refreshing session headers (Clear + Re-set)")

        self._session.headers.clear()

        token = self.auth.token()
        self._session.headers.update({"Authorization": f"Bearer {token}"})

        self.logger.debug("Session headers refreshed successfully")


    def _check_if_closed(self) -> None:
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


    def url(self, target=None) -> None:
        """
        Allows access to base url from endpoint
        Universal interface across API versions
        """

        self._check_if_closed()
        if self._version == "classic":
            return self.base_url

        if self._version == "pro":
            return self.base_url.format(jamfapiversion=target)

        raise ConfigError("Invalid API version")


    def header(self, key: str) -> dict:
        """Returns given set of headers from config"""
        self._check_if_closed()
        try:
            return self._headers[key]

        except KeyError as ve:
            raise KeyError("Invalid header key provided") from ve


    def do(self, request: requests.Request) -> requests.Response:
        """Takes request, preps and sends"""
        self._check_if_closed()
        
        self._refresh_session_headers()

        self.logger.debug("Prepping %s", request)
        prepped = self._session.prepare_request(request)

        self.logger.debug("Sending %s", prepped)
        response = self._session.send(prepped)

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


    # Magic Methods
    def __str__(self):
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


    # Magic Methods
    def __str__(self):
        return f"Jamf {self._version} API Client for {self.tenant}"


class AuthManagerProAPI(API):
    """API with only Auth management endpoints"""

    _version = "pro"
    _short_name = "auth"

    def __init__(self, config):
        super().__init__(config, self._version)

        # Endpoints
        self.apiintegrations = APIIntegrations(self)
        self.apiroleprivileges = APIRolePrivileges(self)
        self.apiroles = APIRoles(self)


    # Magic Methods
    def __str__(self):
        return f"Jamf {self._version} AUTH ONLY API Client for {self.tenant}"


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

    def __str__(self):
        return f"Jamf {self._version} Custom Endpoint for {self.tenant}"


class JamfTenant:
    """Jamf parent object"""
    initiated_tenants = []

    def __init__(
            self,
            tenant: str,
            auth_method: str,
            logger_config: dict = None,
            classic: ClassicAPI = None,
            pro: ProAPI = None
    ):

        self.tenant = tenant
        self._auth_method = auth_method

        self._logger = get_logger(
            name=f"{self.tenant}-tnt-0",
            config=logger_config
        )

        if classic:
            self.classic: ClassicAPI = classic
            self.initiated_tenants.append(self.classic)

        if pro:
            self.pro: ProAPI or AuthManagerProAPI = pro
            self.initiated_tenants.append(self.pro)

        if not classic and not pro:
            raise ConfigError("No APIs Provided for Jamf Object")

    # Methods
    def __str__(self):
        return f"Jamf API Client for Tenant: {self.tenant} using {self._auth_method}"

    def close(self):
        """Closes all initied apis"""
        self._logger.warning("Closing APIs")
        for api in self.initiated_tenants:
            api.close()
