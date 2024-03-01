"""Default config dictionary for module. Defaulted to if file not provided"""

ROUND_AMOUNT = 3


defaultconfig = {
    "urls" : {
        "base": "https://{tenant}.jamfcloud.com",
        "auth": {
            "bearer": "/api/v1/auth/token",
            "oauth": "/api/oauth/token",
            "invalidate-token": "/api/v1/auth/invalidate-token",
            "keep-alive": "/api/v1/auth/keep-alive"
        },
        "api" : {
            "classic": "/JSSResource",
            "pro": "/api/v{jamfapiversion}"
        }
        },
    "headers" : {
        "auth": {
            "oauth": {
                "Content-Type": "application/x-www-form-urlencoded"
            }
        },
        "classic": {
            "basic-json": {
                "accept": "application/json"
            },
            "basic-xml": {
                "accept": "text/xml"
            },
            "put": {
                "accept": "text/xml",
                "content-type": "text/xml"
            },
            "post-json": {
                "accept": "application/json",
                "content-type": "application/xml"
            },
            "post-xml": {
                "accept": "text/xml",
                "content-type": "application/xml"
            }
        },
        "pro": {
            "basic": {
                "accept": "application/json"
            },
            "put": {
                "accept": "application/json",
                "content-type": "application/json"
            },
            "image": {
                "accept": "image/*"
            }
        },
        "universal": {
            "bearer_with_auth": {
                "accept": "application/json",
                "Authorization": "Bearer {token}"
            }
        }
    }
}


class MasterConfig:
    """Default configuration class"""
    def __init__(
            self,
            data
    ):
        self.data = data
        self.validate_data_structure()

    def validate_data_structure(self):
        """validates structure of config data"""
        data = self.data
        try:
            self.urls = data["urls"]
            self.headers = data["headers"]
        except KeyError as e:
            raise KeyError("Config Validation Error - Check config") from e
