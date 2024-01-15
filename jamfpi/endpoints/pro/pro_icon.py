"""Endpoint code for Jamf Pro API Icons"""


from pathlib import Path
from ..endpoint_parent import Endpoint
from requests import Request, Response, request

class Icons(Endpoint):
    suffix = "/icon"

    def get_by_id(self, id: int) -> Response:
        url = self._api.url(1) + self.suffix + f"/{id}"
        headers = self._api.header("basic")
        req = Request("GET", url=url, headers=headers)
        resp = self._api.do(req)
        return resp
        
    def download_by_id(self, id: int) -> Response:
        url = self._api.url(1) + self.suffix + f"/download/{id}"
        headers = self._api.header("image")
        req = Request("GET", url=url, headers=headers)
        resp = self._api.do(req)
        return resp
    
    def download_by_id_from_link(self, id: int) -> Response:
        url = self._api.url(1) + self.suffix + f"/{id}"
        headers = self._api.header("basic")
        req = Request("GET", url=url, headers=headers)
        resp = self._api.do(req)
        resp_json = resp.json()

        self._api.logger.debug("sending GET to image at %s with no headers", resp_json["url"])
        image_resp = request("GET", resp_json["url"])
        self._api.logger.debug("result: %s", image_resp)

        with open(resp_json["name"], "wb") as file:
            file.write(image_resp.content)

        return image_resp
    
    def upload(self, image_filepath: Path) -> Response :
        url = self._api.url(1) + self.suffix
        headers = self._api.header("basic")
        file = open(image_filepath, "rb")
        file_name = image_filepath.name
        payload = {"file": (file_name, file, "image/png")}
        req = Request("POST", url=url, headers=headers, files=payload)
        resp = self._api.do(req)
        return resp

    # // NOTE Doesn't exist but was worth a try. 405 error.
    # def delete(self, id: int) -> Response:
    #     url = self._api.url(1) + self.suffix + f"/{id}"
    #     headers = self._api.header("basic")
    #     req = Request("DELETE", url=url, headers=headers)
    #     resp = self._api.do(req)
    #     return resp 

