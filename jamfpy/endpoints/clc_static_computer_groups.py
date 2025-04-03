"""Endpoints for static computer groups"""
from ._parent import Endpoint


class StaticComputerGroups(Endpoint):
    """Static computer group object"""
    _uri = "/static_computer_groups"
    _name = "static_computer_groups"
