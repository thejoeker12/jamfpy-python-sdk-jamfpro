"""Default config dictionary for module. Defaulted to if file not provided"""

defaultconfig = {
    "urls" : {
        "base": "https://{tenant}.jamfcloud.com",
        "bearer": "/api/v1/auth/token",
        "oauth": "/api/oauth/token",
        "invalidate_token": "/api/v1/auth/invalidate-token",
        "keep_alive": "/v1/auth/keep-alive",
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
            "basic": {
                "accept": "application/json"
            },
            "put": {
                "accept": "application/json",
                "content-type": "text/xml"
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
            "basic)with_auth": {
                "accept": "application/json",
                "Authorization": "bearer {token}"
            }
        }
    }
}
