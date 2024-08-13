"""Module for Endpoint parent class"""

# pylint: disable=import-outside-toplevel

class Endpoint:
    """Endpoint parent class"""
    def __init__(self, api):
        from ..client.client import API
        self._api: API = api
