"""Base endpoint class providing common functionality and structure for all Jamf Pro API endpoints."""
# pylint: disable=import-outside-toplevel
from requests import Request, Response

class Endpoint:
    """Base class for all Jamf Pro API endpoints, providing common functionality and structure."""
    _uri = None
    _name = None
    def __init__(self, api):
        """Initialize endpoint with API client instance."""
        from ..client.client import API
        api: API
        self._api = api

class ClassicEndpoint(Endpoint):
    """Base class for Classic Jamf Pro API endpoints, implementing standard CRUD operations."""

    def get_all(self, suffix: str | None = None) -> Response:
        """Get all records for this endpoint.
        Optionally uses a provided suffix, otherwise defaults to the endpoint's base URI.
        """
        effective_suffix = suffix if suffix is not None else self._uri
        
        return self._api.do(
            Request(
                method="GET",
                url=self._api.url() + effective_suffix,
                headers=self._api.header("read")["json"]
            )
        )

    def get_by_id(self, target_id: int) -> Response:
        """Get a single record by ID."""
        suffix = self._uri + f"/id/{target_id}"
        return self._api.do(
            Request(
                method="GET",
                url=self._api.url() + suffix,
                headers=self._api.header("read")["json"]
            )
        )

    def update_by_id(self, target_id: int, updated_configuration: str) -> Response:
        """Update a record by ID with new configuration."""
        suffix = self._uri + f"/id/{target_id}"
        return self._api.do(
            Request(
                method="PUT",
                url=self._api.url() + suffix,
                headers=self._api.header("create-update")["xml"],
                data=updated_configuration
            )
        )

    def create(self, config_profile: str) -> Response:
        """Create a new record."""
        suffix = self._uri + "/id/0"
        return self._api.do(
            Request(
                method="POST",
                url=self._api.url() + suffix,
                headers=self._api.header("create-update")["xml"],
                data=config_profile
            )
        )

    def delete_by_id(self, target_id: int) -> Response:
        """Delete a record by ID."""
        suffix = self._uri + f"/id/{target_id}"
        return self._api.do(
            Request(
                method="DELETE",
                url=self._api.url() + suffix,
            )
        )


class ProEndpoint(Endpoint):
    """Base class for modern Jamf Pro API endpoints, implementing v1+ API functionality."""
