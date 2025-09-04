"""Constants and configuration values used throughout the Jamf Pro API client."""

from logging import INFO

DEFAULT_LOG_LEVEL = INFO
DEFAULT_TOKEN_BUFFER = 20

AUTH_REQUEST_TIMEOUT = 20
TIME_ROUNDING_AMOUNT = 3

VALID_AUTH_METHODS = ("oauth2", "basic")
