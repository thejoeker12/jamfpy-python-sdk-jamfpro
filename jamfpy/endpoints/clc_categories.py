"""Jamf Classic API Endpoint Code for Computer Groups"""

from requests import Request
from ._parent import Endpoint
from __future__ import annotations
from ..client.client import API

class Categories(Endpoint):
    _uri = "/categories"

    def get_all(self):
        suffix = self._uri
        return self._api.do(
            Request(
                method = "GET",
                url = self._api.url() + suffix,
                headers = self._api.header("read")["json"]
            )
        )


    def get_by_id(self, target_id: int):
        suffix = self._uri + f"/id/{target_id}"
        return self._api.do(
            Request(
                method = "GET",
                url=self._api.url() + suffix,
                headers = self._api.header("read")["json"]
            )
        )


    def create(self, payload_xml):
        suffix = self._uri + "/id/0"
        return self._api.do(
            Request(
                method = "POST",
                url=self._api.url() + suffix,
                headers = self._api.header("create-update")["xml"],
                data=payload_xml
            )
        )


    def update_by_id(self, target_id, payload_xml):
        suffix = self._uri + f"/id/{target_id}"
        return self._api.do(
            Request(
                method = "PUT",
                url=self._api.url() + suffix,
                headers = self._api.header("create-update")["xml"],
                data=payload_xml
            )
        )


    def delete_by_id(self, target_id):
        suffix = self._uri + f"/id/{target_id}"
        return self._api.do(
            Request(
                method = "DELETE",
                url=self._api.url()+ suffix,
                headers = self._api.header("delete")["xml"]
            )
        )
