"""Jamf Classic API Endpoint Code for Restricted Software"""

from ..client.client import API

class RestrictedSoftware(Endpoint):
    _uri = "/restrictedsoftware"
    _name = "restricted_software"

