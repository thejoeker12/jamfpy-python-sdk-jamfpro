"""Endpoint module for managing Jamf Pro app installer deployments."""

from .models import ProEndpoint


class AppInstallers(ProEndpoint):
    """Endpoint for managing app installer deployments in the modern Jamf Pro API (v1+).

    Full CRUD from ProEndpoint. Jamf's schema leaves ``/v1/app-installers/deployments`` out; the OPTIONS probe in
    ``api_schemas/pro-supplement.json`` shows all five verbs (GET and POST on the collection, GET, PUT and DELETE
    by id). Nothing documents its paging parameters or bodies, so ``get_all``'s pagination and the body shapes
    are best-effort.
    """
    _uri = "/app-installers/deployments"
    _name = "app_installers"
    _version = "1"
