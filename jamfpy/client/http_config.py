"""HTTP configuration module for managing API request settings and configurations."""

class HTTPConfig:
    """Configuration class for managing HTTP request settings, URLs, and headers for Jamf Pro API interactions."""
    urls = {
        "base_cloud": "https://{tenant}.jamfcloud.com",
        "auth": {
            "bearer": "/api/v1/auth/token",
            "oauth": "/api/oauth/token",
            "invalidate-token": "/api/v1/auth/invalidate-token",
            "keep-alive": "/api/v1/auth/keep-alive"
        },
        "api": {
            "classic": "/JSSResource",
            "pro": "/api/v{jamfapiversion}"
        }
    }

    headers = {
        "auth": {
            "oauth": {
                "Content-Type": "application/x-www-form-urlencoded"
            },
            "bearer": {
                "accept": "application/json",
                "Authorization": "Bearer {token}"
            }
        },
        "crud": {
            "create-update": {
                "xml": {
                    "accept": "text/xml",
                    "content-type": "text/xml"
                },
                "json": {
                    "accept": "application/json",
                    "content-type": "application/json"
                }
            },
            "read": {
                "xml": {
                    "accept": "text/xml"
                },
                "json": {
                    "accept": "application/json"
                }
            },
            "delete": {
                "xml": {
                    "accept": "text/xml"
                },
                "json": {
                    "accept": "application/json"
                }
            },
            "image": {
                "accept": "image/*"
            }
        }
    }

    def __init__(
            self,
            urls: dict = None,
            headers: dict = None
    ):
        self.urls = urls if urls is not None else self.urls
        self.headers = headers if headers is not None else self.headers
