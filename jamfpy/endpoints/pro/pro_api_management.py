"""Endpint module for Jamf Pro API - API Management"""

import requests
from ...client.exceptions import JamfAPIError
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
            access_token_lifetime_seconds: int,
            authorization_scopes: list,
            client_id: str,
            display_name: str,
            enabled: bool,
            obj_id: int,
            raw
    ) -> None:
        self.access_token_lifetime_seconds = access_token_lifetime_seconds
        self.authorization_scopes = authorization_scopes
        self.client_id = client_id
        self.display_name = display_name
        self.enabled = enabled
        self.obj_id = obj_id
        self.raw = raw


    def is_empty(self):
        if len(self.authorization_scopes) == 1:
            if self.authorization_scopes[0].split("-", maxsplit=1)[0] == "placeholder":
                return True
        return False

# // TODO Revamp Objects

class APIRole:
    def __init__(
            self,
            api,
            display_name: str,
            obj_id: int,
            privileges: list,
            raw: dict

    ):
        self.display_name = display_name
        self.obj_id = obj_id
        self.privileges = privileges
        self.raw = raw
        self.api = api


    def update_perms(self, perms=None):
        suffix = f"/api-roles/{self.obj_id}"
        url = self.api.url("1") + suffix
        headers = self.api.header("put")
        payload = {
            "displayName": self.display_name,
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

        raise JamfAPIError("Bad request", resp, resp.text)
