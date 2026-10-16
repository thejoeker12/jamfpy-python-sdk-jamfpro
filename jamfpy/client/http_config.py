"""HTTP configuration module for managing API request settings and configurations."""

from typing import Any

from .constants import DEFAULT_HTTP_CONFIG_URLS, DEFAULT_HTTP_CONFIG_HEADERS

class HTTPConfig:
    """Configuration class for managing HTTP request settings, URLs, and headers for Jamf Pro API interactions."""

    def __init__(
            self,
            urls: dict[str, Any] | None = None,
            headers: dict[str, Any] | None = None
    ) -> None:
        self.urls: dict[str, Any] = urls or DEFAULT_HTTP_CONFIG_URLS
        self.headers: dict[str, Any] = headers or DEFAULT_HTTP_CONFIG_HEADERS
