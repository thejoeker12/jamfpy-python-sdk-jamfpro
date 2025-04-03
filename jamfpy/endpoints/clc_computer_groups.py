"""Jamf Classic API Endpoint Code for Computer Groups"""

from ._parent import Endpoint

class ComputerGroups(Endpoint):

    _uri = "/computergroups"
    _name = "computer_groups"


   