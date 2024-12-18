"""Jamf Classic API Endpoint Code for Computer Groups"""

from requests import Request
from .endpoint_parent import Endpoint

class Categories(Endpoint):

    _uri = "/categories"

    def get_all(self):
        return self._api.do(
            Request(
                method = "GET",
                url = self._api.url() + self._uri,
                headers = self._api.header("basic-json")
            )
        )


    def get_by_id(self, target_id: int):
        suffix = self._uri + f"/id/{target_id}"
        url = self._api.url() + suffix
        headers = self._api.header("basic-xml")
        req = Request("GET", url=url, headers=headers)
        return self._api.do(req)


    def delete_by_id(self, target_id):
        suffix = self._uri + f"/id/{target_id}"
        url = self._api.url() + suffix
        headers = self._api.header("basic-json")
        req = Request("DELETE", url=url, headers=headers)
        return self._api.do(req)


    def create(self, xml):
        suffix = self._uri + f"/id/0"
        url = self._api.url() + suffix
        headers = self._api.header("basic")
        req = Request("POST", url=url, headers=headers, data=xml)
        return self._api.do(req)

