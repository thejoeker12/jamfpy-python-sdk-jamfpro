"""Base endpoint class providing common functionality and structure for all Jamf Pro API endpoints."""
# pylint: disable=import-outside-toplevel
import json

from requests import Request, Response

from ..client.exceptions import JamfAPIError


class Endpoint:
    """Base class for all Jamf Pro API endpoints, providing common functionality and structure."""
    _uri = None
    _name = None
    def __init__(self, api):
        """Initialize endpoint with API client instance."""
        from ..client.api import API
        self._api: API = api

    @staticmethod
    def _repackage_response(original: Response, new_data) -> Response:
        # Rebuild a Response around new_data, preserving the original's status/headers/encoding/url.
        new = Response()
        new.status_code = original.status_code
        new.headers = original.headers.copy()
        new.encoding = original.encoding
        new.url = original.url
        new.request = original.request
        encoding = new.encoding or "utf-8"
        new._content = json.dumps(new_data).encode(encoding)  # pylint: disable=protected-access
        new.headers["Content-Length"] = str(len(new._content))  # pylint: disable=protected-access
        return new


class ClassicEndpoint(Endpoint):
    """Base class for Classic Jamf Pro API endpoints, implementing standard CRUD operations."""

    def get_all(self, suffix: str | None = None, xml_response: bool = False) -> Response:
        """Get all records for this endpoint.
        Optionally uses a provided suffix, otherwise defaults to the endpoint's base URI.
        """
        effective_suffix = suffix or self._uri

        read_header = "json" if not xml_response else "xml"

        return self._api.do(
            Request(
                method="GET",
                url=self._api.url() + effective_suffix,
                headers=self._api.header("read")[read_header]
            )
        )


    def get_by_id(self, target_id: int, xml_response: bool = False) -> Response:
        """Get a single record by ID."""
        suffix = self._uri + f"/id/{target_id}"
        read_header = "json" if not xml_response else "xml"
        return self._api.do(
            Request(
                method="GET",
                url=self._api.url() + suffix,
                headers=self._api.header("read")[read_header]
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


    def name(self):
        """returns name for easy response browsing"""
        return self._name


class ProEndpoint(Endpoint):
    """Base class for modern Jamf Pro API endpoints, implementing standard CRUD and pagination.

    Mirrors ClassicEndpoint, adapted to Pro idioms: versioned URLs (via ``_version``), a plain
    ``/{id}`` id path (no ``/id/`` segment), and JSON request bodies. Simple Pro resources only
    set ``_uri``, ``_name`` and ``_version`` and inherit every method below.
    """

    _version = "1"
    _page_size = 100

    def get_all(self, page_size: int | None = None, sort: str | None = None) -> Response:
        """Get all records, transparently paginating and aggregating into one Response.

        Walks the ``page``/``page-size`` cursor until every record is collected, then returns a
        single Response whose JSON body is ``{"totalCount": N, "results": [...]}``.
        """
        size = page_size or self._page_size
        accumulated, page, total_count = [], 0, None
        resp = None
        while True:
            url = f"{self._api.url(self._version)}{self._uri}?page={page}&page-size={size}"
            if sort:
                url += f"&sort={sort}"
            resp = self._api.do(
                Request("GET", url=url, headers=self._api.header("read")["json"])
            )
            if not resp.ok:
                raise JamfAPIError(f"get_all failed on page {page}: {resp.status_code}")

            body = resp.json()
            results = body.get("results", [])
            total_count = body.get("totalCount", total_count)
            accumulated.extend(results)

            if not results or len(results) < size:
                break
            if total_count is not None and len(accumulated) >= total_count:
                break
            # Defends against a server that ignores `page` and would otherwise loop forever.
            if page > (max(total_count or 0, 0) // size) + 2:
                break
            page += 1

        return self._repackage_response(resp, {"totalCount": len(accumulated), "results": accumulated})

    def get_by_id(self, target_id: int) -> Response:
        """Get a single record by ID."""
        return self._api.do(
            Request(
                "GET",
                url=self._api.url(self._version) + f"{self._uri}/{target_id}",
                headers=self._api.header("read")["json"]
            )
        )

    def create(self, payload: dict) -> Response:
        """Create a new record from a JSON payload."""
        return self._api.do(
            Request(
                "POST",
                url=self._api.url(self._version) + self._uri,
                headers=self._api.header("create-update")["json"],
                json=payload
            )
        )

    def update_by_id(self, target_id: int, payload: dict) -> Response:
        """Update a record by ID with a JSON payload."""
        return self._api.do(
            Request(
                "PUT",
                url=self._api.url(self._version) + f"{self._uri}/{target_id}",
                headers=self._api.header("create-update")["json"],
                json=payload
            )
        )

    def delete_by_id(self, target_id: int) -> Response:
        """Delete a record by ID."""
        return self._api.do(
            Request(
                "DELETE",
                url=self._api.url(self._version) + f"{self._uri}/{target_id}",
                headers=self._api.header("delete")["json"]
            )
        )

    def name(self):
        """returns name for easy response browsing"""
        return self._name
