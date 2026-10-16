"""Endpoint module for managing Jamf Pro app installer deployments."""

from .models import ProEndpoint


class AppInstallers(ProEndpoint):
    """Endpoint for managing app installer deployments in the modern Jamf Pro API (v1+).

    Full CRUD from ProEndpoint. Jamf's schema leaves ``/v1/app-installers/deployments`` out; the OPTIONS probe in
    ``api_schemas/pro-supplement.json`` shows all five verbs (GET and POST on the collection, GET, PUT and DELETE
    by id), and the shapes it observed (``x-jamfpy-observed``) stand in for the bodies Jamf does not document. The
    live suite proves ``get_all`` pages it and runs a full lifecycle, but with no published contract both can change
    without notice.
    """
    _uri = "/app-installers/deployments"
    _name = "app_installers"
    _version = "1"
