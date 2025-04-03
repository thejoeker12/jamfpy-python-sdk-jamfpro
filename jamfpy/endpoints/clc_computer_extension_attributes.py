"""Jamf Classic API Endpoint Code for Computer Groups"""

from ._parent import Endpoint

class ExtensionAttributes(Endpoint):
    _uri = "/computerextensionattributes"
    _name = "computer_extension_attributes"

  