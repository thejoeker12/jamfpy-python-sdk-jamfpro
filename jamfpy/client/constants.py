"""Constants and configuration values used throughout the Jamf Pro API client."""

from logging import INFO

DEFAULT_LOG_LEVEL = INFO
DEFAULT_TOKEN_BUFFER = 20

AUTH_REQUEST_TIMEOUT = 20
TIME_ROUNDING_DECIMAL_COUNT = 3

VALID_AUTH_METHODS = ("oauth2", "basic")

DEFAULT_HTTP_CONFIG_URLS = {
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

DEFAULT_HTTP_CONFIG_HEADERS = {
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
