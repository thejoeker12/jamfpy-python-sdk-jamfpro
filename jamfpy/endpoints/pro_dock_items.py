"""Endpoint module for managing Jamf Pro dock items."""

from .models import ProCreate, ProDeleteById, ProGetById, ProUpdateById


class DockItems(ProGetById, ProCreate, ProUpdateById, ProDeleteById):
    """Endpoint for managing dock items in the modern Jamf Pro API (v1+).

    Composes the four verbs the schema has: ``/v1/dock-items`` takes only POST, so there is no ``get_all``.
    """
    _uri = "/dock-items"
    _name = "dock_items"
    _version = "1"
