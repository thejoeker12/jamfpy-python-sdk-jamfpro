"""Endpoint code for Jamf Classic API Policies"""

from requests import Request, Response
from ..endpoint_parent import Endpoint


class Policies(Endpoint):
    
    _uri = "/policies"

    def get_all(self):
        url = self._api.url() + self._uri
        headers = self._api.header("basic-json")
        req = Request("GET", url, headers=headers)
        resp = self._api.do(req)
        return resp

    def get_by_id(self, target_id: int, resp_type: str) -> Response:
        
        url = self._api.url() + self._uri + f"/id/{target_id}"
        headers = self._api.header(f"basic-{resp_type}")
        req = Request("GET", url, headers=headers)
        resp = self._api.do(req, error_on_fail=False)
        return resp

    def create(self, policy_xml: str):
        url = self._api.url() + self._uri + "/id/0"
        headers = self._api.header("basic-xml")
        req = Request("POST", url=url, headers=headers, data=policy_xml)
        resp = self._api.do(req, error_on_fail=False)
        return resp
    
    def delete_by_id(self, target_id) -> Response:
        url = self._api.url() + self._uri + f"/id/{target_id}"
        headers = self._api.header("basic-xml")
        req = Request("DELETE", url=url, headers=headers)
        resp = self._api.do(req, error_on_fail=False)
        return resp