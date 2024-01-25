"""Jamf Classic API Endpoint Code for Computers"""
import requests
from ..endpoint_parent import Endpoint

# pylint: disable=relative-beyond-top-level, too-few-public-methods

class ClassicComputers(Endpoint):
    """TO DO""" # // TODO

    _uri = "/computers"

    def get_all(self) -> (requests.Response, list):
        """Gets all computers from parent API obj"""

        suffix = f"{self._uri}/subset/basic"
        url = self._api.url() + suffix
        headers = self._api.header("basic")
        req = requests.Request("GET", url=url, headers=headers)
        call = self._api.do(req)
        if call.ok:
            out = []
            for comp in call.json()["computers"]:
                out.append(ClassicComputer(
                    self._api.tenant,
                    comp["serial_number"],
                    comp["id"],
                    comp
                ))

            return (call, out)

        return (call, None)


class ClassicComputer:
    # // TODO docstring
    def __init__(self, serial_number, comp_id, raw):
        self.serial_number = serial_number
        self.id = comp_id
        self.raw = raw
