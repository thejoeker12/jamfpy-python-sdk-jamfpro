"""Module for Endpoint parent class"""

# pylint: disable=import-outside-toplevel

from abc import abstractmethod


class Endpoint:
    """Endpoint parent class"""
    def __init__(self, api):
        from ..client.client import API
        api: API
        self._api = api

    @abstractmethod
    def delete_by_id(self):
        return
    
    @abstractmethod
    def get_all(self):
        return

