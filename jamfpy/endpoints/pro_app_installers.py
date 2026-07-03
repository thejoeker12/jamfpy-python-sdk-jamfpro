"""Endpoint module for managing Jamf Pro app installer deployments."""

from .models import ProEndpoint


class AppInstallers(ProEndpoint):
    """Endpoint for managing app installer deployments in the modern Jamf Pro API (v1+).

    All CRUD is inherited from ProEndpoint. Note: ``get_all`` and ``update_by_id`` are the
    inherited defaults and are not verified against the published schema for this resource.
    """
    _uri = "/app-installers/deployments"
    _name = "app_installers"
    _version = "1"
