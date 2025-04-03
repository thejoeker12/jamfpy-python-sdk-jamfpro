"""Endpoints for sites"""
from requests import Request, Response
from ._parent import Endpoint


class Sites(Endpoint):
    """Sites object"""
    _uri = "/sites"
    _name = "sites"
