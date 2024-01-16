"""Endpoints for configuration profiles"""
from ..endpoint_parent import Endpoint
from requests import Request

class ConfigurationProfiles(Endpoint):
    """Configuration profiles object"""
    suffix = "/osxconfigurationprofiles"

    def get_by_id(self, id: int):
        url = self._api.url() + self.suffix + f"/id/{id}"
        headers = self._api.header("basic-xml")
        req = Request("GET", url=url, headers=headers)
        resp = self._api.do(req)
        return resp
    





