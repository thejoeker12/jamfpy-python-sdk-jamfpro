"""Jamf Classic API Endpoint for Buildings"""

from ._parent import Endpoint

class Buildings(Endpoint):
    _uri = "/buildings"
    _name = "buildings"

