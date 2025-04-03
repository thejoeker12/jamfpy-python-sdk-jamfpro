"""Endpoint code for Jamf Classic API Policies"""

from ._parent import Endpoint


class Policies(Endpoint):
    
    _uri = "/policies"
    _name = "policies"

   