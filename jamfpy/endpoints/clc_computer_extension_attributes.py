"""Jamf Classic API Endpoint Code for Computer Groups"""

from requests import Request, Response
from .endpoint_parent import Endpoint

class ExtensionAttributes(Endpoint):
    _uri = "/computerextensionattributes/id/0"

    def create(self, xml: str) -> Response:
        suffix = self._uri
        return self._api.do(
            Request(
                method="POST",
                url=self._api.url() + suffix,
                headers=self._api.header("create-update")["xml"],
                data=xml
            )
        )



    # // TODO finish the endpoints

