"""HTTP configuration module for managing API request settings and configurations."""

from .constants import DEFAULT_HTTP_CONFIG_URLS, DEFAULT_HTTP_CONFIG_HEADERS

class HTTPConfig:
    """Configuration class for managing HTTP request settings, URLs, and headers for Jamf Pro API interactions."""

    def __init__(
            self,
            urls: dict = None,
            headers: dict = None
    ):
        self.urls = urls or DEFAULT_HTTP_CONFIG_URLS
        self.headers = headers or DEFAULT_HTTP_CONFIG_HEADERS
