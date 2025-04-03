"""Endpoints for computers"""

from ._parent import Endpoint


class Computers(Endpoint):
    """Computers object"""
    _uri = "/computers"
    _name = "computers"

 