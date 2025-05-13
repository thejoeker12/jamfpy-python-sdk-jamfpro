"""Enums for authentication methods and other constants."""

from enum import Enum


class AuthMethod(Enum):
    """Authentication methods supported by the Jamf Pro API."""
    OAUTH2 = "oauth2"
    BASIC = "basic"