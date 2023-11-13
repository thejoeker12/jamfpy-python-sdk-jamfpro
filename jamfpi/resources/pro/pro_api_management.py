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


    
