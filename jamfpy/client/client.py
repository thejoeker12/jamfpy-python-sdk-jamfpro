"""Core client module for Jamf Pro API interactions, providing base API client functionality and specific implementations for Pro and Classic APIs."""

from logging import Logger
from requests import Session


from .auth import Auth
from .http_config import HTTPConfig
from .constants import DEFAULT_LOG_LEVEL
from .api import API

from ..endpoints.clc_endpoints import (
    ComputerGroups,
    MobileDeviceGroups,
    Policies,
    ConfigurationProfiles,
    ExtensionAttributes,
    Categories,
    AdvancedComputerSearches,
    Scripts,
    Buildings,
    Packages,
    Computers,
    Sites,
    Departments,
    RestrictedSoftware
)

from ..endpoints.clc_endpoints_accounts import Accounts

from ..endpoints.pro_scripts import Scripts as ProScripts
from ..endpoints.pro_mdm_commands import MDMCommands as ProMDMCommands
from ..endpoints.pro_app_installers import AppInstallers

class ClassicAPI(API):
    """Implementation of the Classic Jamf Pro API (JSS) endpoints and functionality."""

    _version = "classic"
    _short_name = "clc"

    def __init__(
            self,
            *,
            fqdn: str,
            auth: Auth,
            log_level = DEFAULT_LOG_LEVEL,
            http_config: HTTPConfig = HTTPConfig(),
            safe_mode: bool = True,
            session: Session = None,
            logger: Logger = None,
            cert_path: str = None,
            verify_path: str = None,
    ):

        # no dynamic args here to preserve the hints.
        super().__init__(
            fqdn=fqdn,
            auth=auth,
            log_level=log_level,
            http_config=http_config,
            safe_mode=safe_mode,
            session=session,
            logger=logger,
            cert_path=cert_path,
            verify_path=verify_path
        )

        # Endpoints
        self.computer_groups = ComputerGroups(self)
        self.mobile_device_groups = MobileDeviceGroups(self)
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
        self.policies = Policies(self)
        self.accounts = Accounts(self)
        self.restricted_software = RestrictedSoftware(self)



class ProAPI(API):
    """Implementation of the modern Jamf Pro API (v1+) endpoints and functionality."""

    _version = "pro"
    _short_name = "pro"

    def __init__(
            self,
            *,
            fqdn: str,
            auth: Auth,
            log_level = DEFAULT_LOG_LEVEL,
            http_config: HTTPConfig = HTTPConfig(),
            safe_mode: bool = True,
            session: Session = None,
            logger: Logger = None,
            cert_path: str = None,
            verify_path: str = None,
    ):

        super().__init__(
            fqdn=fqdn,
            auth=auth,
            log_level=log_level,
            http_config=http_config,
            safe_mode=safe_mode,
            session=session,
            logger=logger,
            cert_path=cert_path,
            verify_path=verify_path
        )

        self.scripts = ProScripts(self)
        self.mdm = ProMDMCommands(self)
        self.app_installers = AppInstallers(self)

    # Magic Methods
    def __str__(self) -> str:
        return f"Jamf {self._version} API Client for {self._fqdn}"
