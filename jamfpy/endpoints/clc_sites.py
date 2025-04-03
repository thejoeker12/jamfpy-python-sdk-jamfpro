"""Endpoints for sites"""

from ._parent import Endpoint


class Sites(Endpoint):
    """Sites object"""
    _uri = "/sites"
    _name = "sites"

    