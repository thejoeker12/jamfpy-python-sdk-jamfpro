from requests import Request, Response
from .models import Endpoint

class AppInstallers(Endpoint):
    _uri = "/app-installers"

    def get_by_id(self, app_installer_id: int):
        return self._api.do(
            Request(
                "GET",
                url=self._api.url("1") + self._uri + f"/deployments/{app_installer_id}",
                headers=self._api.header("create-update")["json"]
            )
        )

    def create(self, payload: dict) -> Response:
        return self._api.do(
            Request(
                "POST",
                url=self._api.url("1") + self._uri + "/deployments",
                headers=self._api.header("create-update")["json"],
                json=payload
            )
        )


    def delete(self, target_id: int) -> Response:
        return self._api.do(
            Request(
                "DELETE",
                url=self._api.url("1") + self._uri + f"/deployments/{target_id}",
                headers=self._api.header("delete")["json"]
            )
        )

