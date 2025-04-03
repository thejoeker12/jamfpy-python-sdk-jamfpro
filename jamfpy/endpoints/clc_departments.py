"""Endpoints for departments"""

from requests import Request, Response
from ._parent import Endpoint


class Departments(Endpoint):
    """Departments object"""
    _uri = "/departments"
    _name = "departments"

    