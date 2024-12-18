"""Endpint module for Jamf Pro API - API Management"""

import requests
from ...client.exceptions import JamfAPIError
from ..endpoint_parent import Endpoint


class APIRoles(Endpoint):  
    _uri = "/api-roles"

    def get_all(self):
        url = self._api.url("1") + self._uri
        headers = self._api.header("basic")
        req = requests.Request("GET", url=url, headers=headers)
        return self._api.do(req)


class APIRolePrivileges(Endpoint):
    _uri = "/api-role-privileges"

    def get_all(self):
        url = self._api.url("1") + self._uri
        headers = self._api.header("basic")
        req = requests.Request("GET", url=url, headers=headers)
        return self._api.do(req)


class APIIntegrations(Endpoint):
    _uri = "/api-integrations"

    def get_all(self):
        url = self._api.url("1") + self._uri
        headers = self._api.header("basic")
        req = requests.Request("GET", url=url, headers=headers)
        return self._api.do(req)
