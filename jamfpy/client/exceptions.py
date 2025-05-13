"""Custom exception classes for handling Jamf Pro API-specific errors and edge cases."""

class JamfAPIError(Exception):
    """Base exception for errors returned by the Jamf Pro API."""


class JamfpyConfigError(Exception):
    """Exception raised when there are configuration-related issues with the jamfpy module."""


class JamfpyInitError(Exception):
    """Exception raised when there are initialization issues with the jamfpy module."""


class JamfAuthError(Exception):
    """Exception raised when there are authentication-related issues with the Jamf Pro API."""
