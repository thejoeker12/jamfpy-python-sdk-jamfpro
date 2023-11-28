"""Python Jamf OAuth Handler"""
# pylint: disable=relative-beyond-top-level
# Libs
import datetime
import requests
from typing import Callable, Optional
from base64 import b64encode

from .logger import get_logger
from .exceptions import JamfAPIError, InitError, AuthError
from ..config.defaultconfig import ROUND_AMOUNT
from .utility import fix_jamf_time_to_iso

class Auth:
    _token_str: Optional[str]
    token_expiry: datetime.time
    _method: str
    _keep_alive_token: Callable
    _set_new_token: Callable

    def __init__(
            self,
            tenant: str,
            libconfig: dict,
            logger_cfg: dict,
            token_exp_thold_mins: int
    ):
        self._tenant = tenant
        self._libconfig = libconfig
        self._logger_cfg = logger_cfg
        self.token_exp_thold_mins = token_exp_thold_mins or 2

        self._init_logger()
        self._init_urls()
        

    def _init_logger(self) -> None:
        """
        Applies proivded custom logger or uses config
        """
        self.logger = self._logger_cfg["custom_logger"] or get_logger (
            name=f"{self._tenant}-auth-{self._method}",
            config=self._logger_cfg
        )
        self.logger.debug("Logger initialised")


    def _init_urls(self) -> None:
        """
        Sets object vars for urls for readability.
        
        E.g
        self._base_url = https://your_server.jamfcloud.com
        self._auth_url = https://your_server.jamfcloud.com/api/oauth/token
        """

        self.logger.debug("FUNCTION: _init_urls")

        self._base_url = self._libconfig.urls["base"].format(tenant=self._tenant)
        self.logger.debug("Base URL set %s", self._base_url)

        endpoint = self._libconfig.urls["auth"][self._method] 
        self._auth_url = self._base_url + endpoint
        self.logger.debug("Auth URL set: %s", self._auth_url)


    def check_token_in_buffer(self) -> bool:
        """
        Checks if token is within the buffer period.

        example:
        self.token_exp_thold_mins = 2
        now = 10:30am
        self.token_expiry = 10:31
        
        function will return True
        """
        self.logger.debug("FUNCTION: check_token_in_buffer")

        self.logger.debug("Expiry time: %s", self.token_expiry)

        now = round(datetime.datetime.utcnow(datetime.timezone.utc).timestamp(), ROUND_AMOUNT)
        self.logger.debug("Now: %s", now)

        expiry_delta_secs = round(self.token_expiry - now, ROUND_AMOUNT)
        expiry_delta_mins = round(expiry_delta_secs / 60, ROUND_AMOUNT)
    
        self.logger.debug("Expiry Delta mins/secs: %s/%s", expiry_delta_mins, expiry_delta_secs)

        if expiry_delta_mins < self.token_exp_thold_mins:
            self.logger.warn("Token in buffer")     
            return True
        
        self.logger.debug("Token not in buffer")
        return False
    

    def check_token_is_expired(self) -> bool:
        """
        Checks if token expiry time has passed
        """
        self.logger.debug("FUNCTION: check_token_is_expired")

        now = datetime.datetime.utcnow(datetime.timezone.utc).timestamp()
        if now > self.token_expiry:
            self.logger.warn("Token expired")
            return True
        
        self.logger.debug("Token not expired")
        return False
    

    def check_token(self) -> None:
        """
        Proccess of checking and refreshing token
        Occurs before every request to ensure no usage of old tokens
        """
        self.logger.debug("FUNCTION: check_token")

        if self.check_token_is_expired():
            self._set_new_token()
            if self.check_token_in_buffer():
                raise AuthError("Buffer longer than token lifetime")
            
        elif self.check_token_in_buffer():
            if self. _method == "bearer":
                self._keep_alive_token()
            elif self._method == "oauth":
                self._set_new_token()

            if self.check_token_in_buffer():
                raise AuthError("Buffer longer than token lifetime")


    def token(self) -> None:
        """Checks token and returns"""
        self.logger.debug("FUNCTION: token")
        self.check_token()
        return self._token_str
    

    def invalidate(self):
        """
        invalidates token
        """
        url = self._libconfig.urls["invalidate-token"]
        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {self._token_str}"
        }
        call = requests.post(
            url=url,
            headers=headers
        )

        if call.ok:
            return True
        
        return False




class OAuth(Auth): 
    _method = "oauth"
    def __init__(
            self,
            tenant,
            libconfig,
            logger_cfg,
            token_exp_thold_mins,
            oauth_cid,
            oauth_cs
    ):
        super().__init__(
            tenant,
            libconfig,
            logger_cfg,
            token_exp_thold_mins
        )

        self._oauth_cid = oauth_cid
        self._oauth_cs = oauth_cs

    # Magic

    def __str__(self):
        return f"OAuth Object for {self._tenant}"

    # Private

    def _set_new_token(self):
        self.logger.debug("FUNCTION: _set_new_token")
        """
        Get new token
        update self values
        """
        endpoint = self._libconfig.urls["auth"]["oauth"]
        url = self._base_url + endpoint
        headers = self._libconfig.headers["auth"]["oauth"]
        data = {
            "client_id": self._oauth_cid,
            "client_secret": self._oauth_cs,
            "grant_type": "client_credentials"
        }

        call = requests.post(
            url=url,
            headers=headers,
            data=data,
            timeout=10
        )

        if call.ok:
            call_json = call.json()
            self._token_str = call_json["access_token"]
            now = datetime.datetime.utcnow()
            self.token_expiry = (now + datetime.timedelta(seconds=call_json["expires_in"])).timestamp()
            self.token_expiry = round(self.token_expiry, ROUND_AMOUNT)
            self.logger.debug("Token set successfully")

        else:
            raise requests.HTTPError("Bad call response")
    

    def _keep_alive_token(self):
        """
        Pleaced to ensure interface symetry.
        """
        raise AuthError("Action not available with OAuth interface.")




class BearerAuth(Auth):
    _method = "bearer"

    def __init__(
            self,
            tenant, 
            libconfig,
            logger_cfg,
            token_exp_thold_mins,
            username: Optional[str] = None,
            password: Optional[str] = None,
            basic_auth_token: Optional[str] = None,
    ):
        
        super().__init__(
            tenant=tenant,
            libconfig=libconfig,
            logger_cfg=logger_cfg,
            token_exp_thold_mins=token_exp_thold_mins
        )

        self.username = username
        self.password = password
        self.basic_auth_token = basic_auth_token
        self._init_auth()


    # Magic
    def __str__(self):
        return f"Bearer Token Object for {self._tenant}"


    # Private
    def _init_auth(self):
        """
        Sets basic auth token if user name and password are provided
        """
        self.logger.debug("FUNCTION: _init_auth")
        if self.username and self.password:
            credstring = f"{self.username}:{self.password}"
            self.basic_auth_token = b64encode(bytes(credstring, encoding="UTF-8")).decode()
        elif self.basic_auth_token:
            pass
        

    def _set_new_token(self):
        
        """
        Gets new token using stored credentials
        update obj values
        """
        self.logger.debug("FUNCTION: _set_new_token")
        url = self._base_url + self._libconfig.urls["auth"]["bearer"]
        
        headers = {
            "accept": "application/json",
            "Authorization": f"Basic {self.basic_auth_token}"  
        }

        call = requests.post(
            url=url,
            headers=headers
        )

        if call.ok:
            call_json = call.json()
            self._token_str = call_json["token"]
            expiry_str = call_json["expires"]
            fixed_expiry_str = fix_jamf_time_to_iso(expiry_str)
            self.token_expiry = datetime.datetime.fromisoformat(fixed_expiry_str).timestamp()
        else:

            raise Exception("Error getting new token")
    

    def _keep_alive_token(self):
        self.logger.debug("_keep_alive_token starting")
        """"
        Keeps token alive
        updates obj values
        """
        url = self._base_url + self._libconfig.urls["auth"]["keep-alive"]
        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {self._token_str}"
        }
        call = requests.post(
            url=url,
            headers=headers
        )
        if call.ok:
            call_json = call.json()
            self._token_str = call_json["token"]
            expiry_str = call_json["expires"]
            self.token_expiry = datetime.datetime.fromisoformat(expiry_str.replace('Z', '+00:00')).timestamp()
            self.logger.debug("_keep_alive_token complete")

        else:
            raise Exception("Error keeping token alive")
