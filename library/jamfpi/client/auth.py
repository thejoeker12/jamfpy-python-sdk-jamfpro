"""Python Jamf OAuth Handler"""

# TEMP - Pylint Exceptions
# pylint: disable=import-error
# pylint: disable=wrong-import-position
# pylint: disable=wrong-import-order
# pylint: disable=too-many-instance-attributes
# pylint: disable=broad-exception-raised

# Libs
import datetime
import requests
import logging

from .default_logging import default_logger
from .exceptions import JamfAPIError

class OAuth:
    """Object to hold OAuth data and functions"""

    auth_token = ""
    token_expiry = ""
    def __init__(
            self,
            logging_config: dict,
            config: dict,
            tenant: str,
            oauth_cid: str,
            oauth_cs: str,
            token_exp_threshold_mins=0
    ):

        # Private
        self._oauth_cid = oauth_cid
        self._oauth_cs = oauth_cs
        self._logging_config = logging_config

        # Public
        self.config = config
        self.tenant = tenant
        self.token_exp_threshold_mins = token_exp_threshold_mins

        # Init methods
        self._init_logging()
        self._set_auth_url()
        self._set_new_token()

        # Config
        if self.token_exp_threshold_mins == 0:
            self.token_exp_threshold_mins = 5

        self.logger.debug("OAuth Init complete")


    def __str__(self):
        return f"Active OAuth Object for {self.tenant}, {self}"

    # Private Methods

    def _init_logging(self):
        self.logger = default_logger(
            logger_name=f"{self.tenant}-oauth",
            logging_format=self._logging_config["logging_format"],
            logging_level=self._logging_config["logging_level"]
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
        headers = self.config["headers"]["auth"]["oauth"]
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
        endpoint = self.config["urls"]["oauth"]
        self.base_url = self.config["urls"]["base"].format(tenant=self.tenant)
        self._oauth_url = self.base_url + endpoint
        self.logger.debug(f"Base URL set: {self.base_url}")


    def _invalidate_token(self):
        self.logger.warning("Invalidating token")
        url = self.base_url + self.config["urls"]["invalidate_token"]
        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {self.token()}"
        }
        call = requests.post(url, headers=headers)
        if call.ok:
            self.logger.warning("Invalidating token successful")
        return call


    # Public Methods

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


    def update_oauth_credentials(self, new_cid: str, new_cs: str):
        """Updates OAuth Credentials"""
        self._oauth_cid = new_cid
        self._oauth_cs = new_cs
        self._set_new_token()
