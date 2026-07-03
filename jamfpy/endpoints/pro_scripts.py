"""Endpoint module for managing Jamf Pro scripts."""

from .models import ProEndpoint


class Scripts(ProEndpoint):
    """Endpoint for managing scripts in the modern Jamf Pro API (v1+)."""
    _uri = "/scripts"
    _name = "scripts"
    _version = "1"
