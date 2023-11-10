"""
Jamf API Client Main
"""

# Libraries
from typing import Any
import requests

# This lib
from .auth import OAuth
from .exceptions import ConfigError

# Endpoints
from ..resources.classic.clc_computers import ClassicComputers
from ..resources.pro.pro_api_management import (
    # APIIntegration,
    APIRolePrivileges,
    APIIntegrations,
    APIRoles
)
from .default_logging import default_logger

# Objects
# None yet

class API:
    """Parent class for Jamf API"""
    _headers_dict = {}
    token = None

    def __init__(
            self,
            config: dict[str: Any],
            version: str
    ) -> None:

        # Private
        self._config: dict = config["config_file"]
        self._bearer_token: str = config["bearer_token"]
        self._session: requests.Session = config["session"]
        self._logger_config: dict = config["logging"]
        self._version: str = version
        self._debug_params = config["debug_params"]

        # Public
        self.tenant: str = config["tenant"]
        self.oauth: OAuth = config["oauth"]


        # Init methods
        self._init_logging()
        self.logger.debug("%s init starting...", self.tenant)

        self._init_debug(config)
        self._init_baseurl()
        self._init_headers()
        self._init_auth()
        self._refresh_session_headers()

        # Logging
        self.logger.debug("%s API for %s init complete", self._version, self.tenant)


    # Private Methods

    def _init_logging(self):
        """Sets three character API version identifier for consistent logging"""
        chr_map = {
            "classic": "clc",
            "pro": "pro",
            "custom": "ctm"
        }
        try:
            self._vers_3chr = chr_map[self._version]
        except ValueError as e:
            raise ValueError("Invalid version mapping in Logger") from e

        self.logger = default_logger(
            logger_name=f"{self.tenant}-{self._vers_3chr}",
            logging_level=self._logger_config["logging_level"],
            logging_format=self._logger_config["logging_format"]
        )


    def _init_debug(self, config):
        """Parses debug params"""
        if "debug_params" in config:
            if config["debug_params"] is not None:
                self.logger.debug("Debug modes enabled: %s", self._debug_params)
                self._debug = True
                self._debug_params = config["debug_params"]
                self.logger.warning("Debug mode enabled")
        else:
            self._debug = False
            self._debug_params = []

        self.logger.debug("_init_debug complete")


    def _init_baseurl(self):
        """Sets base URL"""
        template: str = self._config["urls"]["base"].format(tenant=self.tenant)
        endpoint: str = self._config["urls"]["api"][self._version]
        self.base_url = template + endpoint
        self.logger.debug("_init_baseurl complete")


    def _init_auth(self):
        """Auth Init"""
        if self._bearer_token:
            self._auth_method = "bearer"
            self.token = self._bearer_token

        elif self.oauth:
            self._auth_method = "oauth"
            self._refresh_token()

        else:
            raise ConfigError("Invalid Auth Method supplied")

        self.logger.debug("_init_auth complete")


    def _init_headers(self):
        """Inits headers"""
        self._headers = self._config["headers"][self._version]
        self.logger.debug("_init_headers complete")


    def _refresh_token(self):
        """Sets api token"""
        token_data = self.oauth.token()
        self.token = token_data["token"]


    def _invalidate_bearer_token(self):
        self.logger.warning("Invalidating bearer token")
        base = self._config["urls"]["base"].format(tenant=self.tenant)
        url = base + self._config["urls"]["invalidate_token"]
        headers = {"accept": "application/json"}
        req = requests.Request("POST", url=url, headers=headers)
        call = self.do(req)
        if call.ok:
            self.logger.warning("Bearer token invalidated successfully")

        return call


    def _refresh_session_headers(self):
        """Updates session headers with new auth token"""
        self._session.headers.clear()
        self._session.headers.update({"Authorization": f"Bearer {self.token}"})
        self.logger.debug("session headers refreshed")


    # Public Methods

    def stop(self):
        """Do stuff that stops"""

    def url(self, target):
        """Returns urls"""
        if self._version == "classic":
            return self.base_url

        if self._version == "pro":
            return self.base_url.format(jamfapiversion=target)

        raise ConfigError("Invalid API version")


    def header(self, key: str) -> dict:
        """Returns given set of headers from config"""
        try:
            return self._headers[key]

        except ValueError as ve:
            raise ValueError("Invalid header key provided") from ve


    def do(self, request):
        """Takes request, preps and sends"""
        if self._auth_method == "oauth":
            self._refresh_token()
            self._refresh_session_headers()

        self.logger.debug("Prepping %s", request)
        prepped = self._session.prepare_request(request)

        self.logger.debug("Sending %s", prepped)
        response = self._session.send(prepped)

        return response


class ClassicAPI(API):
    """Classic API child object"""
    _version = "classic"
    def __init__(self, config):
        super().__init__(config, self._version)

        # Endpoints
        self.computers = ClassicComputers(self)

    # Magic Methods
    def __str__(self):
        return f"Jamf {self._version} API Client for {self.tenant}"



class ProAPI(API):
    """Pro API child object"""
    _version = "pro"
    def __init__(self, config):
        super().__init__(config, self._version)
        self.apiintegrations = APIIntegrations(self)
        self.apiroleprivileges = APIRolePrivileges(self)
        self.apiroles = APIRoles(self)

    # Magic Methods
    def __str__(self):
        return f"Jamf {self._version} API Client for {self.tenant}"


class AuthManagerProAPI(API):
    """API with only Auth management endpoints"""
    _version = "pro"
    def __init__(self, config):
        super().__init__(config, self._version)
        self.apiintegrations = APIIntegrations(self)
        self.apiroleprivileges = APIRolePrivileges(self)
        self.apiroles = APIRoles(self)

    # Magic Methods
    def __str__(self):
        return f"Jamf {self._version} AUTH ONLY API Client for {self.tenant}"



class CustomAPI(API):
    """Custom API Endpoint for dynamic endpoint assignment"""
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


class Jamf:
    """Jamf parent object"""
    initiated_tenants = []
    def __init__(
            self,
            tenant: str,
            classic: ClassicAPI = None,
            pro: ProAPI = None
    ):
        # Private
        self.tenant = tenant

        # Public
        if classic:
            self.classic: ClassicAPI = classic
            self.initiated_tenants.append(self.classic)

        if pro:
            self.pro: ProAPI or AuthManagerProAPI = pro
            self.initiated_tenants.append(self.pro)

        if not classic and not pro:
            raise ConfigError("No APIs Provided for Jamf Object")

    def __str__(self):
        return f"Jamf API Client for Tenant: {self.tenant}"

    def close(self):
        """Closes all initied apis"""
        for api in self.initiated_tenants:
            api.stop()
