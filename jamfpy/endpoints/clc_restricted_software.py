"""Jamf Classic API Endpoint Code for Computer Groups"""
from requests import Request
from ._parent import Endpoint
from ..client.client import API

class RestrictedSoftware(Endpoint):
    _uri = "/restrictedsoftware"

    def get_all(self):
        suffix = self._uri
        return self._api.do(
            Request(
                method = "GET",
                url = self._api.url() + suffix,
                headers = self._api.header("read")["json"]
            )
        )