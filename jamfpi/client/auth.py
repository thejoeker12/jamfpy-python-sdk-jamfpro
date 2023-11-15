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
            token_exp_thold_mins: int = 2
    ):
        self._tenant = tenant
        self._libconfig = libconfig
        self._logger_cfg = logger_cfg
        self.token_exp_thold_mins = token_exp_thold_mins

        self._init_logger()
        self._init_urls()
        

    def _init_logger(self) -> None:
        """
        Applies proivded custom logger or uses config
        """
        self.logger = self._logger_cfg["custom_logger"] or get_logger (
            name=f"{self._tenant}-auth",
            config=self._logger_cfg
        )


    def _init_urls(self) -> None:
        """Sets URL for gaining a new token"""
        self._base_url = self._libconfig.urls["base"].format(tenant=self._tenant)
        endpoint = self._libconfig.urls["auth"][self._method] 
        self._auth_url = self._base_url + endpoint


    def check_token_in_buffer(self) -> bool:
        """
        """
        now = datetime.datetime.now()
        time_until_exp = self.token_expiry - now
        if time_until_exp > datetime.timedelta(minutes=self.token_exp_thold_mins):
            return True
        
        return False
    

    def check_token_is_expired(self) -> bool:
        """
        """
        now = datetime.datetime.now()
        if self.token_expiry < now:
            return True
        
        return False
    

    def check_token(self) -> None:
        """
        """
        if self.check_token_is_expired():
            self._set_new_token()
            if self.check_token_in_buffer:
                raise Exception("Buffer longer than token lifetime")
            
        elif self.check_token_in_buffer():
            if self. _method == "bearer":
                self._keep_alive_token()
            elif self._method == "oauth":
                self._set_new_token()

            if self.check_token_in_buffer:
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

        else:
            raise Exception("date time parse issue")
    

    def _keep_alive_token():
        """
        Pleaced to ensure if call accidentally made with wrong interface
        """
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
            bearer_auth_token: Optional[str] = None
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
        """
        if self.username and self.password:
            credstring = f"{self.username}:{self.password}"
            self.basic_auth_token = b64encode(bytes(credstring)).decode()
        elif self.basic_auth_token:
            pass
        else:
            raise InitError("Invalid Auth supplied")

        


    def _set_new_token(self):
        """
        Gets new token
        update obj values
        """
        url = self._base_url + self._libconfig.urls["auth"]["bearer"]
        headers_template = self._libconfig.headers["universal"]["basic_with_auth"]
        headers = headers_template.format(token=self.basic_auth_token)
        call = requests.post(
            url=url,
            headers=headers
        )

        if call.ok:
            call_json = call.json()
            self._token_str = call_json["token"]
            expiry_str = call_json["expires"]
            self.token_expiry = datetime.fromisoformat(expiry_str.replace('Z', '+00:00'))

        raise Exception("Error getting new token")
    

    def _keep_alive_token(self):
        """"
        Keeps token alive
        updates obj values
        """
        url = self._base_url + self._libconfig.urls["auth"]["keep-alive"]
        headers_template = self._libconfig["headers"]["universal"]["basic_with_auth"]
        headers = headers_template.format(token=self._token_str)
        call = requests.post(
            url=url,
            headers=headers
        )
        if call.ok:
            call_json = call.json()
            self._token_str = call_json["token"]
            expiry_str = call_json["expires"]
            self.token_expiry = datetime.fromisoformat(expiry_str.replace('Z', '+00:00'))

        raise Exception("Error keeping token alive")


# class OAuth_old:
#     """Object to hold OAuth data and functions"""

#     auth_token = ""
#     token_expiry = ""
#     def __init__(
#             self,
#             tenant: str,
#             libconfig: dict,
#             logger_cfg: dict,
#             oauth_cid: str,
#             oauth_cs: str,
#             token_exp_threshold_mins: int = 0
#     ):

#         # Private
#         self._libconfig = libconfig
#         self._logger_config = logger_cfg
#         self._oauth_cid = oauth_cid
#         self._oauth_cs = oauth_cs

#         # Public
#         self.tenant = tenant
#         self.token_exp_threshold_mins = token_exp_threshold_mins or 2

#         # Init methods
#         self._init_logging()
#         self._set_auth_url()
#         self._set_new_token()

#         self.logger.debug("OAuth Init complete")


#     def __str__(self):
#         return f"Active OAuth Object for {self.tenant}, {self}"

#     # Private Methods

#     def _init_logging(self):
#         """Assign custom logger or use default setting"""
#         self.logger = self._logger_config["custom_logger"] or get_logger(
#             name=f"{self.tenant}-oauth-0",
#             config=self._logger_config
#         )


#     def _check_token_expiry(self) -> bool:
#         """
#         Checks if token is in the buffer zone (within x mins of expiry).
#         If not in buffer, returns True else returns False
        
#         """
#         now = datetime.datetime.now()
#         time_until_expiry = self.token_expiry - now
#         self.logger.debug(f"Checking if token in active window, {now}, {time_until_expiry}")
#         if time_until_expiry > datetime.timedelta(minutes=self.token_exp_threshold_mins):
#             self.logger.debug("Token OK")
#             return True

#         self.logger.debug("Token in buffer")
#         return False


#     def _set_new_token(self) -> requests.Response:
#         """Gets new token from Jamf"""

#         self.logger.debug("Setting new token")

#         url = self._oauth_url
#         headers = self._libconfig["headers"]["auth"]["oauth"]
#         data = {
#             "client_id": self._oauth_cid,
#             "client_secret": self._oauth_cs,
#             "grant_type": "client_credentials"
#         }

#         call = requests.post(url=url, headers=headers, data=data, timeout=10)

#         if call.ok:
#             now = datetime.datetime.now()
#             resp_json = call.json()
#             self.auth_token = resp_json["access_token"]
#             self.token_expiry = now + datetime.timedelta(seconds=resp_json["expires_in"])

#             self.logger.info("New token set successfully")

#             return call

#         raise requests.HTTPError(call.status_code, "Invalid Credentials Supplied")


#     def _set_auth_url(self) -> None:
#         """Sets Auth URL using config"""

#         self.logger.debug("_set_auth_url starting")

#         endpoint = self._libconfig["urls"]["oauth"]
#         self.base_url = self._libconfig["urls"]["base"].format(tenant=self.tenant)
#         self._oauth_url = self.base_url + endpoint

#         self.logger.debug("_set_base_url complete")
#         self.logger.debug(f"Base URL set: {self.base_url}")

#     # Public Methods

#     def invalidate(self):
#         """Invalidates token"""

#         self.logger.warning("Invalidating token")

#         url = self.base_url + self._libconfig["urls"]["invalidate_token"]
#         headers = self._libconfig["headers"]["universal"]["basic_with_auth"].format(self.auth_token)
#         call = requests.post(url, headers=headers, timeout=10)
#         if call.ok:
#             self.logger.warning("Invalidating token successful")

#         return call


#     def token(self):
#         """
#         Checks if token expiry is within buffer
#         if yes, gets new token & returns with exp
#         if no, returns token + exp
#         """
#         data = {"token": self.auth_token, "expiry": self.token_expiry}
#         if self._check_token_expiry():
#             return data

#         self._set_new_token()
#         if not self._check_token_expiry():
#             raise JamfAPIError("Token lifetime shorter than expiry threashold")

#         return data


#     def update_credentials(self, new_cid: str, new_cs: str):
#         """Updates OAuth Credentials"""
#         self._oauth_cid = new_cid
#         self._oauth_cs = new_cs
#         self._set_new_token()



