"""Jamf Classic API Endpoint Code for Computer Groups"""
# pylint: disable=relative-beyond-top-level, too-few-public-methods

import requests
from ..endpoint_parent import Endpoint

class ComputerGroups(Endpoint):
    """
    Represents a handler for computer groups-related operations in an API.

    This class provides methods to interact with the computer groups endpoint
    of an API. It extends the 'Endpoint' class from the 'endpoint_parent' module.

    Attributes:
    suffix (str): The specific endpoint suffix for computer groups.

    Args:
    api_config (obj): The configuration object for the API, typically containing
                        URL, headers, and other necessary details.
    """

    _uri = "/computergroups"

    def get_by_id(self, target_id: int):
        """
        Retrieves a computer group by its unique identifier.

        Sends a GET request to the API to fetch details of a specific computer group
        based on its ID.

        Args:
        id (int): The unique identifier of the computer group.

        Returns:
        obj: The response object from the API call, typically containing the
            details of the requested computer group.
        """
        suffix = self._uri + f"/id/{target_id}"
        url = self._api.url() + suffix
        headers = self._api.header("basic_json")
        req = requests.Request("GET", url=url, headers=headers)
        call = self._api.do(req)
        return call

    def get_by_name(self, name: str):
        """// TODO me"""

    # // TODO finish the endpoints


# // TODO Write computer group object


class ComputerGroup:
    "// TODO this docstring"
    def __init__(self):
        "// TODO this docstring"
