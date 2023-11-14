"""Python Jamf OAuth Handler"""
# pylint: disable=relative-beyond-top-level
# Libs
import datetime
import requests

from .logger import get_logger
from .exceptions import JamfAPIError


class Auth:
    token_expiry = None

    def __init__(
            self,
            tenant: str,
            libconfig: dict,
            logger_cfg: dict,
            token_exp_thold_mins: int = 2
    ):
        self._tenant = tenant
        self._libconfig = libconfig
        self._logger_cfg = logger_cfg
        self.token_exp_thold_mins = token_exp_thold_mins




    def _init_logger(self):
        self.logger = self._logger_cfg["custom_logger"] or get_logger (
            name=f"{self._tenant}-auth",
            config=self._logger_cfg
        )


    def _check_token_expiry(self) -> bool:
        now = datetime.datetime.now()
        time_until_exp = self.token_expiry - now
        if time_until_exp > datetime.timedelta(minutes=self.token_exp_thold_mins):
            return True
        
        return False
    
    

class OAuth:
    """Object to hold OAuth data and functions"""

    auth_token = ""
    token_expiry = ""
    def __init__(
            self,
            tenant: str,
            libconfig: dict,
            logger_cfg: dict,
            oauth_cid: str,
            oauth_cs: str,
            token_exp_threshold_mins: int = 0
    ):

        # Private
        self._libconfig = libconfig
        self._logger_config = logger_cfg
        self._oauth_cid = oauth_cid
        self._oauth_cs = oauth_cs

        # Public
        self.tenant = tenant
        self.token_exp_threshold_mins = token_exp_threshold_mins or 2

        # Init methods
        self._init_logging()
        self._set_auth_url()
        self._set_new_token()

        self.logger.debug("OAuth Init complete")


    def __str__(self):
        return f"Active OAuth Object for {self.tenant}, {self}"

    # Private Methods

    def _init_logging(self):
        """Assign custom logger or use default setting"""
        self.logger = self._logger_config["custom_logger"] or get_logger(
            name=f"{self.tenant}-oauth-0",
            config=self._logger_config
        )


    def _check_token_expiry(self) -> bool:
        """
        Checks if token is in the buffer zone (within x mins of expiry).
        If not in buffer, returns True else returns False
        
        """
        now = datetime.datetime.now()
        time_until_expiry = self.token_expiry - now
        self.logger.debug(f"Checking if token in active window, {now}, {time_until_expiry}")
        if time_until_expiry > datetime.timedelta(minutes=self.token_exp_threshold_mins):
            self.logger.debug("Token OK")
            return True

        self.logger.debug("Token in buffer")
        return False


    def _set_new_token(self) -> requests.Response:
        """Gets new token from Jamf"""

        self.logger.debug("Setting new token")

        url = self._oauth_url
        headers = self._libconfig["headers"]["auth"]["oauth"]
        data = {
            "client_id": self._oauth_cid,
            "client_secret": self._oauth_cs,
            "grant_type": "client_credentials"
        }

        call = requests.post(url=url, headers=headers, data=data, timeout=10)

        if call.ok:
            now = datetime.datetime.now()
            resp_json = call.json()
            self.auth_token = resp_json["access_token"]
            self.token_expiry = now + datetime.timedelta(seconds=resp_json["expires_in"])

            self.logger.info("New token set successfully")

            return call

        raise requests.HTTPError(call.status_code, "Invalid Credentials Supplied")


    def _set_auth_url(self) -> None:
        """Sets Auth URL using config"""

        self.logger.debug("_set_auth_url starting")

        endpoint = self._libconfig["urls"]["oauth"]
        self.base_url = self._libconfig["urls"]["base"].format(tenant=self.tenant)
        self._oauth_url = self.base_url + endpoint

        self.logger.debug("_set_base_url complete")
        self.logger.debug(f"Base URL set: {self.base_url}")

    # Public Methods

    def invalidate(self):
        """Invalidates token"""

        self.logger.warning("Invalidating token")

        url = self.base_url + self._libconfig["urls"]["invalidate_token"]
        headers = self._libconfig["headers"]["universal"]["basic_with_auth"].format(self.auth_token)
        call = requests.post(url, headers=headers, timeout=10)
        if call.ok:
            self.logger.warning("Invalidating token successful")

        return call


    def token(self):
        """
        Checks if token expiry is within buffer
        if yes, gets new token & returns with exp
        if no, returns token + exp
        """
        data = {"token": self.auth_token, "expiry": self.token_expiry}
        if self._check_token_expiry():
            return data

        self._set_new_token()
        if not self._check_token_expiry():
            raise JamfAPIError("Token lifetime shorter than expiry threashold")

        return data


    def update_credentials(self, new_cid: str, new_cs: str):
        """Updates OAuth Credentials"""
        self._oauth_cid = new_cid
        self._oauth_cs = new_cs
        self._set_new_token()



class BearerToken:
    """Bearer token obj"""
    auth_token = None
    token_expiry = None
    def __init__(
            self,
            tenant: str,
            libconfig: dict,
            logger_config: dict,
            bearer_token: str
    ):
        self._libconfig = libconfig
        self._tenant = tenant
        self.logger = logger_config["custom_logger"] or get_logger(
            f"{self._tenant}-bearer",
            config=logger_config
        )

        self.auth_token = bearer_token


    def invalidate(self):
        """Invalidates token"""
        base = self._libconfig["urls"]["base"].format(tenant=self._tenant)
        endpoint = self._libconfig["urls"]["invalidate_token"]
        url = base + endpoint
        headers = self._libconfig["headers"]["universal"]["basic"].format(token=self.auth_token)
        call = requests.post(
            url=url,
            headers=headers,
            timeout=10
        )
        return call

    def token(self):
        return self.auth_token
