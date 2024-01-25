"""Endpoints for configuration profiles"""

from requests import Request
from ..endpoint_parent import Endpoint


class ConfigurationProfiles(Endpoint):
    """Configuration profiles object"""
    _uri = "/osxconfigurationprofiles"

    def get_all(self, accept_format: str = "xml"):
        # // TODO docstring
        if accept_format.lower() not in ["json", "xml"]:
            raise ValueError(f"Invalid accept format provided (allowed: 'xml', 'json'): {accept_format}")

        url = self._api.url() + self._uri
        headers = self._api.header(f"basic-{accept_format}")
        req = Request("GET", url=url, headers=headers)
        resp = self._api.do(req)
        return resp

    def get_by_id(self, target_id: int, accept_format: str = "xml"):
        # // TODO docstring
        if accept_format.lower() not in ["json", "xml"]:
            raise ValueError(f"Invalid accept format provided (allowed: 'xml', 'json'): {accept_format}")

        url = self._api.url() + self._uri + f"/id/{target_id}"
        headers = self._api.header(f"basic-{accept_format}")
        req = Request("GET", url=url, headers=headers)
        resp = self._api.do(req)
        return resp


    def update_by_id(self, target_id: int, updated_configuration: str):
        # // TODO docstring
        url = self._api.url() + self._uri + f"/id/{target_id}"
        headers = self._api.header("put")
        req = Request("PUT", url=url, headers=headers, data=updated_configuration)
        resp = self._api.do(req)
        return resp


    def create(self, config_profile: str):
        # // TODO docstring
        url = self._api.url() + self._uri + "/id/0"
        headers = self._api.header("post")
        req = Request("POST", url=url, headers=headers, data=config_profile)
        resp = self._api.do(req)
        return resp


    def delete_by_id(self, target_id: int):
        # // TODO docstring
        url = self._api.url() + self._uri + f"/id/{target_id}"
        headers = self._api.header("basic-json")
        req = Request("DELETE", url, headers=headers)
        resp = self._api.do(req)
        return resp
