"""Jamf Classic API Endpoint Code for X"""
from ._parent import Endpoint

class Packages(Endpoint):
    _uri = "/packages"
    _name = "packages"

  