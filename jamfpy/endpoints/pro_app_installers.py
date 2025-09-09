from requests import Request, Response
from .models import Endpoint

class AppInstallers(Endpoint):
    _uri = "/app-installers"

    def create(self, payload: dict) -> Response:
        return self._api.do(
            Request(
                "POST",
                url=self._api.url("1") + self._uri,
                headers=self._api.header("create"),
                data=payload
            )
        )