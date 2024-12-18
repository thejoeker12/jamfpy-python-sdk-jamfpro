"""Jamf Classic API Endpoint Code for Computer Groups"""

import requests
from .endpoint_parent import Endpoint

class ComputerGroups(Endpoint):

    _uri = "/computergroups"

    def get_all(self):
        suffix = self._uri
        url = self._api.url() + suffix
        headers = self._api.header("read")["xml"]
        req = requests.Request("GET", url=url, headers=headers)
        call = self._api.do(req)
        return call

    def get_by_id(self, target_id: int):
        suffix = self._uri + f"/id/{target_id}"
        url = self._api.url() + suffix
        headers = self._api.header("read")["xml"]
        req = requests.Request("GET", url=url, headers=headers)
        call = self._api.do(req)
        return call
    
    def delete_by_id(self, target_id):
        suffix = self._uri + f"/id/{target_id}"
        url = self._api.url() + suffix
        headers = self._api.header("delete")["xml"]
        req = requests.Request("DELETE", url=url, headers=headers)
        call = self._api.do(req, error_on_fail=False)
        return call

    def create(self, xml):
        suffix = self._uri + f"/id/0"
        url = self._api.url() + suffix
        headers = self._api.header("create-update")["xml"]
        req = requests.Request("POST", url=url, headers=headers, data=xml)
        call = self._api.do(req, error_on_fail=False)
        return call
        
