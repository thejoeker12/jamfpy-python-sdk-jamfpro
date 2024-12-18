"""Jamf Classic API Endpoint Code for Computer Groups"""

import requests
from ..endpoint_parent import Endpoint

class ExtensionAttributes(Endpoint):
    _uri = "/computerextensionattributes/id/0"

    def create(self, xml: str):

        suffix = self._uri
        url = self._api.url() + suffix
        headers = self._api.header("basic-xml")
        req = requests.Request("POST", url=url, headers=headers, data=xml)
        call = self._api.do(req)
        return call


    # // TODO finish the endpoints

