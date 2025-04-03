"""Jamf Classic API Endpoint Code for Computer Groups"""

from ..client.client import API

class RestrictedSoftware(Endpoint):
    _uri = "/restrictedsoftware"
    _name = "restricted_software"

