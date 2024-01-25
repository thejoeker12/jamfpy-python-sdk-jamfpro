"""Endpint module for Jamf Pro API - API Management"""

import requests
from ...client.exceptions import *
from ..endpoint_parent import Endpoint


class APIRoles(Endpoint):
    # // TODO docstring
    _uri = "/api-roles"

    def get_all(self):
        # // TODO docstring
        url = self._api.url("1") + self._uri
        headers = self._api.header("basic")
        req = requests.Request("GET", url=url, headers=headers)
        call = self._api.do(req)

        if call.ok:
            return call

        raise JamfAPIError("call error")


class APIRolePrivileges(Endpoint):
    # // TODO docstring

    _uri = "/api-role-privileges"

    def get_all(self):
        # // TODO docstring
        url = self._api.url("1") + self._uri
        headers = self._api.header("basic")
        req = requests.Request("GET", url=url, headers=headers)
        call = self._api.do(req)
        return call


class APIIntegrations(Endpoint):
    # // TODO docstring
    _uri = "/api-integrations"


    def get_all(self) -> (requests.Response, list or None):
        # // TODO docstring
        url = self._api.url("1") + self._uri
        headers = self._api.header("basic")
        req = requests.Request("GET", url=url, headers=headers)
        call = self._api.do(req)
        if call.ok:
            out_list = []
            payload = call.json()["results"]
            for acc in payload:
                out_list.append(APIIntegration(
                    acc["accessTokenLifetimeSeconds"],
                    acc["authorizationScopes"],
                    acc["clientId"],
                    acc["displayName"],
                    acc["enabled"],
                    acc["id"],
                    acc
                ))

            return (call, out_list)
        return (call, None)



# // TODO all of this
class APIIntegration:
    def __init__(
            self,
            accessTokenLifetimeSeconds: int,
            authorizationScopes: list,
            clientId: str,
            displayName: str,
            enabled: bool,
            id: int,
            raw
    ) -> None:
        self.accessTokenLifetimeSeconds = accessTokenLifetimeSeconds
        self.authorizationScopes = authorizationScopes
        self.clientId = clientId
        self.displayName = displayName
        self.enabled = enabled
        self.id = id
        self.raw = raw


    def isEmpty(self):
        if len(self.authorizationScopes) == 1:
            if self.authorizationScopes[0].split("-", maxsplit=1)[0] == "placeholder":
                return True
        return False


class APIRole:
    def __init__(
            self,
            api,
            displayName: str,
            id: int,
            privileges: list,
            raw: dict

    ):
        self.displayName = displayName
        self.id = id
        self.privileges = privileges
        self.raw = raw
        self.api = api


    def update_perms(self, perms=None):
        suffix = f"/api-roles/{self.id}"
        url = self.api.url("1") + suffix
        headers = self.api.header("put")
        payload = {
            "displayName": self.displayName,
            "privileges": perms or []
        }
        req = requests.Request(
            "PUT",
            url=url,
            headers=headers,
            json=payload
        )
        resp = self.api.do(req)
        if resp.ok:
            return resp
        else:
            raise JamfAPIError("Bad request", resp, resp.text)