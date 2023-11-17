"""Python Jamf OAuth Handler"""
# pylint: disable=relative-beyond-top-level
# Libs
import datetime
import requests
from typing import Callable, Optional
from base64 import b64encode

from .logger import get_logger
from .exceptions import JamfAPIError, InitError


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


    def _init_urls(self) -> None:
        """Sets URL for gaining a new token"""
        self._base_url = self._libconfig.urls["base"].format(tenant=self._tenant)
        endpoint = self._libconfig.urls["auth"][self._method] 
        self._auth_url = self._base_url + endpoint


    def check_token_in_buffer(self) -> bool:
        self.logger.debug("Checking token in buffer...")
        """
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        time_until_exp = self.token_expiry - now

        if time_until_exp < datetime.timedelta(minutes=self.token_exp_thold_mins):
            self.logger.debug("Token in buffer")
            self.logger.debug(now)
            self.logger.debug(time_until_exp)
            self.logger.debug(self.token_exp_thold_mins)
            
            return True
        
        self.logger.debug("Token not in buffer")
        return False
    

    def check_token_is_expired(self) -> bool:
        self.logger.debug("Checking if Token expired")
        """
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        if self.token_expiry < now:
            self.logger.debug("Token expiried:")
            self.logger.debug(now)
            self.logger.debug(self.token_expiry)
            return True
        
        self.logger.debug("Token not expired")
        return False
    

    def check_token(self) -> None:
        """
        """
        if self.check_token_is_expired():
            self._set_new_token()
            if self.check_token_in_buffer():
                raise Exception("Buffer longer than token lifetime")
            
        elif self.check_token_in_buffer():
            if self. _method == "bearer":
                self._keep_alive_token()
            elif self._method == "oauth":
                self._set_new_token()

            if self.check_token_in_buffer():
                self.token_expiry
                raise Exception("Buffer longer than token lifetime")
            

    def token(self) -> None:
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
        self.logger.debug("_set_new_token starting")
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
            now = datetime.datetime.now()
            self.token_expiry = now + datetime.timedelta(seconds=call_json["expires_in"])
            self.logger.debug("_set_new_token complete")

        else:
            raise Exception("date time parse issue")
    

    def _keep_alive_token(self):
        self.logger.debug("_keep_alive_token starting")
        """
        Pleaced to ensure if call accidentally made with wrong interface
        """
        self.logger.debug("_keep_alive_token complete")
        raise Exception("Action not available with OAuth interface")


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
        self._set_new_token()

    # Magic

    def __str__(self):
        return f"Bearer Token Object for {self._tenant}"

    # Private

    def _init_auth(self):
        self.logger.debug("_init_auth starting")
        """
        """
        if self.username and self.password:
            credstring = f"{self.username}:{self.password}"
            self.basic_auth_token = b64encode(bytes(credstring, encoding="UTF-8")).decode()
        elif self.basic_auth_token:
            pass
        else:
            raise InitError("Invalid Auth supplied")
        
        self.logger.debug("_init_auth complete")


    def _set_new_token(self):
        self.logger.debug("_set_new_token starting")
        """
        Gets new token
        update obj values
        """
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
            self.token_expiry = datetime.datetime.fromisoformat(expiry_str.replace('Z', '+00:00'))
            self.logger.debug("_set_new_token complete")
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
            self.token_expiry = datetime.datetime.fromisoformat(expiry_str.replace('Z', '+00:00'))
            self.logger.debug("_keep_alive_token complete")

        else:
            raise Exception("Error keeping token alive")
