"""Jamf Classic API Endpoint Code for X"""
from ._parent import Endpoint

class Categories(Endpoint):
    _uri = "/categories"
    _name = "categories"
