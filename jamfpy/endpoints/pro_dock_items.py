"""Endpoint module for managing Jamf Pro dock items."""

from .models import ProEndpoint


class DockItems(ProEndpoint):
    """Endpoint for managing dock items in the modern Jamf Pro API (v1+)."""
    _uri = "/dock-items"
    _name = "dock_items"
    _version = "1"
