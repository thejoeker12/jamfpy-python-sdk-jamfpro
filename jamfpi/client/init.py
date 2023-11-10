"""
Init function for API Objects
"""

# TEMP - Pylint Exceptions
# pylint: disable=import-error
# pylint: disable=wrong-import-position
# pylint: disable=wrong-import-order
# pylint: disable=broad-exception-raised

# Libs
import logging
import requests

# This Lib
from .api import ProAPI, ClassicAPI, AuthManagerProAPI, Jamf
from .default_logging import default_logger
from .auth import OAuth
from .utility import import_config
from .defaultconfig import defaultconfig
from .exceptions import InitError, ConfigError


def init_client(
        tenant_name: str,
        config_filepath: str = None,
        bearer_token: str = None,
        client_id: str = None,
        client_secret: str = None,
        session: requests.Session = None,
        logger: logging.Logger = None,
        logging_level=None,
        logging_format: str = None,
        token_exp_threshold_mins: int = None,
        mode: str = None,
        debug_params: list = None,
        # custom_endpoints: str = None
):

    """Initilizes a new Jamf instance object"""

    # Logging
    logger = logger or default_logger(
        logger_name=f"{tenant_name}-ini",
        logging_format=logging_format,
        logging_level=logging_level
    )
    logger.debug(f"Logger initialised, {logger}")
    logging_config = {
        "logging_level": logging_level,
        "logging_format": logging_format
    }

    logger.debug(f"{tenant_name} init started")


    # Config File
    if config_filepath:
        config_file = import_config(config_filepath)
        logger.debug(f"Using imported log from {config_filepath}")
    else:
        config_file = defaultconfig
        logger.debug("Using default config")


    # Session
    session = session or requests.Session()
    logger.debug(f"Session initialised, {session}")


    # Auth
    if bearer_token:
        auth_method = "bearer"
        logger.info(f"Auth Method: {auth_method}")
        oauth = None

    elif client_id and client_secret:
        auth_method = "oauth"
        logger.info(f"Auth Method: {auth_method}")
        token_exp_threshold_mins = token_exp_threshold_mins or 5
        logger.debug("Initiating OAuth")
        oauth = OAuth(
            config=config_file,
            logging_config=logging_config,
            tenant=tenant_name,
            oauth_cid=client_id,
            oauth_cs=client_secret,
            token_exp_threshold_mins=token_exp_threshold_mins
        )

    else:
        raise InitError("Invalid Auth supplied")


    if bearer_token:
        logger.warning("Auth method is bearer token. Reccommend using OAuth when able")


    # Master Config
    api_config = {
        "config_file": config_file,
        "session": session,
        "logging": logging_config,
        "bearer_token": bearer_token or None,
        "oauth": oauth,
        "tenant": tenant_name,
        "auth_method": auth_method,
        "debug_params": debug_params
    }


    # Mode
    if not mode:
        classic = ClassicAPI(api_config)
        pro = ProAPI(api_config)

    elif mode == "classic":
        classic = ClassicAPI(api_config)
        pro = None

    elif mode == "pro":
        classic = None
        pro = ProAPI(api_config)

    elif mode == "auth":
        classic = None
        pro = AuthManagerProAPI(api_config)

    elif mode == "custom":
        print("Feature not built yet")
        raise Exception("Nope try again...") # WIP.

    else:
        raise ConfigError("Invalid API Mode")

    logger.info(f"{tenant_name} Init Complete")
    del logger

    return Jamf(
        tenant=tenant_name,
        classic=classic,
        pro=pro
    )
