"""Jamf Classic API Endpoint Code for Computer Groups"""

from requests import Request, Response
from ._parent import Endpoint

class ExtensionAttributes(Endpoint):
    _uri = "/computerextensionattributes"

    def get_all(self) -> Response:
        suffix = self._uri
        return self._api.do(
            Request(
                "GET",
                url = self._api.url() + suffix,
                headers=self._api.header("read")["json"]
            )
        )


    def create(self, payload_xml: str) -> Response:
        suffix = self._uri + "/id/0"
        return self._api.do(
            Request(
                method="POST",
                url=self._api.url() + suffix,
                headers=self._api.header("create-update")["xml"],
                data=payload_xml
            )
        )



