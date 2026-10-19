"""Base endpoint class providing common functionality and structure for all Jamf Pro API endpoints."""
import json
import math
from collections.abc import Iterator
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from typing import TYPE_CHECKING, Any

from requests import Request, Response

if TYPE_CHECKING:
    # Hint-only: the client layer imports the endpoints, so endpoints never import it at runtime and the graph cannot cycle.
    from ..client.api import API


class Endpoint:
    """Base class for all Jamf Pro API endpoints, providing common functionality and structure."""
    _uri: str
    _name: str | None = None
    def __init__(self, api: "API") -> None:
        """Initialize endpoint with API client instance."""
        self._api: API = api

    @staticmethod
    def _repackage_response(original: Response, new_data: object) -> Response:
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


    def name(self) -> str | None:
        """returns name for easy response browsing"""
        return self._name


class ProBase(Endpoint):
    """Shared base of the Pro capability mixins: the API version, the default page size and ``name()``.

    Not used on its own. A Pro endpoint subclasses ``ProEndpoint`` for full CRUD, or composes exactly the
    capability mixins its resource supports (``ProGetAll``, ``ProGetById``, ``ProCreate``, ``ProUpdateById``,
    ``ProDeleteById``), and sets ``_uri``, ``_name`` and ``_version``.
    """

    _version: str = "1"
    _page_size: int = 100

    def name(self) -> str | None:
        """returns name for easy response browsing"""
        return self._name


class ProGetAll(ProBase):
    """Capability: ``get_all``, which pages through the collection and aggregates every page into one Response."""

    def get_all(self, page_size: int | None = None, sort: str | None = None) -> Response:
        """Get all records, paginating the ``page``/``page-size`` cursor and aggregating into one Response.

        Page 0 is fetched first. When its body has a ``totalCount``, the remaining pages are known and are fetched
        together on up to the API's ``parallelism`` worker threads (one at a time, on the calling thread, when it is
        1), then read in page order. Without a ``totalCount`` the pages are walked one at a time until a short or
        empty page, and as a bound against a server that ignores ``page`` the walk stops after page 3: at most four
        pages, 400 records at the default page size of 100. A larger collection comes back truncated there, and the
        aggregate's ``totalCount`` is the count of the results collected, not the server's.

        Returns one Response whose JSON body is ``{"totalCount": N, "results": [...]}``, with N the number of
        results collected; it is built only when every page read was ok. Reading in page order, the first page
        that isn't ok is returned as-is, so the lowest page number wins when several fail, and a request that
        raises raises from here. In parallel, a failed page also stops further pages from starting: the pages
        already in flight (at most ``parallelism``, each with its own retries) finish, and the pages after them
        are never requested. If a later page repeats page 0's results, the server is taken to be ignoring
        ``page``: a WARNING is logged and only the results of the pages before it are returned.
        """
        size = page_size or self._page_size
        first = self._get_page(0, size, sort)
        if not first.ok:
            return first

        body = first.json()
        total_count = body.get("totalCount")
        if total_count is None:
            return self._walk_to_short_page(first, size, sort)

        first_results = body.get("results", [])
        collected = list(first_results)
        last = first
        remaining = list(range(1, math.ceil(total_count / size)))
        for page, resp in zip(remaining, self._fetch_pages(remaining, size, sort)):
            if not resp.ok:
                return resp
            results = resp.json().get("results", [])
            # An empty page 0 is not evidence of anything, so only a repeat of real results trips the guard.
            if first_results and results == first_results:
                self._api._logger.warning(  # pylint: disable=protected-access
                    "get_all: page %d (%s) repeated page 0's results; the server appears to ignore page: %d %s from %s returned",
                    page, resp.url, len(collected), "result" if len(collected) == 1 else "results",
                    "page 0" if page == 1 else f"pages 0-{page - 1}",
                )
                break
            collected.extend(results)
            last = resp

        return self._repackage_response(last, {"totalCount": len(collected), "results": collected})

    def _get_page(self, page: int, size: int, sort: str | None) -> Response:
        url = f"{self._api.url(self._version)}{self._uri}?page={page}&page-size={size}"
        if sort:
            url += f"&sort={sort}"
        return self._api.do(Request("GET", url=url, headers=self._api.header("read")["json"]))

    def _fetch_pages(self, pages: list[int], size: int, sort: str | None) -> Iterator[Response]:
        """Each page's Response, in page order. Once a page fails, no further page is started."""
        parallelism = self._api._parallelism  # pylint: disable=protected-access
        if parallelism == 1 or not pages:
            # Lazy, so a caller that stops at a failed or repeated page sends nothing after it.
            return (self._get_page(page, size, sort) for page in pages)
        with ThreadPoolExecutor(max_workers=min(parallelism, len(pages))) as pool:
            futures: list[Future[Response]] = []
            running: set[Future[Response]] = set()
            failed = False
            while True:
                # Submit only as many pages as can run now. An executor queue would start its pages on its own
                # after a failure, and the worker that returned the failed page would take the next one before
                # this thread could cancel it.
                while not failed and len(futures) < len(pages) and len(running) < parallelism:
                    futures.append(pool.submit(self._get_page, pages[len(futures)], size, sort))
                    running.add(futures[-1])
                if not running:
                    break
                finished, running = wait(running, return_when=FIRST_COMPLETED)
                failed = failed or any(future.exception() is not None or not future.result().ok for future in finished)
        # The with-block has waited for the pages in flight. Results are read in page order, so a page's exception
        # surfaces only if every page before it was ok, as it would in a sequential walk. Pages are submitted in
        # order, so the lowest failed page is among those submitted and the caller stops at or before it.
        return (future.result() for future in futures)

    def _walk_to_short_page(self, first: Response, size: int, sort: str | None) -> Response:
        """No ``totalCount`` on page 0, so the page count is unknown: fetch one page at a time until a short page."""
        accumulated: list[Any] = []
        total_count: int | None = None
        page, resp = 0, first
        while True:
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
            resp = self._get_page(page, size, sort)
            if not resp.ok:
                return resp

        return self._repackage_response(resp, {"totalCount": len(accumulated), "results": accumulated})


class ProGetById(ProBase):
    """Capability: ``get_by_id``."""

    def get_by_id(self, target_id: int) -> Response:
        """Get a single record by ID."""
        return self._api.do(
            Request(
                "GET",
                url=self._api.url(self._version) + f"{self._uri}/{target_id}",
                headers=self._api.header("read")["json"]
            )
        )


class ProCreate(ProBase):
    """Capability: ``create``."""

    def create(self, payload: dict[str, Any]) -> Response:
        """Create a new record from a JSON payload."""
        return self._api.do(
            Request(
                "POST",
                url=self._api.url(self._version) + self._uri,
                headers=self._api.header("create-update")["json"],
                json=payload
            )
        )


class ProUpdateById(ProBase):
    """Capability: ``update_by_id`` (PUT, a best-effort default: some resources are read-only or need PATCH)."""

    def update_by_id(self, target_id: int, payload: dict[str, Any]) -> Response:
        """Update a record by ID with a JSON payload."""
        return self._api.do(
            Request(
                "PUT",
                url=self._api.url(self._version) + f"{self._uri}/{target_id}",
                headers=self._api.header("create-update")["json"],
                json=payload
            )
        )


class ProDeleteById(ProBase):
    """Capability: ``delete_by_id``."""

    def delete_by_id(self, target_id: int) -> Response:
        """Delete a record by ID."""
        return self._api.do(
            Request(
                "DELETE",
                url=self._api.url(self._version) + f"{self._uri}/{target_id}",
                headers=self._api.header("delete")["json"]
            )
        )


class ProEndpoint(ProGetAll, ProGetById, ProCreate, ProUpdateById, ProDeleteById):
    """Base class for modern Jamf Pro API endpoints with full CRUD and pagination: all five capability mixins.

    Mirrors ClassicEndpoint, adapted to Pro idioms: versioned URLs (via ``_version``), a plain
    ``/{id}`` id path (no ``/id/`` segment), and JSON request bodies. Simple Pro resources only
    set ``_uri``, ``_name`` and ``_version`` and inherit every method. A resource that supports only
    some of the verbs composes just those mixins instead (see ``DockItems``).
    """
