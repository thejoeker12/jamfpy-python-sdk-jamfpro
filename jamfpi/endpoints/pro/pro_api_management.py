import requests
from ..objects.obj_api_management import *
from ...client.exceptions import *

class APIRoles:
    def __init__(self, api):
        self.api = api

    def get_all(self):
        suffix = "/api-roles"
        url = self.api.url("1") + suffix
        headers = self.api.header("basic")
        req = requests.Request("GET", url=url, headers=headers)
        call = self.api.do(req)

        if call.ok:
            return call

        raise JamfAPIError("call error")

    

class APIRolePrivileges:
    def __init__(self, api):
        self.api = api


    def get_all(self):
        suffix = "/api-role-privileges"
        url = self.api.url("1") + suffix
        headers = self.api.header("basic")
        req = requests.Request("GET", url=url, headers=headers)
        call = self.api.do(req)
        return call


class APIIntegrations:
    def __init__(self, api):
        self.api = api


    def get_all(self) -> (requests.Response, list or None):
        suffix = "/api-integrations"
        url = self.api.url("1") + suffix
        headers = self.api.header("basic")
        req = requests.Request("GET", url=url, headers=headers)
        call = self.api.do(req)
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