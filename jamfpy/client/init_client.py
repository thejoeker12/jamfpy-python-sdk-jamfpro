"""
Init function for API Objects
"""

# pylint: disable=broad-exception-raised, unused-argument

# Libs
from logging import Logger
import requests

# This Lib
from .client import ProAPI, ClassicAPI, AuthManagerProAPI, JamfTenant
from .logger import get_logger
from .auth import OAuth, BearerAuth
from .utility import import_json
from ..config.defaultconfig import defaultconfig, MasterConfig
from .exceptions import jamfpyInitError, jamfpyConfigError




def init_client(
        tenant_name: str,
        config_filepath: str = None,
        basic_token: str = None,
        username: str = None,
        password: str = None,
        client_id: str = None,
        client_secret: str = None,
        session: requests.Session = None,
        custom_logger: Logger = None,
        logging_level=None,
        logging_format: str = None,
        token_exp_threshold_mins: int = None,
        mode: str = None,
        safe_mode: bool = True,
        # custom_auth: OAuth | BearerAuth = None
) -> JamfTenant:

    """Initilizes a new Jamf instance object"""


    # Logger Setup
    if custom_logger:
        if not isinstance(custom_logger, Logger):
            raise RuntimeError("Bad custom logger type:", type(custom_logger))

    logger_config = {
        "custom_logger": custom_logger,
        "logging_level": logging_level,
        "logging_format": logging_format
    }

    # Logger for init function
    logger = custom_logger or get_logger(
        name=f"{tenant_name}-ini",
        config=logger_config
    )

    # Init Start
    logger.debug("%s client init started", tenant_name)


    # Config File
    if config_filepath:
        imported = import_json(config_filepath)
        libconfig = MasterConfig(imported)
        logger.info("Config: Custom - PATH %s", config_filepath)
    else:
        libconfig = MasterConfig(defaultconfig)
        logger.info("Config: Default")


    # Session
    session = session or requests.Session()
    logger.debug("Shared requests.Session initialised")


    # Auth - WIP
    if client_id and client_secret:
        auth_method = "oauth"
        auth = OAuth(
            tenant=tenant_name,
            libconfig=libconfig,
            logger_cfg=logger_config,
            token_exp_thold_mins=token_exp_threshold_mins,
            oauth_cid=client_id,
            oauth_cs=client_secret
        )

    elif (username and password) or basic_token:
        auth_method = "bearer"
        auth = BearerAuth(
            tenant=tenant_name,
            libconfig=libconfig,
            logger_cfg=logger_config,
            token_exp_thold_mins=token_exp_threshold_mins,
            username=username,
            password=password,
            basic_auth_token=basic_token,
        )

    else:
        raise jamfpyInitError("Bad combination of Authentication info provided.\nPlease refer to docs.")

    auth.set_new_token()

    # Master Config
    api_config = {
        "tenant": tenant_name,
        "libconfig": libconfig,
        "logging": logger_config,
        "session": session,
        "auth_method": auth_method,
        "auth": auth,
        "safe_mode": safe_mode
    }


    # Mode
    match mode:
        case None | "":
            classic = ClassicAPI(api_config)
            pro = ProAPI(api_config)

        case "classic":
            classic = ClassicAPI(api_config)
            pro = None

        case "pro":
            classic = None
            pro = ProAPI(api_config)

        case "auth":
            classic = None
            pro = AuthManagerProAPI(api_config)

        case _:
            raise jamfpyConfigError("Invalid API Mode")

    logger.info("%s Init Complete", tenant_name)

    return JamfTenant(
        tenant=tenant_name,
        auth_method=auth_method,
        logger_config=logger_config,
        classic=classic,
        pro=pro
    )


class Config:
    def __init__(
      self,
      jp_fqdn: str,
      auth_method: str,
      client_id: str = None,
      client_secret: str = None,
      username: str = None,
      password: str = None,
      custom_session: requests.Session = None,
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
