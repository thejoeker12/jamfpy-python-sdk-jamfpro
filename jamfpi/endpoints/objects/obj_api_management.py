
import requests
from ...client.exceptions import JamfAPIError

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

